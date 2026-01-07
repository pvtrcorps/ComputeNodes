"""
ResourceResolver - Phased resource allocation for Compute Executor.

This module provides phased resource resolution, enabling correct handling
of dynamic resources that depend on loop outputs.

Key Concepts:
- STATIC resources: Known at compile time, allocated in Phase 0
- AFTER_LOOP resources: Depend on loop outputs, allocated after loops execute
- ON_DEMAND resources: Allocated lazily when first used

Architecture:
    executor.py
        │
        ├── resolve_static(graph, state)     # Phase 0
        │
        ├── loop_executor.execute()          # Phase 1 - updates state.resource_sizes
        │
        ├── resolve_pending(graph, state)    # Phase 2 - uses updated sizes
        │
        └── pass_runner.run()                # Phase 3+
"""

import logging
import bpy
from .textures import TextureManager, DynamicTexturePool
from .scalar_evaluator import ScalarEvaluator, EvalContext
from .execution_state import ExecutionState, ResourceLifetime
from ..ir.resources import ImageDesc
from ..ir.ops import OpCode

logger = logging.getLogger(__name__)


class ResourceResolver:
    """
    Handles phased resource resolution for Compute Executor.
    
    Supports three-phase allocation:
    1. resolve_static(): Allocate resources with known sizes
    2. (loop execution happens, updating ExecutionState)
    3. resolve_pending(): Allocate deferred resources using updated sizes
    
    Also provides backward-compatible resolve_resources() for simpler cases.
    """
    
    def __init__(self, texture_mgr: TextureManager):
        self.texture_mgr = texture_mgr
        self.dynamic_pool = DynamicTexturePool()
        self._resource_textures = {}  # idx -> (texture, blender_image)
        self._pending_resources = {}  # idx -> res_desc (deferred)
        self._scalar_evaluator = ScalarEvaluator()
        self._graph = None
    
    # =========================================================================
    # Phased Resolution API
    # =========================================================================
    
    def resolve_static(self, graph, state: ExecutionState) -> dict:
        """
        Phase 0: Resolve all STATIC resources.
        
        Resources that depend on loop outputs are deferred to resolve_pending().
        
        Args:
            graph: IR Graph with resources
            state: ExecutionState to track sizes
            
        Returns:
            texture_map: Dict mapping resource index -> GPU texture
        """
        texture_map = {}
        self._resource_textures.clear()
        self._pending_resources.clear()
        self._graph = graph
        
        for idx, res_desc in enumerate(graph.resources):
            if not isinstance(res_desc, ImageDesc):
                continue
            
            # Classify resource lifetime
            lifetime = self._classify_lifetime(res_desc, graph)
            state.set_lifetime(idx, lifetime)
            
            if lifetime == ResourceLifetime.AFTER_LOOP:
                # Only defer resources that depend on loop outputs
                self._pending_resources[idx] = res_desc
                logger.info(f"Deferring resource[{idx}] '{res_desc.name}' (after_loop)")
            else:
                # STATIC and ON_DEMAND: Allocate immediately
                # ON_DEMAND will be resized during loop execution by _evaluate_dynamic_sizes
                tex, image = self._allocate_resource(idx, res_desc, state)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, image)
                state.update_size(idx, tex.width, tex.height, getattr(tex, 'depth', 1))
        
        logger.debug(f"Phase 0: Resolved {len(texture_map)} resources, deferred {len(self._pending_resources)}")
        return texture_map
    
    def resolve_pending(self, graph, state: ExecutionState, texture_map: dict) -> dict:
        """
        Phase 2: Resolve deferred resources using current ExecutionState.
        
        Called after loops execute, when state.resource_sizes has correct values.
        
        Args:
            graph: IR Graph with resources
            state: ExecutionState with updated sizes from loop execution
            texture_map: Existing texture map to update
            
        Returns:
            Updated texture_map
        """
        for idx, res_desc in list(self._pending_resources.items()):
            # Evaluate size using current state
            size = self._evaluate_size_with_state(res_desc, state)
            
            # Update descriptor size
            if len(size) == 2:
                res_desc.size = size
            else:
                res_desc.size = size[:2]
            
            # Allocate texture
            tex, image = self._allocate_resource(idx, res_desc, state)
            texture_map[idx] = tex
            self._resource_textures[idx] = (tex, image)
            state.update_size(idx, tex.width, tex.height, size[2] if len(size) > 2 else 1)
            state.mark_allocated(idx)
            
            logger.debug(f"Phase 2: Allocated pending resource[{idx}] '{res_desc.name}' at {size}")
        
        self._pending_resources.clear()
        return texture_map
    
    # =========================================================================
    # Backward-Compatible API
    # =========================================================================
    
    def resolve_resources(self, graph, context_width, context_height) -> dict:
        """
        Legacy API: Resolve all resources in one pass.
        
        Maintained for backward compatibility. For cases without
        loop-dependent resources, this works correctly.
        
        For graphs with dynamic resources depending on loops,
        use resolve_static() + resolve_pending() instead.
        """
        # Create temporary state
        state = ExecutionState(
            context_width=context_width,
            context_height=context_height
        )
        
        # Phase 0: Static resources
        texture_map = self.resolve_static(graph, state)
        
        # Phase 2: Pending resources (evaluated with iteration 0)
        # This is the legacy behavior - may give wrong sizes for loop-dependent resources
        texture_map = self.resolve_pending(graph, state, texture_map)
        
        return texture_map
    
    # =========================================================================
    # Lifetime Classification
    # =========================================================================
    
    def _classify_lifetime(self, res_desc: ImageDesc, graph) -> ResourceLifetime:
        """
        Determine when a resource can be allocated.
        
        STATIC: Size is constant or only depends on context
        AFTER_LOOP: Size depends on a loop output resource
        ON_DEMAND: Needs lazy allocation
        """
        is_dynamic = getattr(res_desc, 'dynamic_size', False)
        
        if not is_dynamic:
            return ResourceLifetime.STATIC
        
        # Check size expression for loop dependencies
        size_expr = getattr(res_desc, 'size_expression', {})
        
        # Check source_resource pattern (used by OutputImage inheriting from loop)
        source_idx = size_expr.get('source_resource')
        if source_idx is not None and source_idx < len(graph.resources):
            source_res = graph.resources[source_idx]
            source_name = getattr(source_res, 'name', '')
            # Loop ping-pong buffers have these patterns
            if 'loop_' in source_name or '_ping' in source_name or '_pong' in source_name:
                return ResourceLifetime.AFTER_LOOP
            # Also check if source is itself dynamic
            if getattr(source_res, 'dynamic_size', False):
                return ResourceLifetime.AFTER_LOOP
        # Check if this resource was created inside a loop body
        # loop_body_resource is set during graph extraction when handlers know they're in a loop
        is_loop_body_resource = getattr(res_desc, 'loop_body_resource', False)
        
        if is_loop_body_resource:
            # Resources created inside loop body are always ON_DEMAND
            # They need to be evaluated/resized during each iteration
            return ResourceLifetime.ON_DEMAND
        
        # Check width/height/depth expressions for external resources
        # External outputs (is_internal=False) that depend on loop outputs need AFTER_LOOP
        is_internal = getattr(res_desc, 'is_internal', True)
        
        for dim in ('width', 'height', 'depth'):
            val = size_expr.get(dim)
            if val and self._depends_on_loop_resource(val, graph):
                if not is_internal:
                    # External output depending on loop output -> AFTER_LOOP
                    return ResourceLifetime.AFTER_LOOP
                else:
                    # Internal non-loop-body resource with loop dependency -> AFTER_LOOP
                    # This catches things like Capture.001 that are AFTER the loop
                    return ResourceLifetime.AFTER_LOOP
        
        # Dynamic but not loop-dependent
        return ResourceLifetime.ON_DEMAND
    
    def _depends_on_loop_resource(self, val, graph) -> bool:
        """
        Check if a Value expression depends on a loop resource.
        
        Traverses the expression tree looking for references to
        resources that come from loop outputs (ping/pong buffers).
        """
        if val is None:
            return False
        
        # Check if this value references a resource
        res_idx = getattr(val, 'resource_index', None)
        if res_idx is not None and res_idx < len(graph.resources):
            res = graph.resources[res_idx]
            name = getattr(res, 'name', '')
            # Only loop ping-pong buffers are considered "loop outputs"
            # Dynamic internal resources like resize_Resize should NOT be flagged
            if 'loop_' in name or '_ping' in name or '_pong' in name:
                return True
        
        # Check origin op's inputs recursively
        origin = getattr(val, 'origin', None)
        if origin:
            # Check if it's an IMAGE_SIZE referencing a loop resource
            if hasattr(origin, 'opcode') and origin.opcode == OpCode.IMAGE_SIZE:
                inputs = getattr(origin, 'inputs', [])
                for inp in inputs:
                    if self._depends_on_loop_resource(inp, graph):
                        return True
            
            # Check all inputs recursively
            inputs = getattr(origin, 'inputs', [])
            for inp in inputs:
                if self._depends_on_loop_resource(inp, graph):
                    return True
        
        return False
    
    # =========================================================================
    # Size Evaluation
    # =========================================================================
    
    def _evaluate_size_with_state(self, res_desc: ImageDesc, state: ExecutionState) -> tuple:
        """
        Evaluate size expression using ExecutionState.
        
        Uses state.resource_sizes for accurate post-loop dimensions.
        """
        size_expr = getattr(res_desc, 'size_expression', {})
        
        # Handle direct source_resource reference (used by OutputImage inheriting from loop)
        if 'source_resource' in size_expr:
            source_idx = size_expr['source_resource']
            if source_idx is not None and source_idx in state.resource_sizes:
                src_size = state.resource_sizes[source_idx]
                logger.debug(f"Inheriting size from source resource[{source_idx}]: {src_size}")
                return src_size
        
        if not size_expr:
            # No expression, use descriptor size or context
            w = res_desc.size[0] if res_desc.size[0] > 0 else state.context_width
            h = res_desc.size[1] if len(res_desc.size) > 1 and res_desc.size[1] > 0 else state.context_height
            return (w, h, 1)
        
        # Build EvalContext from ExecutionState
        ctx = EvalContext(
            iteration=state.current_iteration,
            context_width=state.context_width,
            context_height=state.context_height,
            context_depth=state.context_depth,
            grid_sizes=state.resource_sizes.copy()
        )
        
        self._scalar_evaluator.clear_cache()
        
        # Evaluate each dimension
        width = self._eval_dim(size_expr.get('width'), res_desc.size[0], state.context_width, ctx)
        height = self._eval_dim(size_expr.get('height'), 
                                 res_desc.size[1] if len(res_desc.size) > 1 else state.context_height,
                                 state.context_height, ctx)
        depth = self._eval_dim(size_expr.get('depth'), 1, 1, ctx)
        
        return (width, height, depth)
    
    def _eval_dim(self, expr, default: int, fallback: int, ctx: EvalContext) -> int:
        """Evaluate a single dimension expression."""
        if expr is None:
            return default if default > 0 else fallback
        
        try:
            result = self._scalar_evaluator.evaluate(expr, ctx)
            # Handle tuple result (from IMAGE_SIZE)
            if isinstance(result, (tuple, list)):
                result = result[0]
            return max(1, min(16384, int(result)))
        except Exception as e:
            logger.warning(f"Failed to evaluate dimension: {e}")
            return default if default > 0 else fallback
    
    # =========================================================================
    # Resource Allocation
    # =========================================================================
    
    def _allocate_resource(self, idx: int, res_desc: ImageDesc, state: ExecutionState):
        """
        Allocate a GPU texture for a resource.
        
        Returns:
            Tuple of (texture, blender_image or None)
        """
        is_write = 'WRITE' in res_desc.access.name
        is_internal = getattr(res_desc, 'is_internal', True)
        
        # Ensure size is valid
        if res_desc.size == (0, 0) or res_desc.size[0] <= 0:
            res_desc.size = (state.context_width, state.context_height)
        
        if is_internal:
            # GPU-Only texture
            tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
            return (tex, None)
        else:
            # Blender Image linked
            return self._allocate_blender_image(idx, res_desc, state, is_write)
    
    def _allocate_blender_image(self, idx: int, res_desc: ImageDesc, 
                                 state: ExecutionState, is_write: bool):
        """Allocate texture linked to Blender Image."""
        image = bpy.data.images.get(res_desc.name)
        width = res_desc.size[0] if res_desc.size[0] > 0 else state.context_width
        height = res_desc.size[1] if len(res_desc.size) > 1 and res_desc.size[1] > 0 else state.context_height
        is_float = res_desc.format.upper() in ('RGBA32F', 'RGBA16F', 'R32F')
        
        # Create Image if needed
        if image is None and is_write:
            image = bpy.data.images.new(
                name=res_desc.name,
                width=width,
                height=height,
                alpha=True,
                float_buffer=is_float
            )
        elif image and is_write:
            if (image.size[0], image.size[1]) != (width, height):
                image.scale(width, height)
        
        # Get/create texture
        if image and not is_write:
            tex = self.texture_mgr.get_texture_from_image(image)
            res_desc.format = tex.format
            return (tex, None)
        elif image and is_write:
            res_desc.size = (width, height)
            res_desc.format = "RGBA32F"
            tex = self.texture_mgr.create_storage_texture(
                name=res_desc.name,
                width=width,
                height=height,
                format=res_desc.format
            )
            return (tex, image)
        else:
            tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
            return (tex, None)
    
    # =========================================================================
    # Readback & Utilities
    # =========================================================================
    
    def readback_results(self, graph, texture_map):
        """Readback writable textures to Blender Images."""
        for idx, (original_tex, image) in self._resource_textures.items():
            if image is None:
                continue
            
            res_desc = graph.resources[idx]
            if res_desc.access.name not in {'WRITE', 'READ_WRITE'}:
                continue
            
            tex = texture_map.get(idx, original_tex)
            
            if tex.width != image.size[0] or tex.height != image.size[1]:
                image.scale(tex.width, tex.height)
            
            self.texture_mgr.readback_to_image(tex, image)
    
    def get_dynamic_resources(self):
        """Get dict of all dynamic resources (for loop executor to evaluate sizes)."""
        if not self._graph:
            return {}
        
        result = {}
        for idx, res in enumerate(self._graph.resources):
            if getattr(res, 'dynamic_size', False):
                result[idx] = res
        return result
    
    def get_pending_resources(self):
        """Get dict of pending resources."""
        return self._pending_resources.copy()
    
    def update_grid_size(self, idx: int, width: int, height: int, depth: int = 1):
        """Update tracked grid size (called by loop executor)."""
        # This is now handled via ExecutionState
        pass
    
    def evaluate_dynamic_size(self, res_desc, iteration: int, 
                               context_width: int, context_height: int) -> tuple:
        """
        Backward-compatible method for loop_executor.
        
        Creates a temporary ExecutionState for size evaluation.
        """
        temp_state = ExecutionState(
            context_width=context_width,
            context_height=context_height
        )
        temp_state.set_loop_context(iteration, iteration + 1)
        
        return self._evaluate_size_with_state(res_desc, temp_state)[:2]
    
    def cleanup(self):
        """Release pooled textures."""
        self.dynamic_pool.release_all()
