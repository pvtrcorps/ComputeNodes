"""
ComputeExecutor for Compute Nodes runtime.

Orchestrates the execution of compute graphs:
- Resolves resources to GPU textures
- Binds shaders and dispatches compute work
- Handles readback to Blender Image datablocks
- Manages multi-pass loops with ping-pong buffering
"""

import logging
import math
import bpy
import gpu
from .textures import TextureManager, DynamicTexturePool
from .shaders import ShaderManager
from ..planner.passes import ComputePass
from ..planner.loops import PassLoop
from ..ir.resources import ImageDesc

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """
    Orchestrates the execution of a compute graph.
    
    Binds resources, sets uniforms, and dispatches compute shaders.
    Handles multi-pass loops with automatic ping-pong buffering.
    Uses DynamicTexturePool for dynamic-sized resources (Resize in loops).
    """
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        self.dynamic_pool = DynamicTexturePool()  # For dynamic resolution
        self._resource_textures = {}
        self._dynamic_resources = {}  # Track which resources are dynamic

    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """Execute the entire graph by running passes in order."""
        # Phase 1: Resolve Resources
        texture_map = self._resolve_resources(graph, context_width, context_height)
        
        # Phase 2: Execute Passes (handles both ComputePass and PassLoop)
        for item in passes:
            # Robust check for Loop (handles reloading class mismatch)
            if 'PassLoop' in str(type(item)) or hasattr(item, 'body_passes'):
                self._run_pass_loop(graph, item, texture_map, context_width, context_height)
            else:
                self._run_pass(graph, item, texture_map, context_width, context_height)

        # Phase 3: Readback results to Blender Images
        self._readback_results(graph, texture_map)
        
        # Phase 4: Write sequence outputs (Grid3D → Z-slice files)
        if hasattr(graph, 'sequence_outputs') and graph.sequence_outputs:
            self._write_sequence_outputs(graph, texture_map)
        
        # Phase 5: Register GPU-only viewer draw handlers
        if hasattr(graph, 'viewer_outputs') and graph.viewer_outputs:
            self._register_viewer_handlers(graph, texture_map)

    def _resolve_resources(self, graph, context_width, context_height) -> dict:
        """Map resource indices to GPU textures.
        
        Resource handling based on is_internal flag:
        - is_internal=True (Rasterize, Resize): GPU-only texture, no Blender Image
        - is_internal=False (Output): Creates/uses Blender Image datablock
        """
        texture_map = {}
        self._resource_textures.clear()
        self._dynamic_resources.clear()
        
        for idx, res_desc in enumerate(graph.resources):
            if not isinstance(res_desc, ImageDesc):
                continue
            
            is_write = 'WRITE' in res_desc.access.name
            is_internal = getattr(res_desc, 'is_internal', True)  # Default True for GPU-only
            is_dynamic = getattr(res_desc, 'dynamic_size', False)
            
            # Handle dynamic-sized resources (will be allocated at runtime)
            if is_dynamic:
                logger.info(f"Dynamic resource detected: {res_desc.name} - deferred to runtime")
                self._dynamic_resources[idx] = res_desc
                # Create a placeholder with default size for now
                # The actual texture will be created/swapped in _run_pass_loop
                if res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, None)
                continue
            
            if is_internal:
                # GPU-ONLY: Internal texture (Rasterize, Resize)
                # No Blender Image datablock needed - pure VRAM
                if res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, None)  # No image for internal
                logger.debug(f"Internal GPU texture: {res_desc.name} {res_desc.size}")
                
            else:
                # OUTPUT: Needs Blender Image datablock for CPU readback
                image = bpy.data.images.get(res_desc.name)
                
                width = res_desc.size[0] if res_desc.size[0] > 0 else context_width
                height = res_desc.size[1] if res_desc.size[1] > 0 else context_height
                is_float = res_desc.format.upper() in ('RGBA32F', 'RGBA16F', 'R32F')
                
                # Create if doesn't exist
                if image is None and is_write:
                    image = bpy.data.images.new(
                        name=res_desc.name,
                        width=width,
                        height=height,
                        alpha=True,
                        float_buffer=is_float
                    )
                    logger.info(f"Created output image: {res_desc.name} ({width}x{height})")
                
                # Resize if needed
                elif image and is_write:
                    if (image.size[0], image.size[1]) != (width, height):
                        image.scale(width, height)
                        logger.info(f"Resized image {res_desc.name} to {width}x{height}")
                
                if image and not is_write:
                    # READ-ONLY from existing image
                    tex = self.texture_mgr.get_texture_from_image(image)
                    res_desc.format = tex.format
                elif image and is_write:
                    # WRITABLE output
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
        
        return texture_map


    def _run_pass(self, graph, compute_pass: ComputePass, texture_map, context_width, context_height):
        """Execute a single compute pass with its specific dispatch size."""
        # Generate shader source if not already set
        src = compute_pass.display_source or compute_pass.source
        if not src:
            from ..codegen.glsl import ShaderGenerator
            gen = ShaderGenerator(graph)
            src = gen.generate(compute_pass)
            compute_pass.source = src
        
        # Pass read/write indices for correct sampler vs image bindings
        shader = self.shader_mgr.get_shader(
            src, 
            resources=graph.resources,
            reads_idx=compute_pass.reads_idx,
            writes_idx=compute_pass.writes_idx,
            dispatch_size=compute_pass.dispatch_size
        )
        shader.bind()
        
        # Bind resources based on PASS-SPECIFIC access
        used_indices = compute_pass.reads_idx.union(compute_pass.writes_idx)
        
        # Create same binding map as GLSL codegen
        sorted_indices = sorted(used_indices)
        binding_map = {res_idx: slot for slot, res_idx in enumerate(sorted_indices)}
        
        for idx in sorted_indices:
            if idx not in texture_map:
                continue
                
            tex = texture_map[idx]
            # Use sequential binding slot to match shader
            slot = binding_map[idx]
            uniform_name = f"img_{slot}"
            
            # Use pass-specific access (read-only in this pass = sampler, write = image)
            is_read_in_pass = idx in compute_pass.reads_idx
            is_write_in_pass = idx in compute_pass.writes_idx
            
            try:
                if is_read_in_pass and not is_write_in_pass:
                    # Read-only in this pass: bind as sampler
                    shader.uniform_sampler(uniform_name, tex)
                else:
                    # Write or read-write: bind as image
                    shader.image(uniform_name, tex)
            except Exception as e:
                logger.error(f"Failed to bind {uniform_name}: {e}")

        # Determine dispatch dimensions from pass or fallback to context
        dispatch_w, dispatch_h, dispatch_d = compute_pass.dispatch_size
        
        if dispatch_w == 0:
            dispatch_w = context_width
        if dispatch_h == 0:
            dispatch_h = context_height
        if dispatch_d == 0:
            dispatch_d = 1
        
        # DYNAMIC SIZING Logic
        # Dispatch size determines how many threads run.
        # It should match the WRITE area (Output). 
        # If we dispatch larger than write area, we waste threads and risk out-of-bounds writes (or silent discard = crop).
        # If we dispatch smaller, we leave output pixels untouched.
        
        max_size = (0, 0)
        has_writes = False
        
        # 1. Determine Write Area (Primary driver)
        for idx in compute_pass.writes_idx:
            if idx in texture_map:
                tex = texture_map[idx]
                max_size = (max(max_size[0], tex.width), max(max_size[1], tex.height))
                has_writes = True
        
        # 2. If no writes (e.g. side-effects only? rare), or explicitly dependent on reads (e.g. analyze),
        # enforce context or read size. But usually for Image Processing, Write Size is King.
        if not has_writes:
            # Fallback to defaults or read sizes if needed
            # For now, keep fallback to dispatch defaults which usually match context
            max_size = (dispatch_w, dispatch_h)
            
            # Optional: Expand to read size if generic compute? 
            # Let's check reads only if no dispatch size set?
            # Actually, existing logic used reads to expand. 
            # But that caused the Resize Crop bug.
            # So we stick to: Dispatch defined by Graph, overridden ONLY by Writes.
            pass
            
        # Apply override if valid write size found
        if has_writes and max_size != (0,0):
             dispatch_w, dispatch_h = max_size
             logger.info(f"Dispatch override (Write-Driven): {dispatch_w}x{dispatch_h}")
        
        # Apply override if found larger textures
        if max_size != (dispatch_w, dispatch_h):
            logger.info(f"Dispatch override: {dispatch_w}x{dispatch_h} -> {max_size[0]}x{max_size[1]}")
            dispatch_w, dispatch_h = max_size
            

        
        # Workgroup size based on DISPATCH dimensions (must match shader's local_group_size)
        
        # Workgroup size based on DISPATCH dimensions (must match shader's local_group_size)
        # 3D dispatch (z > 1) uses 8x8x8, 2D dispatch uses 16x16x1
        if dispatch_d > 1:
            local_x, local_y, local_z = 8, 8, 8
        else:
            local_x, local_y, local_z = 16, 16, 1
            
        group_x = math.ceil(dispatch_w / local_x)
        group_y = math.ceil(dispatch_h / local_y)
        group_z = math.ceil(dispatch_d / local_z)
        
        logger.debug(f"Pass {compute_pass.id}: dispatch({dispatch_w}x{dispatch_h}x{dispatch_d}) -> groups({group_x}x{group_y}x{group_z})")
        
        # Set dispatch size uniforms for Position normalization
        # Set dispatch size uniforms for Position normalization
        try:
            shader.uniform_int("u_dispatch_width", dispatch_w)
            shader.uniform_int("u_dispatch_height", dispatch_h)
            shader.uniform_int("u_dispatch_depth", dispatch_d)
            # Loop iteration index (0 for non-loop passes, set by _run_pass_loop for loops)
            loop_iter = getattr(compute_pass, '_current_loop_iteration', 0)
            shader.uniform_int("u_loop_iteration", loop_iter)
        except Exception as e:
            logger.debug(f"Could not set uniforms: {e}")
        
        # PROFILING: Start Timer
        should_profile = getattr(graph, 'profile_execution', False)
        start_time = 0.0
        
        if should_profile:
            import time
            self._gl_finish() # Ensure previous work is done
            start_time = time.perf_counter()

        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Dispatch failed: {e}")
            
        # PROFILING: Stop Timer
        if should_profile:
            self._gl_finish() # Ensure this dispatch is done
            end_time = time.perf_counter()
            elapsed_ms = (end_time - start_time) * 1000.0
            
            # Attribute time to participating nodes
            seen_nodes = set()
            for op in compute_pass.ops:
                if hasattr(op, 'origin') and op.origin:
                    node = op.origin
                    # Check if 'node' is a Blender Node object (has 'execution_time' prop)
                    # Note: op.origin might be a proxy or something else depending on graph extraction
                    # But usually it is the Node object.
                    if hasattr(node, 'execution_time') and node not in seen_nodes:
                        node.execution_time = elapsed_ms
                        seen_nodes.add(node)
                        
            # Accumulate total time (simplistic, assumes sequential passes)
            if hasattr(graph, "execution_time_total"):
                graph.execution_time_total += elapsed_ms

        # Memory barrier: ensures texture writes are visible before next pass reads
        self._memory_barrier()

    def _gl_finish(self):
        """Wait for all GPU commands to complete (for profiling)."""
        import platform
        import ctypes
        
        try:
            if platform.system() == 'Windows':
                opengl32 = ctypes.windll.opengl32
                glFinish = opengl32.glFinish
            else:
                # Linux/macOS
                try:
                    libgl = ctypes.CDLL('libGL.so.1')
                except OSError:
                    try:
                        libgl = ctypes.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
                    except OSError:
                        return
                glFinish = libgl.glFinish
            
            glFinish()
        except Exception as e:
            pass

    def _run_pass_loop(self, graph, loop: PassLoop, texture_map, context_width, context_height):
        """
        Execute a multi-pass loop with ping-pong buffering.
        
        For each iteration:
        1. Swap ping-pong buffers for Grid state variables
        2. Execute all body passes
        3. Insert memory barrier
        
        Final result is in the last-written buffer (ping or pong depending on iteration count).
        """
        # Determine iteration count
        iterations = loop.iterations
        if hasattr(iterations, 'constant_value'):
            iterations = int(iterations.constant_value)
        elif not isinstance(iterations, int):
            iterations = 10  # Default fallback
        
        logger.info(f"Running loop: {iterations} iterations, {len(loop.state_vars)} state vars")
        
        # Allocate/ensure ping-pong buffers for Grid state vars
        ping_pong_buffers = {}
        for state in loop.state_vars:
            if state.is_grid and state.ping_idx is not None and state.pong_idx is not None:
                # Get format from state (inherited from source resource, defaults to RGBA32F)
                fmt = getattr(state, 'format', 'RGBA32F')
                
                # Ensure buffers exist in texture_map
                if state.ping_idx not in texture_map:
                    # Create buffer based on size and format from state
                    size = state.size if state.size != (0, 0, 0) else (context_width, context_height, 1)
                    desc = ImageDesc(
                        name=f"loop_ping_{state.name}",
                        access='READ_WRITE',
                        format=fmt,
                        size=size,
                        dimensions=state.dimensions,
                        is_internal=True
                    )
                    tex = self.texture_mgr.ensure_internal_texture(desc.name, desc)
                    texture_map[state.ping_idx] = tex
                
                if state.pong_idx not in texture_map:
                    size = state.size if state.size != (0, 0, 0) else (context_width, context_height, 1)
                    desc = ImageDesc(
                        name=f"loop_pong_{state.name}",
                        access='READ_WRITE',
                        format=fmt,
                        size=size,
                        dimensions=state.dimensions,
                        is_internal=True
                    )
                    tex = self.texture_mgr.ensure_internal_texture(desc.name, desc)
                    texture_map[state.pong_idx] = tex
                
                ping_pong_buffers[state.index] = {
                    'ping': texture_map[state.ping_idx],
                    'pong': texture_map[state.pong_idx],
                    'ping_idx': state.ping_idx,
                    'pong_idx': state.pong_idx,
                    'state': state
                }
                
                # Initialize ping buffer: DIRECT MAP to initial texture for first iteration
                # This avoids quality loss from copying through compute shader
                if state.initial_value is not None and hasattr(state.initial_value, 'resource_index'):
                    init_idx = state.initial_value.resource_index
                    if init_idx is not None and init_idx in texture_map:
                        # Store original ping texture for later iterations
                        if 'original_ping' not in ping_pong_buffers[state.index]:
                            ping_pong_buffers[state.index]['original_ping'] = texture_map[state.ping_idx]
                        # Map ping_idx directly to initial texture (no copy!)
                        texture_map[state.ping_idx] = texture_map[init_idx]
                        ping_pong_buffers[state.index]['ping'] = texture_map[init_idx]
                        logger.info(f"Loop init: mapping ping[{state.ping_idx}] -> initial[{init_idx}]")
        
        # Execute iterations
        for iter_idx in range(iterations):
            # Swap ping-pong based on even/odd iteration
            for buf_info in ping_pong_buffers.values():
                if iter_idx % 2 == 0:
                    # Even iterations: read from ping, write to pong
                    texture_map[buf_info['ping_idx']] = buf_info['ping']
                    texture_map[buf_info['pong_idx']] = buf_info['pong']
                else:
                    # Odd iterations: read from pong, write to ping (swap roles)
                    texture_map[buf_info['ping_idx']] = buf_info['pong']
                    texture_map[buf_info['pong_idx']] = buf_info['ping']
            
            # Execute body passes
            for body_pass in loop.body_passes:
                # Set current iteration for uniform (u_loop_iteration)
                body_pass._current_loop_iteration = iter_idx
                
                # logger.info(f"DEBUG: Processing body item type: {type(body_pass)}")
                if 'PassLoop' in str(type(body_pass)) or hasattr(body_pass, 'body_passes'):
                    # Nested loop - recursive
                    self._run_pass_loop(graph, body_pass, texture_map, context_width, context_height)
                else:
                    self._run_pass(graph, body_pass, texture_map, context_width, context_height)
            
            # Copy blur/filter outputs to pong buffer for ping-pong pattern
            # DYNAMIC SIZING: If source changed size, reallocate ping/pong buffers
            for state in loop.state_vars:
                if hasattr(state, 'copy_from_resource') and state.copy_from_resource is not None:
                    src_idx = state.copy_from_resource
                    
                    if src_idx not in texture_map:
                        continue
                    
                    src_tex = texture_map[src_idx]
                    src_size = (src_tex.width, src_tex.height)
                    
                    # Determine current destination buffer
                    if iter_idx % 2 == 0:
                        dst_key = 'pong'
                    else:
                        dst_key = 'ping'
                    
                    dst = ping_pong_buffers[state.index][dst_key]
                    dst_size = (dst.width, dst.height)
                    
                    # Check if source is a dynamic resource with different size
                    if src_idx in self._dynamic_resources or src_size != dst_size:
                        if src_size != dst_size:
                            # Source changed size - need new buffer
                            logger.info(f"Dynamic state resize: {state.name} {dst_size} -> {src_size}")
                            
                            # Get new buffer from dynamic pool
                            fmt = getattr(state, 'format', 'RGBA32F')
                            new_buf = self.dynamic_pool.get_or_create(
                                src_size, fmt, state.dimensions
                            )
                            
                            # Update ping_pong_buffers with new sized buffer
                            ping_pong_buffers[state.index][dst_key] = new_buf
                            dst = new_buf
                    
                    # Copy from source to destination
                    fmt = getattr(state, 'format', 'RGBA32F')
                    self._copy_texture(src_tex, dst, format=fmt, dimensions=state.dimensions)
            
            # Handle dynamic-sized resources: evaluate expressions and swap textures
            for res_idx, res_desc in self._dynamic_resources.items():
                size_expr = getattr(res_desc, 'size_expression', {})
                if not size_expr:
                    continue
                
                # Evaluate size based on NEXT iteration (prepare for next pass)
                next_iter = iter_idx + 1
                if next_iter < iterations:
                    new_size = self._evaluate_dynamic_size(res_desc, next_iter, context_width, context_height)
                    current_size = (texture_map[res_idx].width, texture_map[res_idx].height)
                    
                    if new_size != current_size:
                        # Size will change next iteration - get new texture
                        logger.info(f"Dynamic resize (prep): {res_desc.name} {current_size} -> {new_size}")
                        new_tex = self.dynamic_pool.get_or_create(new_size, res_desc.format, res_desc.dimensions)
                        texture_map[res_idx] = new_tex
            
            # Memory barrier after each iteration
            self._memory_barrier()
        
        # After loop: final output is in last-written buffer
        # Update texture_map to point to the final buffer
        final_size = None
        for buf_info in ping_pong_buffers.values():
            state = buf_info['state']
            
            # IMPORTANT: If copy_from_resource is set, the actual output is in that
            # resource, not in the ping/pong buffer (e.g., Resize writes to its own output)
            copy_from = getattr(state, 'copy_from_resource', None)
            if copy_from is not None and copy_from in texture_map:
                # Use the Resize/filter output as the final buffer for downstream
                final_buf = texture_map[copy_from]
                logger.info(f"Loop final: using copy_from_resource {copy_from} ({final_buf.width}x{final_buf.height})")
            else:
                # Standard ping-pong: result is in last-written buffer
                # After N iterations, result is in:
                # - pong if N is odd (last write was to pong)
                # - ping if N is even (we haven't written, so it's still in ping from init)
                if iterations % 2 == 1:
                    final_buf = buf_info['pong']
                else:
                    final_buf = buf_info['ping']
            
            final_size = (final_buf.width, final_buf.height)
            
            # Map both indices to final for downstream use
            texture_map[buf_info['ping_idx']] = final_buf
            texture_map[buf_info['pong_idx']] = final_buf
        
        # DYNAMIC SIZING: If final buffer size changed, update output textures
        if final_size and final_size != (context_width, context_height):
            logger.info(f"Dynamic loop output: updating output textures to {final_size}")
            # Find and resize output resources that inherit from loop
            for idx, res_desc in enumerate(graph.resources):
                if hasattr(res_desc, 'is_internal') and not res_desc.is_internal:
                    # This is an output resource - needs resizing
                    old_size = (texture_map[idx].width, texture_map[idx].height) if idx in texture_map else (0, 0)
                    if old_size != final_size:
                        logger.info(f"Resizing output {res_desc.name}: {old_size} -> {final_size}")
                        # Create new output texture at final size
                        new_tex = self.dynamic_pool.get_or_create(final_size, 'RGBA32F', res_desc.dimensions)
                        texture_map[idx] = new_tex
        
        logger.info(f"Loop completed: {iterations} iterations")
    
    def _evaluate_dynamic_size(self, res_desc, iteration: int, 
                                context_width: int, context_height: int) -> tuple:
        """
        Evaluate size expression for a dynamic resource.
        
        Parses the expression tree to find base value for patterns like:
        - base * pow(2, iteration)
        - ADD(base, 0) * POW(2, iter)
        """
        size_expr = getattr(res_desc, 'size_expression', {})
        
        def extract_constant_from_value(val):
            """Recursively find a constant value from a Value/Op tree."""
            if val is None:
                return None
            # Direct constant
            if hasattr(val, 'origin') and val.origin:
                op = val.origin
                if hasattr(op, 'attrs') and 'value' in op.attrs:
                    return op.attrs['value']
                # ADD of constant + 0
                if hasattr(op, 'opcode') and op.opcode.name == 'ADD':
                    if len(op.inputs) >= 1:
                        return extract_constant_from_value(op.inputs[0])
            return None
        
        def get_base_from_mul(expr_val):
            """Extract base from MUL(base, pow(2,iter)) pattern."""
            if expr_val is None:
                return None
            if hasattr(expr_val, 'origin') and expr_val.origin:
                op = expr_val.origin
                if hasattr(op, 'opcode') and op.opcode.name == 'MUL':
                    # First input should be the base (possibly wrapped in ADD)
                    if len(op.inputs) >= 1:
                        return extract_constant_from_value(op.inputs[0])
            return None
        
        # Get width
        width = res_desc.size[0] if len(res_desc.size) > 0 else context_width
        if 'width' in size_expr:
            base = get_base_from_mul(size_expr['width'])
            if base is not None:
                width = max(1, min(16384, int(base * (2 ** iteration))))
                logger.debug(f"Dynamic width: base={base}, iter={iteration} -> {width}")
        
        # Get height  
        height = res_desc.size[1] if len(res_desc.size) > 1 else context_height
        if 'height' in size_expr:
            base = get_base_from_mul(size_expr['height'])
            if base is not None:
                height = max(1, min(16384, int(base * (2 ** iteration))))
                logger.debug(f"Dynamic height: base={base}, iter={iteration} -> {height}")
        
        return (width, height)

    def _copy_texture(self, src, dst, format='RGBA32F', dimensions=2):
        """Copy contents from one texture to another using a compute shader."""
        import math
        
        # Get dimensions
        width = src.width
        height = src.height
        depth = 1
        if dimensions == 3 and hasattr(src, 'depth'):
            depth = src.depth
        
        # Get specialized shader
        shader = self._get_copy_shader(format, dimensions)
        shader.bind()
        
        shader.image('src_tex', src)
        shader.image('dst_tex', dst)
        
        # Dispatch
        if dimensions == 3:
            # 3D Dispatch (8x8x8 local groups)
            group_x = math.ceil(width / 8)
            group_y = math.ceil(height / 8)
            group_z = math.ceil(depth / 8)
        else:
            # 2D Dispatch (16x16 local groups)
            group_x = math.ceil(width / 16)
            group_y = math.ceil(height / 16)
            group_z = 1
            
        gpu.compute.dispatch(shader, group_x, group_y, group_z)
        
        self._memory_barrier()
        logger.debug(f"Texture copy ({dimensions}D, {format}): {src} -> {dst} ({width}x{height}x{depth})")
    
    def _get_copy_shader(self, format, dimensions):
        """Get or create a cached copy shader for the given format/dimensions."""
        # Initialize cache if needed
        if not hasattr(self, '_copy_shader_cache'):
            self._copy_shader_cache = {}
            
        key = (format, dimensions)
        if key in self._copy_shader_cache:
            return self._copy_shader_cache[key]
        
        # Generate Shader
        is_3d = (dimensions == 3)
        img_type = 'FLOAT_3D' if is_3d else 'FLOAT_2D'
        coord_type = 'ivec3' if is_3d else 'ivec2'
        load_coord = 'ivec3(gl_GlobalInvocationID.xyz)' if is_3d else 'ivec2(gl_GlobalInvocationID.xy)'
        
        copy_src = f"""
        void main() {{
            {coord_type} coord = {load_coord};
            vec4 val = imageLoad(src_tex, coord);
            imageStore(dst_tex, coord, val);
        }}
        """
        
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.image(0, format, img_type, 'src_tex', qualifiers={'READ'})
        shader_info.image(1, format, img_type, 'dst_tex', qualifiers={'WRITE'})
        
        if is_3d:
            shader_info.local_group_size(8, 8, 8)
        else:
            shader_info.local_group_size(16, 16, 1)
            
        shader_info.compute_source(copy_src)
        
        try:
            shader = gpu.shader.create_from_info(shader_info)
            self._copy_shader_cache[key] = shader
            logger.debug(f"Created copy shader: {format} {dimensions}D")
            return shader
        except Exception as e:
            logger.error(f"Failed to compile copy shader ({format}, {dimensions}D): {e}")
            raise
        logger.debug("Created texture copy shader")

    def _memory_barrier(self):
        """
        Insert a memory barrier to synchronize texture operations between passes.
        
        Critical when Pass N writes to a texture that Pass N+1 reads.
        Uses platform-specific OpenGL calls with graceful fallback.
        """
        import platform
        
        try:
            import ctypes
            GL_ALL_BARRIER_BITS = 0xFFFFFFFF
            
            if platform.system() == 'Windows':
                opengl32 = ctypes.windll.opengl32
                glMemoryBarrier = opengl32.glMemoryBarrier
            else:
                # Linux/macOS: use libGL
                try:
                    libgl = ctypes.CDLL('libGL.so.1')
                except OSError:
                    try:
                        libgl = ctypes.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
                    except OSError:
                        logger.debug("Could not load OpenGL library for memory barrier")
                        return
                glMemoryBarrier = libgl.glMemoryBarrier
            
            glMemoryBarrier.argtypes = [ctypes.c_uint]
            glMemoryBarrier(GL_ALL_BARRIER_BITS)
        except Exception as e:
            logger.debug(f"Memory barrier not available: {e}")

    def _readback_results(self, graph, texture_map):
        """Readback writable textures to their associated Blender Images.
        
        Also handles save_mode:
        - DATABLOCK: Just readback (default)
        - SAVE: Readback + save to file
        - PACK: Readback + pack into .blend
        """
        import os
        
        # Get output settings if available
        output_settings = getattr(graph, 'output_image_settings', {})
        
        for idx, (original_tex, image) in self._resource_textures.items():
            if image is None:
                continue
                
            res_desc = graph.resources[idx]
            if res_desc.access.name not in {'WRITE', 'READ_WRITE'}:
                continue
            
            # Use the ACTUAL texture from texture_map (may have been dynamically resized)
            tex = texture_map.get(idx, original_tex)
            
            # DYNAMIC SIZING: Resize Blender Image if texture size changed
            if tex.width != image.size[0] or tex.height != image.size[1]:
                logger.info(f"Resizing output Image '{image.name}': {image.size[0]}x{image.size[1]} -> {tex.width}x{tex.height}")
                image.scale(tex.width, tex.height)
            
            # Readback GPU → CPU
            self.texture_mgr.readback_to_image(tex, image)
            
            # Handle save mode
            settings = output_settings.get(res_desc.name, {})
            save_mode = settings.get('save_mode', 'DATABLOCK')
            
            if save_mode == 'SAVE':
                filepath = settings.get('filepath', '')
                file_format = settings.get('file_format', 'OPEN_EXR')
                
                if filepath:
                    abs_path = bpy.path.abspath(filepath)
                    
                    # Create directory if needed
                    dir_path = os.path.dirname(abs_path)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)
                    
                    # Configure format
                    scene = bpy.context.scene
                    old_format = scene.render.image_settings.file_format
                    old_mode = scene.render.image_settings.color_mode
                    old_depth = scene.render.image_settings.color_depth
                    
                    scene.render.image_settings.file_format = file_format
                    scene.render.image_settings.color_mode = 'RGBA'
                    if file_format == 'OPEN_EXR':
                        scene.render.image_settings.color_depth = '32'
                    else:
                        scene.render.image_settings.color_depth = '16'
                    
                    image.save_render(abs_path)
                    
                    # Restore
                    scene.render.image_settings.file_format = old_format
                    scene.render.image_settings.color_mode = old_mode
                    scene.render.image_settings.color_depth = old_depth
                    
                    logger.info(f"Saved {res_desc.name} to {abs_path}")
                    
            elif save_mode == 'PACK':
                if not image.packed_file:
                    image.pack()
                    logger.info(f"Packed {res_desc.name} into .blend")


    def _write_sequence_outputs(self, graph, texture_map):
        """Write Grid3D textures as Z-slice image sequences.
        
        Since GPUTexture.read() only reads the first Z-slice of 3D textures,
        we use a compute shader to extract each slice to a 2D texture,
        then write that to disk.
        """
        import os
        import numpy as np
        
        # Lazy-create slice extraction shader
        if not hasattr(self, '_slice_shader'):
            self._create_slice_shader()
        
        for seq_info in graph.sequence_outputs:
            src_idx = seq_info['source_resource_idx']
            directory = seq_info['directory']
            pattern = seq_info['filename_pattern']
            format_type = seq_info['format']
            width = seq_info['width']
            height = seq_info['height']
            depth = seq_info['depth']
            start_index = seq_info['start_index']
            color_depth = seq_info.get('color_depth', '16')
            
            # Get the GPU texture
            if src_idx not in texture_map:
                logger.warning(f"Sequence output: source texture {src_idx} not found")
                continue
                
            tex3d = texture_map[src_idx]
            
            # Resolve directory path
            abs_dir = bpy.path.abspath(directory)
            os.makedirs(abs_dir, exist_ok=True)
            
            logger.info(f"Writing sequence: {depth} slices to {abs_dir}")
            
            # Create 2D target texture for slice extraction
            tex2d = gpu.types.GPUTexture((width, height), format='RGBA32F')
            
            # Create Blender Image for writing
            temp_img_name = f"__seq_temp_{src_idx}"
            temp_image = bpy.data.images.new(
                name=temp_img_name,
                width=width,
                height=height,
                alpha=True,
                float_buffer=True
            )
            
            # Configure format settings
            scene = bpy.context.scene
            old_format = scene.render.image_settings.file_format
            old_mode = scene.render.image_settings.color_mode
            old_depth = scene.render.image_settings.color_depth
            
            if format_type == 'PNG':
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_depth = color_depth
            elif format_type == 'TIFF':
                scene.render.image_settings.file_format = 'TIFF'
                scene.render.image_settings.color_depth = color_depth
            else:
                scene.render.image_settings.file_format = 'OPEN_EXR'
                scene.render.image_settings.color_depth = '32'
            scene.render.image_settings.color_mode = 'RGBA'
            
            try:
                for z in range(depth):
                    # Extract slice using compute shader
                    self._extract_slice(tex3d, tex2d, z, width, height)
                    
                    # Read 2D texture to CPU
                    raw_data = tex2d.read()
                    data = np.array(raw_data, dtype=np.float32).flatten()
                    
                    # Write to temp image
                    temp_image.pixels.foreach_set(data.tolist())
                    temp_image.update()
                    
                    # Save to file
                    filename = pattern.format(start_index + z)
                    filepath = os.path.join(abs_dir, filename)
                    temp_image.save_render(filepath)
                    
                    if z == 0 or z == depth - 1:
                        logger.debug(f"  Wrote: {filename}")
                
                logger.info(f"Sequence complete: {depth} slices written")
                
            except Exception as e:
                logger.error(f"Failed to write sequence: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Cleanup
                bpy.data.images.remove(temp_image)
                scene.render.image_settings.file_format = old_format
                scene.render.image_settings.color_mode = old_mode
                scene.render.image_settings.color_depth = old_depth
    
    def _create_slice_shader(self):
        """Create compute shader for extracting Z-slices from 3D textures."""
        slice_src = """
void main() {
    ivec2 coord = ivec2(gl_GlobalInvocationID.xy);
    ivec3 coord3d = ivec3(coord.x, coord.y, u_slice_z);
    vec4 val = imageLoad(src_3d, coord3d);
    imageStore(dst_2d, coord, val);
}
"""
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.image(0, 'RGBA32F', 'FLOAT_3D', 'src_3d', qualifiers={'READ'})
        shader_info.image(1, 'RGBA32F', 'FLOAT_2D', 'dst_2d', qualifiers={'WRITE'})
        shader_info.push_constant('INT', 'u_slice_z')
        shader_info.local_group_size(16, 16, 1)
        shader_info.compute_source(slice_src)
        
        self._slice_shader = gpu.shader.create_from_info(shader_info)
        logger.debug("Created slice extraction shader")
    
    def _extract_slice(self, tex3d, tex2d, z, width, height):
        """Extract a single Z-slice from 3D texture to 2D texture."""
        shader = self._slice_shader
        shader.bind()
        
        # Bind textures as images
        shader.image('src_3d', tex3d)
        shader.image('dst_2d', tex2d)
        shader.uniform_int('u_slice_z', z)
        
        # Dispatch
        group_x = math.ceil(width / 16)
        group_y = math.ceil(height / 16)
        gpu.compute.dispatch(shader, group_x, group_y, 1)

    def _register_viewer_handlers(self, graph, texture_map):
        """Register GPU-only draw handlers for viewer nodes."""
        from ..nodes.viewer import register_viewer_handler
        
        for output_name, viewer_info in graph.viewer_outputs.items():
            node = viewer_info['node']
            resource_idx = viewer_info['resource_index']
            
            viewer_id = node.get_viewer_id()
            
            # The texture is already in the texture_manager's cache
            # Register draw handler with texture reference
            register_viewer_handler(
                viewer_id,
                self.texture_mgr,
                output_name,
                node
            )
            
            logger.debug(f"Registered viewer handler for {output_name}")

