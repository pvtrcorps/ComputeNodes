"""
LoopExecutor - GLSL-First Loop Execution with Explicit Texture Copies.

This module implements the GLSL-native pattern for multi-pass loops:
- Dedicated read/write buffers (never share the same GPUTexture)
- Explicit copies between IMAGE and SAMPLER usage
- Proper ping-pong with memory barriers

Key Principle:
    In pure GLSL, you NEVER bind the same texture as IMAGE (for writes)
    and then as SAMPLER (for reads) across passes. This causes undefined
    behavior on many GPU drivers. Instead, we:
    1. Use separate textures for reading and writing
    2. Copy data explicitly between them
    3. Issue memory barriers after each copy

Architecture:
    ┌───────────────────────────────────────────────────────────┐
    │  Pre-Loop: Write initial values to internal buffers       │
    │  Pass 101_1: imageStore(initial_A, red)                   │
    └───────────────────────────────────────────────────────────┘
                              ↓ COPY
    ┌───────────────────────────────────────────────────────────┐
    │  Loop Setup: Copy initial → dedicated ping buffer         │
    │  gpu_ops.copy_texture(initial_A → A.ping)                 │
    └───────────────────────────────────────────────────────────┘
                              ↓
    ┌───────────────────────────────────────────────────────────┐
    │  Iteration 0: Read=ping, Write=pong                       │
    │  Iteration 1: Read=pong, Write=ping                       │
    │  (Each iteration gets clean read from previous write)     │
    └───────────────────────────────────────────────────────────┘
                              ↓
    ┌───────────────────────────────────────────────────────────┐
    │  Finalize: Copy final buffer → output                     │
    └───────────────────────────────────────────────────────────┘
"""

import logging
from typing import Dict, Any, Optional, Tuple
import gpu

from ..planner.loops import PassLoop
from ..ir.resources import ImageDesc
from .pass_runner import PassRunner
from .execution_state import ExecutionState

logger = logging.getLogger(__name__)


class LoopExecutor:
    """
    Executes multi-pass loops using GLSL-native texture handling.
    
    Ensures proper GPU state by:
    - Never sharing texture objects between IMAGE and SAMPLER bindings
    - Using explicit copies between passes
    - Maintaining clean ping-pong buffer separation
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
        Execute a complete loop with GLSL-first texture handling.
        
        Args:
            graph: IR Graph containing resources
            loop: PassLoop definition with state_vars and body_passes
            texture_map: Dict mapping resource index -> GPU texture
            state: ExecutionState to update with final sizes
            context_width: Default width for new textures
            context_height: Default height for new textures
        """
        iterations = self._resolve_iterations(loop)
        logger.info(f"Loop: {iterations} iterations, {len(loop.state_vars)} states")
        
        # Phase 1: Create dedicated ping/pong buffers and copy initial data
        ping_pong = self._create_dedicated_buffers(loop, texture_map, graph)
        
        # Phase 2: Get dynamic resources for iteration-specific size evaluation
        dynamic_resources = self.resolver.get_dynamic_resources()
        
        # Phase 3: Execute all iterations
        for iter_idx in range(iterations):
            self._execute_iteration(
                graph, loop, iter_idx, iterations,
                texture_map, ping_pong, dynamic_resources,
                state, context_width, context_height
            )
        
        # Phase 4: Finalize - update texture_map and state with final buffers
        self._finalize_loop(graph, loop, texture_map, ping_pong, iterations, state)
        
        logger.info(f"Loop completed: {iterations} iterations")
    
    def _resolve_iterations(self, loop: PassLoop) -> int:
        """Resolve iteration count from loop definition."""
        iterations = loop.iterations
        if hasattr(iterations, 'constant_value'):
            return int(iterations.constant_value)
        elif not isinstance(iterations, int):
            return 10  # Default fallback
        return int(iterations)
    
    def _create_dedicated_buffers(self, loop: PassLoop, texture_map: dict, 
                                   graph) -> Dict[int, dict]:
        """
        Create DEDICATED ping/pong buffers for each state.
        
        CRITICAL: We create NEW textures, NOT references to existing ones.
        Then we COPY initial data into the ping buffer.
        
        This ensures:
        - Initial texture (used as IMAGE in pre-loop) stays separate
        - Ping buffer (used as SAMPLER in loop) has its own GPU state
        """
        ping_pong = {}
        
        for state in loop.state_vars:
            # Get initial value info
            init_idx = None
            init_tex = None
            
            if state.initial_value is not None:
                init_idx = getattr(state.initial_value, 'resource_index', None)
                if init_idx is not None and init_idx in texture_map:
                    init_tex = texture_map[init_idx]
            
            # Determine buffer size from initial texture or state definition
            if init_tex is not None:
                width, height = init_tex.width, init_tex.height
                fmt = getattr(graph.resources[init_idx], 'format', 'RGBA32F')
            else:
                width, height = state.size if state.size else (512, 512)
                fmt = 'RGBA32F'
            
            # Create FRESH ping buffer (never shared with initial texture)
            ping_tex = gpu.types.GPUTexture(
                size=(width, height),
                format=fmt
            )
            
            # Create FRESH pong buffer
            pong_tex = gpu.types.GPUTexture(
                size=(width, height),
                format=fmt
            )
            
            # CRITICAL: Copy initial data into ping buffer
            if init_tex is not None:
                logger.debug(f"State '{state.name}': copying initial data {width}x{height}")
                self.gpu_ops.copy_texture(init_tex, ping_tex, format=fmt)
            
            # Update texture_map with our dedicated buffers
            texture_map[state.ping_idx] = ping_tex
            texture_map[state.pong_idx] = pong_tex
            
            ping_pong[state.index] = {
                'ping': ping_tex,
                'pong': pong_tex,
                'ping_idx': state.ping_idx,
                'pong_idx': state.pong_idx,
                'state': state,
                'current_size': (width, height),
                'format': fmt
            }
            
            logger.debug(f"State '{state.name}': ping[{state.ping_idx}]={width}x{height}, "
                        f"pong[{state.pong_idx}]={width}x{height}")
        
        # Memory barrier after all initial copies
        self.gpu_ops.memory_barrier()
        
        return ping_pong
    
    def _execute_iteration(self, graph, loop: PassLoop, iter_idx: int,
                           total_iterations: int, texture_map: dict,
                           ping_pong: dict, dynamic_resources: dict,
                           state: ExecutionState, 
                           context_width: int, context_height: int) -> None:
        """
        Execute a single loop iteration.
        
        Ping-Pong Pattern:
        - Even iterations (0, 2, 4...): Read from PING, write to PONG
        - Odd iterations (1, 3, 5...): Read from PONG, write to PING
        """
        # Set up buffer roles for this iteration
        self._swap_buffers(iter_idx, ping_pong, texture_map)
        
        # Evaluate and apply dynamic sizes for this iteration
        self._evaluate_dynamic_sizes(
            graph, loop, texture_map, dynamic_resources, 
            state, context_width, context_height,
            current_iteration=iter_idx
        )


        # Execute body passes
        for body_pass in loop.body_passes:
            # Set loop iteration uniform
            body_pass.loop_iteration = iter_idx
            
            # Handle nested loops recursively
            if hasattr(body_pass, 'body_passes'):
                self.execute(
                    graph, body_pass, texture_map, state,
                    context_width, context_height
                )
            else:
                self.pass_runner.run(
                    graph, body_pass, texture_map,
                    context_width, context_height
                )
        
        # After body execution: copy results to appropriate buffers
        self._handle_state_copies(iter_idx, loop, texture_map, ping_pong)
    
    def _swap_buffers(self, iter_idx: int, ping_pong: dict, 
                      texture_map: dict) -> None:
        """
        Configure texture_map for correct read/write roles this iteration.
        
        This sets up which buffer the shader will READ from (as sampler)
        and which it will WRITE to (as image).
        """
        for buf_info in ping_pong.values():
            ping_idx = buf_info['ping_idx']
            pong_idx = buf_info['pong_idx']
            
            if iter_idx % 2 == 0:
                # Even: Read from ping, write to pong
                texture_map[ping_idx] = buf_info['ping']
                texture_map[pong_idx] = buf_info['pong']
            else:
                # Odd: Read from pong, write to ping
                texture_map[ping_idx] = buf_info['pong']
                texture_map[pong_idx] = buf_info['ping']
    
    def _handle_state_copies(self, iter_idx: int, loop: PassLoop,
                             texture_map: dict, ping_pong: dict) -> None:
        """
        Copy loop body outputs (e.g., Capture.002) to the write buffer.
        
        This ensures the next iteration reads the correct data.
        Also handles size changes when the capture has different resolution.
        """
        for state_idx, buf_info in ping_pong.items():
            state = buf_info['state']
            copy_from_idx = getattr(state, 'copy_from_resource', None)
            
            if copy_from_idx is None:
                continue
            
            # Source: what the loop body wrote to
            src_tex = texture_map.get(copy_from_idx)
            if src_tex is None:
                continue
            
            src_size = (src_tex.width, src_tex.height)
            current_size = buf_info['current_size']
            fmt = buf_info['format']
            
            # Determine destination buffer (the one we're writing to this iter)
            if iter_idx % 2 == 0:
                dst_key = 'pong'
            else:
                dst_key = 'ping'
            
            dst_tex = buf_info[dst_key]
            
            # Handle size change: resize only the DESTINATION buffer
            # The other buffer will be resized when it becomes the destination
            if src_size != (dst_tex.width, dst_tex.height):
                logger.debug(f"State '{state.name}': resize {dst_key} {(dst_tex.width, dst_tex.height)} -> {src_size}")
                
                # Create new destination buffer at correct size
                new_dst = gpu.types.GPUTexture(
                    size=src_size,
                    format=fmt
                )
                
                # Update only the destination
                buf_info[dst_key] = new_dst
                dst_tex = new_dst
                
                # Update texture_map for destination
                dst_idx = buf_info['pong_idx'] if dst_key == 'pong' else buf_info['ping_idx']
                texture_map[dst_idx] = new_dst
                
                # Update current_size
                buf_info['current_size'] = src_size
            
            # EXPLICIT COPY: source -> destination
            self.gpu_ops.copy_texture(src_tex, dst_tex, format=fmt)
        
        # Memory barrier after all copies
        self.gpu_ops.memory_barrier()
    
    def _evaluate_dynamic_sizes(self, graph, loop: PassLoop, texture_map: dict,
                                 dynamic_resources: dict, state: ExecutionState,
                                 context_width: int, context_height: int,
                                 current_iteration: int = 0) -> None:
        """
        Evaluate and allocate dynamic-sized resources for this iteration.
        
        For loop body resources with dynamic sizes, we MUST re-evaluate
        on each iteration because the size may depend on the iteration index.
        """
        for res_idx, res in dynamic_resources.items():
            # Skip resources not relevant to this loop
            if not getattr(res, 'loop_body_resource', False):
                continue
            
            # Evaluate size expression with CURRENT iteration
            width, height = self.resolver.evaluate_dynamic_size(
                res, current_iteration, context_width, context_height,
                texture_map=texture_map
            )
            depth = 1  # 2D textures for now
            
            # Check if we need to (re)allocate
            existing_tex = texture_map.get(res_idx)
            needs_alloc = (existing_tex is None or
                          existing_tex.width != width or
                          existing_tex.height != height)
            
            if needs_alloc:
                # Create texture at evaluated size
                tex = gpu.types.GPUTexture(
                    size=(width, height) if depth == 1 else (width, height, depth),
                    format=getattr(res, 'format', 'RGBA32F')
                )
                texture_map[res_idx] = tex
                
                # Update state
                state.update_size(res_idx, width, height, depth)
                
                logger.debug(f"Dynamic resource [{res_idx}] '{res.name}': {width}x{height} (iter {current_iteration})")
    
    def _finalize_loop(self, graph, loop: PassLoop, texture_map: dict,
                       ping_pong: dict, iterations: int,
                       state: ExecutionState) -> None:
        """
        Finalize loop: set up final buffers for post-loop passes.
        
        After N iterations:
        - The last iteration wrote to the "write" buffer
        - For even iters (0,2,4): last write was to pong
        - For odd iters (1,3): last write was to ping
        
        But since _handle_state_copies ran AFTER writing, the data is in:
        - Even iters: pong (we copied src -> pong)
        - Odd iters: ping (we copied src -> ping)
        """
        for buf_info in ping_pong.values():
            state_var = buf_info['state']
            
            # The final buffer is where we last copied data TO
            # After iter N-1, we copied to the "dst" buffer for that iteration
            # iter 0: dst=pong, iter 1: dst=ping, iter 2: dst=pong, iter 3: dst=ping
            # So for iterations=4 (iters 0,1,2,3), last was iter 3 which wrote to ping
            last_iter = iterations - 1
            if last_iter % 2 == 0:
                final_buf = buf_info['pong']
            else:
                final_buf = buf_info['ping']
            
            final_size = (final_buf.width, final_buf.height)
            
            # Update texture_map - both ping and pong point to final
            texture_map[buf_info['ping_idx']] = final_buf
            texture_map[buf_info['pong_idx']] = final_buf
            
            # Update ExecutionState with final size
            state.update_size(buf_info['ping_idx'], final_size[0], final_size[1], 1)
            state.update_size(buf_info['pong_idx'], final_size[0], final_size[1], 1)
            
            logger.debug(f"Loop end: state '{state_var.name}' final={final_size[0]}x{final_size[1]}")
            logger.debug(f"Loop end: state '{state_var.name}' final={final_size[0]}x{final_size[1]}")
        
        # Resize external outputs to match loop states
        self._resize_outputs(graph, texture_map, ping_pong, state)
    
    def _resize_outputs(self, graph, texture_map: dict, ping_pong: dict,
                        state: ExecutionState) -> None:
        """Resize external outputs to match their source state sizes."""
        pong_indices = {buf_info['pong_idx']: buf_info for buf_info in ping_pong.values()}
        
        for idx, res in enumerate(graph.resources):
            if getattr(res, 'is_internal', True):
                continue
            
            # Check if this output depends on a loop state
            size_expr = getattr(res, 'size_expression', None)
            if size_expr is None:
                continue
            
            source_idx = getattr(size_expr, 'source_resource', None)
            if source_idx is None or source_idx not in pong_indices:
                continue
            
            # Get final size from the source state
            buf_info = pong_indices[source_idx]
            final_size = buf_info['current_size']
            
            # Resize output texture if needed
            old_tex = texture_map.get(idx)
            if old_tex is None:
                continue
            
            old_size = (old_tex.width, old_tex.height)
            if old_size == final_size:
                continue
            
            # Create new texture at correct size
            new_tex = gpu.types.GPUTexture(
                size=final_size,
                format=getattr(res, 'format', 'RGBA32F')
            )
            texture_map[idx] = new_tex
            state.update_size(idx, final_size[0], final_size[1], 1)
            
            logger.debug(f"Output [{idx}] resized: {old_size} -> {final_size}")
