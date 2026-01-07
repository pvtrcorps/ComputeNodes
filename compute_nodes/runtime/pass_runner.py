"""
PassRunner - Executes a single ComputePass.

This module extracts the single-pass execution logic from the monolithic
ComputeExecutor, providing a cleaner separation of concerns.

Responsibilities:
- Compile/retrieve shader for pass
- Bind textures to shader slots
- Calculate dispatch size from write textures
- Set uniforms (dispatch size, loop context)
- Execute compute dispatch
- Insert memory barrier
"""

import math
import time
import logging
import gpu

from ..planner.passes import ComputePass
from ..errors import ShaderCompileError, TextureBindError, DispatchError

logger = logging.getLogger(__name__)


class PassRunner:
    """
    Executes a single compute pass.
    
    This class handles all the low-level details of running one GPU compute
    dispatch, including shader management, texture binding, and dispatching.
    
    Attributes:
        shader_mgr: ShaderManager for shader compilation/caching
        gpu_ops: GPUOps for low-level GPU operations
        loop_context: Dict with current loop iteration info
    
    Example:
        runner = PassRunner(shader_mgr, gpu_ops)
        runner.run(graph, pass_, texture_map, 512, 512)
    """
    
    def __init__(self, shader_mgr, gpu_ops):
        """
        Initialize PassRunner.
        
        Args:
            shader_mgr: ShaderManager instance
            gpu_ops: GPUOps instance for memory barriers etc.
        """
        self.shader_mgr = shader_mgr
        self.gpu_ops = gpu_ops
        
        # Loop context for uniforms (updated by LoopExecutor)
        self._loop_context = {
            'iteration': 0,
            'read_width': 0,
            'read_height': 0,
            'write_width': 0,
            'write_height': 0,
        }
    
    def set_loop_context(self, **kwargs):
        """
        Update loop context for uniform values.
        
        Called by LoopExecutor before each iteration.
        
        Args:
            iteration: Current iteration index (0-based)
            read_width: Width of source texture
            read_height: Height of source texture
            write_width: Width of destination texture
            write_height: Height of destination texture
        """
        self._loop_context.update(kwargs)
    
    def run(self, graph, compute_pass: ComputePass, texture_map: dict, 
            context_width: int, context_height: int) -> None:
        """
        Execute a single compute pass.
        
        Args:
            graph: The IR Graph containing resources
            compute_pass: The ComputePass to execute
            texture_map: Dict mapping resource index -> GPU texture
            context_width: Default width if pass has no explicit size
            context_height: Default height if pass has no explicit size
        """
        # 1. COMPILE SHADER
        shader = self._compile_shader(graph, compute_pass)
        if not shader:
            return
        
        shader.bind()
        
        # 2. BIND TEXTURES
        self._bind_textures(shader, graph, compute_pass, texture_map)
        
        # 3. CALCULATE DISPATCH SIZE
        dispatch_w, dispatch_h, dispatch_d = self._calculate_dispatch_size(
            compute_pass, texture_map, context_width, context_height
        )
        
        # 4. SET UNIFORMS
        self._set_uniforms(shader, dispatch_w, dispatch_h, dispatch_d)
        
        # 5. DISPATCH
        profiling = getattr(graph, 'profile_execution', False)
        self._dispatch(shader, compute_pass, graph, dispatch_w, dispatch_h, dispatch_d, profiling)
        
        # 6. MEMORY BARRIER
        self.gpu_ops.memory_barrier()
    
    def _compile_shader(self, graph, compute_pass: ComputePass):
        """
        Compile shader or retrieve from cache.
        
        Returns:
            Compiled GPU shader, or None on failure
        """
        src = compute_pass.display_source or compute_pass.source
        
        if not src:
            from ..codegen.glsl import ShaderGenerator
            gen = ShaderGenerator(graph)
            src = gen.generate(compute_pass)
            compute_pass.source = src
        
        try:
            return self.shader_mgr.get_shader(
                src,
                resources=graph.resources,
                reads_idx=compute_pass.reads_idx,
                writes_idx=compute_pass.writes_idx,
                dispatch_size=compute_pass.dispatch_size
            )
        except ShaderCompileError:
            # Re-raise specific error as-is
            raise
        except Exception as e:
            raise ShaderCompileError(
                f"Shader compilation failed for pass {compute_pass.id}",
                source=src,
                error_message=str(e)
            ) from e
    
    def _bind_textures(self, shader, graph, compute_pass: ComputePass, texture_map: dict):
        """
        Bind textures to shader uniform slots.
        
        Read-only textures are bound as samplers.
        Write or read-write textures are bound as images.
        """
        used_indices = compute_pass.reads_idx.union(compute_pass.writes_idx)
        sorted_indices = sorted(used_indices)
        binding_map = {res_idx: slot for slot, res_idx in enumerate(sorted_indices)}
        
        for idx in sorted_indices:
            if idx not in texture_map:
                continue
            
            tex = texture_map[idx]
            slot = binding_map[idx]
            uniform_name = f"img_{slot}"
            
            is_read = idx in compute_pass.reads_idx
            is_write = idx in compute_pass.writes_idx
            
            try:
                if is_read and not is_write:
                    # Read-only: bind as sampler2D
                    shader.uniform_sampler(uniform_name, tex)
                else:
                    # Write or read-write: bind as image2D
                    shader.image(uniform_name, tex)
            except Exception as e:
                raise TextureBindError(
                    f"Failed to bind {uniform_name}",
                    uniform_name=uniform_name,
                    texture_size=(tex.width, tex.height) if tex else None
                ) from e
    
    def _calculate_dispatch_size(self, compute_pass: ComputePass, texture_map: dict,
                                  context_width: int, context_height: int) -> tuple:
        """
        Calculate dispatch dimensions.
        
        Priority:
        1. Use explicit size from write textures (runtime size)
        2. Fall back to pass dispatch_size
        3. Fall back to context defaults
        
        Returns:
            Tuple of (width, height, depth)
        """
        dispatch_w, dispatch_h, dispatch_d = compute_pass.dispatch_size
        
        # Defaults
        if dispatch_w == 0:
            dispatch_w = context_width
        if dispatch_h == 0:
            dispatch_h = context_height
        if dispatch_d == 0:
            dispatch_d = 1
        
        # Override with actual write texture sizes (runtime takes precedence)
        max_size = (0, 0)
        for idx in compute_pass.writes_idx:
            if idx in texture_map:
                tex = texture_map[idx]
                max_size = (max(max_size[0], tex.width), max(max_size[1], tex.height))
        
        if max_size != (0, 0):
            dispatch_w, dispatch_h = max_size
        
        return dispatch_w, dispatch_h, dispatch_d
    
    def _set_uniforms(self, shader, dispatch_w: int, dispatch_h: int, dispatch_d: int):
        """Set dispatch and loop context uniforms."""
        try:
            shader.uniform_int("u_dispatch_width", dispatch_w)
            shader.uniform_int("u_dispatch_height", dispatch_h)
            shader.uniform_int("u_dispatch_depth", dispatch_d)
            
            shader.uniform_int("u_loop_iteration", self._loop_context['iteration'])
            shader.uniform_int("u_loop_read_width", self._loop_context['read_width'])
            shader.uniform_int("u_loop_read_height", self._loop_context['read_height'])
            shader.uniform_int("u_loop_write_width", self._loop_context['write_width'])
            shader.uniform_int("u_loop_write_height", self._loop_context['write_height'])
        except Exception as e:
            logger.debug(f"Could not set uniforms: {e}")
    
    def _dispatch(self, shader, compute_pass: ComputePass, graph, 
                  dispatch_w: int, dispatch_h: int, dispatch_d: int, profiling: bool):
        """Execute the compute dispatch."""
        # Calculate workgroup counts
        if dispatch_d > 1:
            local_x, local_y, local_z = 8, 8, 8
        else:
            local_x, local_y, local_z = 16, 16, 1
        
        group_x = math.ceil(dispatch_w / local_x)
        group_y = math.ceil(dispatch_h / local_y)
        group_z = math.ceil(dispatch_d / local_z)
        
        logger.debug(f"Pass {compute_pass.id}: dispatch({dispatch_w}x{dispatch_h}x{dispatch_d}) -> groups({group_x}x{group_y}x{group_z})")
        
        # Profiling: start timer
        start_time = 0.0
        if profiling:
            self.gpu_ops.gl_finish()
            start_time = time.perf_counter()
        
        # Execute dispatch
        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            raise DispatchError(
                f"Dispatch failed for pass {compute_pass.id}",
                dispatch_size=(dispatch_w, dispatch_h, dispatch_d),
                pass_id=compute_pass.id
            ) from e
        
        # Profiling: stop timer and attribute time
        if profiling:
            self.gpu_ops.gl_finish()
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            
            seen_nodes = set()
            for op in compute_pass.ops:
                if hasattr(op, 'origin') and op.origin:
                    node = op.origin
                    if hasattr(node, 'execution_time') and node not in seen_nodes:
                        node.execution_time = elapsed_ms
                        seen_nodes.add(node)
            
            if hasattr(graph, "execution_time_total"):
                graph.execution_time_total += elapsed_ms
