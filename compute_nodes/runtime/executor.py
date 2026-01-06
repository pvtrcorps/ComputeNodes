"""
ComputeExecutor for Compute Nodes runtime.

Orchestrates the execution of compute graphs:
- Resolves resources to GPU textures (Delegated to ResourceResolver)
- Binds shaders and dispatches compute work
- Handles readback to Blender Image datablocks (Delegated to ResourceResolver)
- Manages multi-pass loops with ping-pong buffering
"""

import logging
import math
import time
import gpu

# Components
from .textures import TextureManager
from .shaders import ShaderManager
from .gpu_ops import GPUOps
from .resource_resolver import ResourceResolver
from .sequence_exporter import SequenceExporter
from ..planner.passes import ComputePass
from ..planner.loops import PassLoop
from ..ir.resources import ImageDesc

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """
    Orchestrates the execution of a compute graph.
    
    Binds resources, sets uniforms, and dispatches compute shaders.
    Handles multi-pass loops with automatic ping-pong buffering.
    Delegates specialized tasks to sub-components.
    """
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        
        # Sub-components
        self.gpu_ops = GPUOps()
        self.resolver = ResourceResolver(texture_mgr)
        self.sequence_exporter = SequenceExporter()
        
        # Loop context for shader uniforms (set by _run_pass_loop)
        self._loop_context = {
            'iteration': 0,
            'read_width': 0,
            'read_height': 0,
            'write_width': 0,
            'write_height': 0,
        }

    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """Execute the entire graph by running passes in order."""
        
        # Phase 1: Resolve Resources
        texture_map = self.resolver.resolve_resources(graph, context_width, context_height)
        
        # Phase 2: Execute Passes (handles both ComputePass and PassLoop)
        for item in passes:
            # Robust check for Loop (handles reloading class mismatch)
            if 'PassLoop' in str(type(item)) or hasattr(item, 'body_passes'):
                self._run_pass_loop(graph, item, texture_map, context_width, context_height)
            else:
                self._run_pass(graph, item, texture_map, context_width, context_height)

        # Phase 3: Readback results to Blender Images
        self.resolver.readback_results(graph, texture_map)
        
        # Phase 4: Write sequence outputs (Grid3D -> Z-slice files)
        if hasattr(graph, 'sequence_outputs') and graph.sequence_outputs:
            self.sequence_exporter.write_sequence_outputs(graph, texture_map)
        
        # Phase 5: Register GPU-only viewer draw handlers
        if hasattr(graph, 'viewer_outputs') and graph.viewer_outputs:
            self._register_viewer_handlers(graph, texture_map)
        
        # Phase 6: Release all dynamic pool textures for reuse
        self.resolver.cleanup()
        logger.debug("Released all dynamic pool textures")

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
        
        if dispatch_w == 0: dispatch_w = context_width
        if dispatch_h == 0: dispatch_h = context_height
        if dispatch_d == 0: dispatch_d = 1
        
        # DYNAMIC SIZING Logic: Write Size is King.
        max_size = (0, 0)
        has_writes = False
        
        # 1. Determine Write Area (Primary driver)
        for idx in compute_pass.writes_idx:
            if idx in texture_map:
                tex = texture_map[idx]
                max_size = (max(max_size[0], tex.width), max(max_size[1], tex.height))
                has_writes = True
        
        # Apply override if valid write size found
        if has_writes and max_size != (0,0):
             dispatch_w, dispatch_h = max_size
        
        # Apply override if found larger textures but didn't write? (Fallback logic kept same)
        if max_size != (0,0) and max_size != (dispatch_w, dispatch_h):
            dispatch_w, dispatch_h = max_size
            
        # Workgroup size based on DISPATCH dimensions (must match shader's local_group_size)
        if dispatch_d > 1:
            local_x, local_y, local_z = 8, 8, 8
        else:
            local_x, local_y, local_z = 16, 16, 1
            
        group_x = math.ceil(dispatch_w / local_x)
        group_y = math.ceil(dispatch_h / local_y)
        group_z = math.ceil(dispatch_d / local_z)
        
        logger.debug(f"Pass {compute_pass.id}: dispatch({dispatch_w}x{dispatch_h}x{dispatch_d}) -> groups({group_x}x{group_y}x{group_z})")
        
        # Set dispatch size uniforms for Position normalization
        try:
            shader.uniform_int("u_dispatch_width", dispatch_w)
            shader.uniform_int("u_dispatch_height", dispatch_h)
            shader.uniform_int("u_dispatch_depth", dispatch_d)
            
            # Loop context uniforms (set by _run_pass_loop each iteration)
            shader.uniform_int("u_loop_iteration", self._loop_context['iteration'])
            shader.uniform_int("u_loop_read_width", self._loop_context['read_width'])
            shader.uniform_int("u_loop_read_height", self._loop_context['read_height'])
            shader.uniform_int("u_loop_write_width", self._loop_context['write_width'])
            shader.uniform_int("u_loop_write_height", self._loop_context['write_height'])
        except Exception as e:
            logger.debug(f"Could not set uniforms: {e}")
        
        # PROFILING: Start Timer
        should_profile = getattr(graph, 'profile_execution', False)
        start_time = 0.0
        
        if should_profile:
            self.gpu_ops.gl_finish() # Ensure previous work is done
            start_time = time.perf_counter()

        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Dispatch failed: {e}")
            
        # PROFILING: Stop Timer
        if should_profile:
            self.gpu_ops.gl_finish() # Ensure this dispatch is done
            end_time = time.perf_counter()
            elapsed_ms = (end_time - start_time) * 1000.0
            
            # Attribute time to participating nodes
            seen_nodes = set()
            for op in compute_pass.ops:
                if hasattr(op, 'origin') and op.origin:
                    node = op.origin
                    if hasattr(node, 'execution_time') and node not in seen_nodes:
                        node.execution_time = elapsed_ms
                        seen_nodes.add(node)
            if hasattr(graph, "execution_time_total"):
                graph.execution_time_total += elapsed_ms

        # Memory barrier
        self.gpu_ops.memory_barrier()

    def _run_pass_loop(self, graph, loop: PassLoop, texture_map, context_width, context_height):
        """
        Execute a multi-pass loop with ping-pong buffering.
        
        For each iteration:
        1. Swap ping-pong buffers for Grid state variables
        2. Execute all body passes
        3. Insert memory barrier
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
                
                # Initialize ping buffer (DIRECT MAP)
                if state.initial_value is not None and hasattr(state.initial_value, 'resource_index'):
                    init_idx = state.initial_value.resource_index
                    if init_idx is not None and init_idx in texture_map:
                        if 'original_ping' not in ping_pong_buffers[state.index]:
                            ping_pong_buffers[state.index]['original_ping'] = texture_map[state.ping_idx]
                        texture_map[state.ping_idx] = texture_map[init_idx]
                        ping_pong_buffers[state.index]['ping'] = texture_map[init_idx]
                        logger.info(f"Loop init: mapping ping[{state.ping_idx}] -> initial[{init_idx}]")
        
        # Execute iterations
        dynamic_resources = self.resolver.get_dynamic_resources()
        
        for iter_idx in range(iterations):
            # Swap ping-pong based on even/odd iteration
            for buf_info in ping_pong_buffers.values():
                if iter_idx % 2 == 0:
                    texture_map[buf_info['ping_idx']] = buf_info['ping']
                    texture_map[buf_info['pong_idx']] = buf_info['pong']
                else:
                    texture_map[buf_info['ping_idx']] = buf_info['pong']
                    texture_map[buf_info['pong_idx']] = buf_info['ping']
            
            # Update loop context variables
            if ping_pong_buffers:
                first_state_idx = next(iter(ping_pong_buffers.keys()))
                buf_info = ping_pong_buffers[first_state_idx]
                if iter_idx % 2 == 0:
                    read_buf = buf_info['ping']
                    write_buf = buf_info['pong']
                else:
                    read_buf = buf_info['pong']
                    write_buf = buf_info['ping']
                
                self._loop_context = {
                    'iteration': iter_idx,
                    'read_width': read_buf.width if read_buf else 0,
                    'read_height': read_buf.height if read_buf else 0,
                    'write_width': write_buf.width if write_buf else 0,
                    'write_height': write_buf.height if write_buf else 0,
                }
            else:
                self._loop_context = {
                    'iteration': iter_idx,
                    'read_width': context_width,
                    'read_height': context_height,
                    'write_width': context_width,
                    'write_height': context_height,
                }
            
            # Evaluate and apply dynamic resource sizes for CURRENT iteration
            # This must happen BEFORE body pass execution so shaders write to correct size
            for res_idx, res_desc in dynamic_resources.items():
                size_expr = getattr(res_desc, 'size_expression', {})
                if not size_expr:
                    continue
                
                new_size = self.resolver.evaluate_dynamic_size(res_desc, iter_idx, context_width, context_height)
                current_size = (texture_map[res_idx].width, texture_map[res_idx].height)
                
                if new_size != current_size:
                    logger.info(f"Dynamic resize (iter {iter_idx}): {res_desc.name} {current_size} -> {new_size}")
                    new_tex = self.resolver.dynamic_pool.get_or_create(new_size, res_desc.format, res_desc.dimensions)
                    texture_map[res_idx] = new_tex
                    # Update grid sizes for Grid Info support in ScalarEvaluator
                    self.resolver.update_grid_size(res_idx, new_size[0], new_size[1])
            
            # Execute body passes
            for body_pass in loop.body_passes:
                if 'PassLoop' in str(type(body_pass)) or hasattr(body_pass, 'body_passes'):
                    self._run_pass_loop(graph, body_pass, texture_map, context_width, context_height)
                else:
                    self._run_pass(graph, body_pass, texture_map, context_width, context_height)
            
            # Handle copy back (Blur etc.) and Resizing
            for state in loop.state_vars:
                if hasattr(state, 'copy_from_resource') and state.copy_from_resource is not None:
                    src_idx = state.copy_from_resource
                    
                    if src_idx not in texture_map:
                        continue
                    
                    src_tex = texture_map[src_idx]
                    src_size = (src_tex.width, src_tex.height)
                    
                    # Determine current destination buffer
                    dst_key = 'pong' if iter_idx % 2 == 0 else 'ping'
                    dst = ping_pong_buffers[state.index][dst_key]
                    dst_size = (dst.width, dst.height)
                    
                    # Check if source size changed (Dynamic Resize)
                    if src_idx in dynamic_resources or src_size != dst_size:
                        if src_size != dst_size:
                            logger.info(f"Dynamic state resize: {state.name} {dst_size} -> {src_size}")
                            
                            # Get new buffer from dynamic pool (Accessed via resolver)
                            fmt = getattr(state, 'format', 'RGBA32F')
                            new_buf = self.resolver.dynamic_pool.get_or_create(
                                src_size, fmt, state.dimensions
                            )
                            ping_pong_buffers[state.index][dst_key] = new_buf
                            dst = new_buf
                    
                    # Copy
                    fmt = getattr(state, 'format', 'RGBA32F')
                    self.gpu_ops.copy_texture(src_tex, dst, format=fmt, dimensions=state.dimensions)
            
            self.gpu_ops.memory_barrier()
        
        # After loop: Final output - point ping/pong to the correct source textures
        # Also build mapping of pong_idx -> final_size for output resizing
        pong_to_size = {}
        for buf_info in ping_pong_buffers.values():
            state = buf_info['state']
            
            copy_from = getattr(state, 'copy_from_resource', None)
            if copy_from is not None and copy_from in texture_map:
                final_buf = texture_map[copy_from]
            else:
                if iterations % 2 == 1:
                    final_buf = buf_info['pong']
                else:
                    final_buf = buf_info['ping']
            
            # Update both ping and pong to point to the state's final buffer
            # This allows subsequent passes to read from the correct sized texture
            texture_map[buf_info['ping_idx']] = final_buf
            texture_map[buf_info['pong_idx']] = final_buf
            pong_to_size[buf_info['pong_idx']] = (final_buf.width, final_buf.height)
            logger.debug(f"Loop end: state {state.name} final size {final_buf.width}x{final_buf.height}")
        
        # Resize outputs that read from loop states to match their source sizes
        # Find outputs (non-internal resources) and resize them to match their source pong
        for idx, res_desc in enumerate(graph.resources):
            if hasattr(res_desc, 'is_internal') and not res_desc.is_internal:
                # Find which pong this output corresponds to - check if it's connected to a loop state
                # For now, iterate pong indices and find matching output by position
                # This works because the final pass reads/writes are ordered consistently
                pass
        
        # For each pong_idx, find the corresponding output in texture_map and resize
        # The mapping is: sorted(pong_indices) -> sorted(output_indices)
        pong_indices = sorted(pong_to_size.keys())
        output_indices = sorted([idx for idx, res in enumerate(graph.resources) 
                                  if hasattr(res, 'is_internal') and not res.is_internal])
        
        for pong_idx, output_idx in zip(pong_indices, output_indices):
            pong_size = pong_to_size[pong_idx]
            if output_idx in texture_map:
                current = texture_map[output_idx]
                if (current.width, current.height) != pong_size:
                    # Resize output to match source size
                    res_desc = graph.resources[output_idx]
                    new_tex = self.resolver.dynamic_pool.get_or_create(
                        pong_size, 'RGBA32F', getattr(res_desc, 'dimensions', 2)
                    )
                    texture_map[output_idx] = new_tex
                    logger.info(f"Resized output[{output_idx}] to {pong_size} to match loop state")
        
        logger.info(f"Loop completed: {iterations} iterations")


    def _register_viewer_handlers(self, graph, texture_map):
        """Register GPU-only draw handlers for viewer nodes."""
        from ..nodes.viewer import register_viewer_handler
        
        for output_name, viewer_info in graph.viewer_outputs.items():
            node = viewer_info['node']
            
            viewer_id = node.get_viewer_id()
            register_viewer_handler(
                viewer_id,
                self.texture_mgr,
                output_name,
                node
            )
