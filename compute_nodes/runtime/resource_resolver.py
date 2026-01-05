
import logging
import bpy
from .textures import TextureManager, DynamicTexturePool
from .scalar_evaluator import ScalarEvaluator, EvalContext
from ..ir.resources import ImageDesc

logger = logging.getLogger(__name__)

class ResourceResolver:
    """
    Handles resource resolution for Compute Executor.
    - Maps Graph Resources (indices) to GPU Textures
    - Handles Dynamic Resizing (evaluating expressions)
    - Manages Readback to Blender Images
    """
    
    def __init__(self, texture_mgr: TextureManager):
        self.texture_mgr = texture_mgr
        self.dynamic_pool = DynamicTexturePool()
        self._resource_textures = {} # idx -> (texture, blender_image)
        self._dynamic_resources = {} # idx -> res_desc
        self._grid_sizes = {} # idx -> (width, height, depth) for Grid Info support
        self._scalar_evaluator = ScalarEvaluator()
        
    def resolve_resources(self, graph, context_width, context_height) -> dict:
        """Map resource indices to GPU textures."""
        texture_map = {}
        self._resource_textures.clear()
        self._dynamic_resources.clear()
        self._grid_sizes.clear()
        
        for idx, res_desc in enumerate(graph.resources):
            if not isinstance(res_desc, ImageDesc):
                continue
            
            is_write = 'WRITE' in res_desc.access.name
            is_internal = getattr(res_desc, 'is_internal', True)
            is_dynamic = getattr(res_desc, 'dynamic_size', False)
            
            # 1. Dynamic Resources (Deferred Allocation)
            if is_dynamic:
                logger.info(f"Dynamic resource detected: {res_desc.name}")
                self._dynamic_resources[idx] = res_desc
                
                # Evaluate size expression for iteration 0 (initial size)
                size_expr = getattr(res_desc, 'size_expression', {})
                if size_expr and (size_expr.get('width') or size_expr.get('height')):
                    # Evaluate for iteration 0
                    initial_size = self.evaluate_dynamic_size(res_desc, 0, context_width, context_height)
                    res_desc.size = initial_size
                    logger.debug(f"Dynamic resource initial size (iter 0): {initial_size}")
                elif res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, None)
                # Track grid size for Grid Info support
                self._grid_sizes[idx] = (tex.width, tex.height, getattr(tex, 'depth', 1))
                continue
            
            # 2. Static Resources
            if is_internal:
                # GPU-Only
                if res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, None)
                # Track grid size for Grid Info support
                self._grid_sizes[idx] = (tex.width, tex.height, getattr(tex, 'depth', 1))
            else:
                # Blender Image Linked
                image = bpy.data.images.get(res_desc.name)
                width = res_desc.size[0] if res_desc.size[0] > 0 else context_width
                height = res_desc.size[1] if res_desc.size[1] > 0 else context_height
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
                    # Resize logic
                    if (image.size[0], image.size[1]) != (width, height):
                        image.scale(width, height)
                
                if image and not is_write:
                    # READ-ONLY from Image
                    tex = self.texture_mgr.get_texture_from_image(image)
                    res_desc.format = tex.format
                elif image and is_write:
                    # WRITABLE
                    res_desc.size = (width, height)
                    res_desc.format = "RGBA32F"
                    tex = self.texture_mgr.create_storage_texture(
                        name=res_desc.name,
                        width=width,
                        height=height,
                        format=res_desc.format
                    )
                else:
                    # Fallback
                    tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                    image = None
                
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, image if is_write else None)
                # Track grid size for Grid Info support
                self._grid_sizes[idx] = (tex.width, tex.height, getattr(tex, 'depth', 1))
        
        return texture_map

    def readback_results(self, graph, texture_map):
        """Readback writable textures to Blender Images."""
        for idx, (original_tex, image) in self._resource_textures.items():
            if image is None:
                continue
            
            res_desc = graph.resources[idx]
            if res_desc.access.name not in {'WRITE', 'READ_WRITE'}:
                continue
            
            # Use actual current texture (might be resized)
            tex = texture_map.get(idx, original_tex)
            
            if tex.width != image.size[0] or tex.height != image.size[1]:
                image.scale(tex.width, tex.height)
            
            self.texture_mgr.readback_to_image(tex, image)

    def evaluate_dynamic_size(self, res_desc, iteration: int, context_width: int, context_height: int) -> tuple:
        """
        Evaluate size expression for dynamic resource using ScalarEvaluator.
        
        This properly interprets the IR expression tree (e.g., 256 * Iteration)
        instead of using a hardcoded formula.
        """
        size_expr = getattr(res_desc, 'size_expression', {})
        
        # Clear cache for new evaluation context
        self._scalar_evaluator.clear_cache()
        
        # Build evaluation context
        ctx = EvalContext(
            iteration=iteration,
            context_width=context_width,
            context_height=context_height,
            context_depth=1,
            grid_sizes=self._grid_sizes.copy()
        )
        
        # Evaluate width
        width = res_desc.size[0] if len(res_desc.size) > 0 else context_width
        if 'width' in size_expr and size_expr['width'] is not None:
            try:
                evaluated = self._scalar_evaluator.evaluate(size_expr['width'], ctx)
                width = int(evaluated)
                logger.debug(f"Evaluated width expression: {width} (iter={iteration})")
            except Exception as e:
                logger.warning(f"Failed to evaluate width expression: {e}")
        
        # Evaluate height
        height = res_desc.size[1] if len(res_desc.size) > 1 else context_height
        if 'height' in size_expr and size_expr['height'] is not None:
            try:
                evaluated = self._scalar_evaluator.evaluate(size_expr['height'], ctx)
                height = int(evaluated)
                logger.debug(f"Evaluated height expression: {height} (iter={iteration})")
            except Exception as e:
                logger.warning(f"Failed to evaluate height expression: {e}")
        
        # Clamp to valid texture dimensions
        width = max(1, min(16384, width))
        height = max(1, min(16384, height))
        
        return (width, height)

    def get_dynamic_resources(self):
        return self._dynamic_resources
    
    def update_grid_size(self, idx: int, width: int, height: int, depth: int = 1):
        """Update tracked grid size (called by executor when textures are resized)."""
        self._grid_sizes[idx] = (width, height, depth)
    
    def cleanup(self):
        self.dynamic_pool.release_all()
