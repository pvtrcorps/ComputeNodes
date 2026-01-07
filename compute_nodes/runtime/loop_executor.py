"""
LoopExecutor - Executes Repeat Zones with ping-pong buffering.

This module extracts the loop execution logic from the monolithic
ComputeExecutor, providing cleaner separation of concerns.

Key Concepts:
    Ping-Pong Buffering: When a shader reads AND writes the same resource,
    we use two buffers and alternate between them:
    - Iteration 0: Read from PING, write to PONG
    - Iteration 1: Read from PONG, write to PING
    - ...and so on

Responsibilities:
- Setup ping-pong buffers for Grid states
- Evaluate dynamic sizes per iteration
- Swap buffers between iterations
- Execute body passes via PassRunner
- Resize outputs to match final loop state sizes
"""

import logging
from typing import Dict, Any, Optional

from ..planner.loops import PassLoop
from ..ir.resources import ImageDesc
from .pass_runner import PassRunner
from .execution_state import ExecutionState

logger = logging.getLogger(__name__)


class LoopExecutor:
    """
    Executes multi-pass loops with automatic ping-pong buffering.
    
    Handles the complex logic of:
    - Buffer allocation and swapping
    - Dynamic size evaluation per iteration
    - State copying between iterations
    - Output resizing after loop completion
    
    Example:
        loop_exec = LoopExecutor(pass_runner, resolver, texture_mgr, gpu_ops)
        loop_exec.execute(graph, loop, texture_map, 512, 512)
    """
    
    def __init__(self, pass_runner: PassRunner, resolver, texture_mgr, gpu_ops):
        """
        Initialize LoopExecutor.
        
        Args:
            pass_runner: PassRunner for executing individual passes
            resolver: ResourceResolver for texture allocation
            texture_mgr: TextureManager for buffer management
            gpu_ops: GPUOps for copy_texture and memory_barrier
        """
        self.pass_runner = pass_runner
        self.resolver = resolver
        self.texture_mgr = texture_mgr
        self.gpu_ops = gpu_ops
    
    def execute(self, graph, loop: PassLoop, texture_map: dict,
                state: ExecutionState,
                context_width: int, context_height: int) -> None:
        """
        Execute a complete loop with all iterations.
        
        After execution, updates state.resource_sizes with final output sizes,
        enabling correct resolution of post-loop resources.
        
        Args:
            graph: IR Graph containing resources
            loop: PassLoop definition with state_vars and body_passes
            texture_map: Dict mapping resource index -> GPU texture
            state: ExecutionState to update with final sizes
            context_width: Default width for new textures
            context_height: Default height for new textures
        """
        iterations = self._resolve_iterations(loop)
        logger.info(f"Running loop: {iterations} iterations, {len(loop.state_vars)} state vars")
        
        # 1. Setup ping-pong buffers
        ping_pong = self._setup_ping_pong_buffers(
            loop, texture_map, context_width, context_height
        )
        
        # 2. Get dynamic resources for size evaluation
        dynamic_resources = self.resolver.get_dynamic_resources()
        
        # 3. Execute iterations
        for iter_idx in range(iterations):
            # Update state loop context
            state.set_loop_context(iter_idx, iterations)
            
            self._execute_iteration(
                graph, loop, iter_idx, iterations,
                texture_map, ping_pong, dynamic_resources,
                context_width, context_height
            )
        
        # 4. Finalize - assign final buffers, resize outputs, update state
        self._finalize_loop(graph, loop, iterations, texture_map, ping_pong, state)
        
        logger.info(f"Loop completed: {iterations} iterations")
    
    def _resolve_iterations(self, loop: PassLoop) -> int:
        """Resolve iteration count from loop definition."""
        iterations = loop.iterations
        if hasattr(iterations, 'constant_value'):
            return int(iterations.constant_value)
        elif not isinstance(iterations, int):
            return 10  # Default fallback
        return int(iterations)
    
    def _setup_ping_pong_buffers(self, loop: PassLoop, texture_map: dict,
                                  context_width: int, context_height: int) -> Dict[int, dict]:
        """
        Allocate and initialize ping-pong buffers for Grid states.
        
        Returns:
            Dict mapping state.index -> {ping, pong, ping_idx, pong_idx, state}
        """
        ping_pong = {}
        
        for state in loop.state_vars:
            if not (state.is_grid and state.ping_idx is not None and state.pong_idx is not None):
                continue
            
            fmt = getattr(state, 'format', 'RGBA32F')
            size = state.size if state.size != (0, 0, 0) else (context_width, context_height, 1)
            
            # Ensure ping buffer exists
            if state.ping_idx not in texture_map:
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
            
            # Ensure pong buffer exists
            if state.pong_idx not in texture_map:
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
            
            ping_pong[state.index] = {
                'ping': texture_map[state.ping_idx],
                'pong': texture_map[state.pong_idx],
                'ping_idx': state.ping_idx,
                'pong_idx': state.pong_idx,
                'state': state
            }
            
            # Map initial value to ping buffer
            if state.initial_value is not None and hasattr(state.initial_value, 'resource_index'):
                init_idx = state.initial_value.resource_index
                if init_idx is not None and init_idx in texture_map:
                    ping_pong[state.index]['original_ping'] = texture_map[state.ping_idx]
                    texture_map[state.ping_idx] = texture_map[init_idx]
                    ping_pong[state.index]['ping'] = texture_map[init_idx]
                    logger.info(f"Loop init: mapping ping[{state.ping_idx}] -> initial[{init_idx}]")
        
        return ping_pong
    
    def _execute_iteration(self, graph, loop: PassLoop, iter_idx: int, total_iterations: int,
                           texture_map: dict, ping_pong: dict, dynamic_resources: dict,
                           context_width: int, context_height: int) -> None:
        """Execute a single loop iteration."""
        
        # 1. Swap ping-pong buffers
        self._swap_buffers(iter_idx, ping_pong, texture_map)
        
        # 2. Update loop context for uniforms
        loop_context = self._build_loop_context(
            iter_idx, ping_pong, context_width, context_height
        )
        self.pass_runner.set_loop_context(**loop_context)
        
        # 3. Evaluate dynamic sizes
        self._evaluate_dynamic_sizes(
            iter_idx, dynamic_resources, texture_map, context_width, context_height
        )
        
        # 4. Execute body passes
        for body_pass in loop.body_passes:
            if hasattr(body_pass, 'body_passes'):
                # Nested loop - recursive call
                self.execute(graph, body_pass, texture_map, context_width, context_height)
            else:
                self.pass_runner.run(graph, body_pass, texture_map, context_width, context_height)
        
        # 5. Handle copy-back and state resizing
        self._handle_state_copies(iter_idx, loop, texture_map, ping_pong, dynamic_resources)
        
        # 6. Memory barrier
        self.gpu_ops.memory_barrier()
    
    def _swap_buffers(self, iter_idx: int, ping_pong: dict, texture_map: dict) -> None:
        """Swap ping-pong buffers based on iteration parity."""
        for buf_info in ping_pong.values():
            if iter_idx % 2 == 0:
                texture_map[buf_info['ping_idx']] = buf_info['ping']
                texture_map[buf_info['pong_idx']] = buf_info['pong']
            else:
                texture_map[buf_info['ping_idx']] = buf_info['pong']
                texture_map[buf_info['pong_idx']] = buf_info['ping']
    
    def _build_loop_context(self, iter_idx: int, ping_pong: dict,
                            context_width: int, context_height: int) -> dict:
        """Build loop context dict for shader uniforms."""
        if not ping_pong:
            return {
                'iteration': iter_idx,
                'read_width': context_width,
                'read_height': context_height,
                'write_width': context_width,
                'write_height': context_height,
            }
        
        first_state_idx = next(iter(ping_pong.keys()))
        buf_info = ping_pong[first_state_idx]
        
        if iter_idx % 2 == 0:
            read_buf = buf_info['ping']
            write_buf = buf_info['pong']
        else:
            read_buf = buf_info['pong']
            write_buf = buf_info['ping']
        
        return {
            'iteration': iter_idx,
            'read_width': read_buf.width if read_buf else 0,
            'read_height': read_buf.height if read_buf else 0,
            'write_width': write_buf.width if write_buf else 0,
            'write_height': write_buf.height if write_buf else 0,
        }
    
    def _evaluate_dynamic_sizes(self, iter_idx: int, dynamic_resources: dict,
                                 texture_map: dict, context_width: int, 
                                 context_height: int) -> None:
        """Evaluate and apply dynamic resource sizes for current iteration."""
        for res_idx, res_desc in dynamic_resources.items():
            # Skip resources that are pending allocation (not in texture_map yet)
            if res_idx not in texture_map:
                continue
            
            size_expr = getattr(res_desc, 'size_expression', {})
            if not size_expr:
                continue
            
            new_size = self.resolver.evaluate_dynamic_size(
                res_desc, iter_idx, context_width, context_height
            )
            current_size = (texture_map[res_idx].width, texture_map[res_idx].height)
            
            if new_size != current_size:
                logger.info(f"Dynamic resize (iter {iter_idx}): {res_desc.name} {current_size} -> {new_size}")
                new_tex = self.resolver.dynamic_pool.get_or_create(
                    new_size, res_desc.format, res_desc.dimensions
                )
                texture_map[res_idx] = new_tex
                self.resolver.update_grid_size(res_idx, new_size[0], new_size[1])
    
    def _handle_state_copies(self, iter_idx: int, loop: PassLoop,
                              texture_map: dict, ping_pong: dict,
                              dynamic_resources: dict) -> None:
        """Handle copy-back operations and resize states if needed."""
        for state in loop.state_vars:
            if not hasattr(state, 'copy_from_resource') or state.copy_from_resource is None:
                continue
            
            src_idx = state.copy_from_resource
            if src_idx not in texture_map:
                continue
            
            src_tex = texture_map[src_idx]
            src_size = (src_tex.width, src_tex.height)
            
            # Determine current destination buffer
            dst_key = 'pong' if iter_idx % 2 == 0 else 'ping'
            dst = ping_pong[state.index][dst_key]
            dst_size = (dst.width, dst.height)
            
            # Check if resize needed
            if src_idx in dynamic_resources or src_size != dst_size:
                if src_size != dst_size:
                    logger.info(f"Dynamic state resize: {state.name} {dst_size} -> {src_size}")
                    fmt = getattr(state, 'format', 'RGBA32F')
                    new_buf = self.resolver.dynamic_pool.get_or_create(
                        src_size, fmt, state.dimensions
                    )
                    ping_pong[state.index][dst_key] = new_buf
                    dst = new_buf
            
            # Copy texture
            fmt = getattr(state, 'format', 'RGBA32F')
            self.gpu_ops.copy_texture(src_tex, dst, format=fmt, dimensions=state.dimensions)
    
    def _finalize_loop(self, graph, loop: PassLoop, iterations: int,
                        texture_map: dict, ping_pong: dict,
                        state: ExecutionState) -> None:
        """Finalize loop: assign final buffers, resize outputs, update state."""
        pong_to_size = {}
        
        # Assign final buffers
        for buf_info in ping_pong.values():
            state_var = buf_info['state']
            
            copy_from = getattr(state_var, 'copy_from_resource', None)
            if copy_from is not None and copy_from in texture_map:
                final_buf = texture_map[copy_from]
            else:
                if iterations % 2 == 1:
                    final_buf = buf_info['pong']
                else:
                    final_buf = buf_info['ping']
            
            # Update both indices to point to final buffer
            texture_map[buf_info['ping_idx']] = final_buf
            texture_map[buf_info['pong_idx']] = final_buf
            pong_to_size[buf_info['pong_idx']] = (final_buf.width, final_buf.height)
            
            # UPDATE ExecutionState with final size
            # This is the critical update that enables post-loop resource resolution
            state.update_size(buf_info['ping_idx'], final_buf.width, final_buf.height, 1)
            state.update_size(buf_info['pong_idx'], final_buf.width, final_buf.height, 1)
            
            logger.debug(f"Loop end: state {state_var.name} final size {final_buf.width}x{final_buf.height}")
        
        # Resize outputs to match loop states
        self._resize_outputs(graph, texture_map, pong_to_size)
    
    def _resize_outputs(self, graph, texture_map: dict, pong_to_size: dict) -> None:
        """Resize external outputs to match their source state sizes."""
        pong_indices = sorted(pong_to_size.keys())
        output_indices = sorted([
            idx for idx, res in enumerate(graph.resources)
            if hasattr(res, 'is_internal') and not res.is_internal
        ])
        
        for pong_idx, output_idx in zip(pong_indices, output_indices):
            pong_size = pong_to_size[pong_idx]
            if output_idx in texture_map:
                current = texture_map[output_idx]
                if (current.width, current.height) != pong_size:
                    res_desc = graph.resources[output_idx]
                    new_tex = self.resolver.dynamic_pool.get_or_create(
                        pong_size, 'RGBA32F', getattr(res_desc, 'dimensions', 2)
                    )
                    texture_map[output_idx] = new_tex
                    logger.info(f"Resized output[{output_idx}] to {pong_size} to match loop state")
