"""
ComputeExecutor for Compute Nodes runtime.

Orchestrates the execution of compute graphs using phased resource resolution:
- Phase 0: Resolve STATIC resources (known sizes)
- Phase 1: Execute loops (updating ExecutionState with final sizes)
- Phase 2: Resolve PENDING resources (using updated sizes from loops)
- Phase 3: Execute post-loop passes
- Phase 4+: Readback, sequence export, cleanup

Components:
- PassRunner: Executes individual compute passes
- LoopExecutor: Handles multi-pass loops with ping-pong buffering
- ResourceResolver: Phased resource resolution
- SequenceExporter: Exports Grid3D to Z-slice sequences
"""

import logging
from typing import List, Tuple

# Components
from .textures import TextureManager
from .shaders import ShaderManager
from .gpu_ops import GPUOps
from .resource_resolver import ResourceResolver
from .execution_state import ExecutionState
from .sequence_exporter import SequenceExporter
from .pass_runner import PassRunner
from .loop_executor import LoopExecutor
from ..planner.passes import ComputePass
from ..planner.loops import PassLoop

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """
    Orchestrates the execution of a compute graph with phased resource resolution.
    
    The executor separates passes into two groups:
    1. Loop passes - Executed first, may change resource sizes
    2. Post-loop passes - Executed after pending resources are resolved
    
    This ensures resources that depend on loop outputs get correct sizes.
    """
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        
        # Core GPU operations
        self.gpu_ops = GPUOps()
        
        # Resource management
        self.resolver = ResourceResolver(texture_mgr)
        
        # Pass execution
        self.pass_runner = PassRunner(shader_mgr, self.gpu_ops)
        self.loop_executor = LoopExecutor(
            self.pass_runner, 
            self.resolver, 
            texture_mgr, 
            self.gpu_ops
        )
        
        # Sequence export
        self.sequence_exporter = SequenceExporter()
        
        # Execution state
        self._state = None

    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """
        Execute the entire graph by running passes in phases.
        
        Phased Execution:
        - Phase 0: Resolve static resources
        - Phase 1: Execute loops (updates ExecutionState)
        - Phase 2: Resolve pending resources (uses updated sizes)
        - Phase 3: Execute post-loop passes
        - Phase 4+: Readback, cleanup
        
        Args:
            graph: IR Graph with resources and ops
            passes: List of ComputePass and PassLoop items
            context_width: Default width for unspecified resources
            context_height: Default height for unspecified resources
        """
        # Create execution state
        self._state = ExecutionState(
            context_width=context_width,
            context_height=context_height
        )
        
        # Partition passes into pre-loop, loops, and post-loop
        pre_loop_passes, loop_passes, post_loop_passes = self._partition_passes(passes)
        
        # Phase 0: Resolve STATIC resources
        texture_map = self.resolver.resolve_static(graph, self._state)
        logger.debug(f"Phase 0: {len(texture_map)} static resources resolved")
        
        # Phase 0.5: Execute PRE-LOOP passes (independent of loop outputs)
        for pass_ in pre_loop_passes:
            self.pass_runner.run(
                graph, pass_, texture_map, context_width, context_height
            )
        
        # Phase 1: Execute LOOP passes
        # Loops update self._state.resource_sizes with final output sizes
        for loop_pass in loop_passes:
            self.loop_executor.execute(
                graph, loop_pass, texture_map, 
                self._state,  # Pass state for updates
                context_width, context_height
            )
        
        # Phase 2: Resolve PENDING resources using updated state
        if self.resolver.get_pending_resources():
            texture_map = self.resolver.resolve_pending(graph, self._state, texture_map)
            logger.debug(f"Phase 2: Pending resources resolved with post-loop sizes")
        
        # Phase 3: Execute POST-LOOP passes
        for pass_ in post_loop_passes:
            self.pass_runner.run(
                graph, pass_, texture_map, context_width, context_height
            )
        
        # Phase 4: Readback results to Blender Images
        self.resolver.readback_results(graph, texture_map)
        
        # Phase 5: Write sequence outputs (Grid3D -> Z-slice files)
        if hasattr(graph, 'sequence_outputs') and graph.sequence_outputs:
            self.sequence_exporter.write_sequence_outputs(graph, texture_map)
        
        # Phase 6: Register GPU-only viewer draw handlers
        if hasattr(graph, 'viewer_outputs') and graph.viewer_outputs:
            self._register_viewer_handlers(graph, texture_map)
        
        # Phase 7: Release all dynamic pool textures for reuse
        self.resolver.cleanup()
        logger.debug("Graph execution completed")
    
    def _partition_passes(self, passes) -> Tuple[List, List, List]:
        """
        Partition passes into pre-loop, loops, and post-loop.
        
        This preserves execution order while enabling phased resource resolution:
        - Pre-loop passes: Can be resolved and executed immediately
        - Loops: Executed, updating ExecutionState with final sizes
        - Post-loop passes: Resolved with correct sizes, then executed
        
        Returns:
            Tuple of (pre_loop_passes, loop_passes, post_loop_passes)
        """
        pre_loop_passes = []
        loop_passes = []
        post_loop_passes = []
        loop_seen = False
        
        for item in passes:
            is_loop = 'PassLoop' in str(type(item)) or hasattr(item, 'body_passes')
            
            if is_loop:
                loop_passes.append(item)
                loop_seen = True
            elif loop_seen:
                post_loop_passes.append(item)
            else:
                pre_loop_passes.append(item)
        
        logger.debug(f"Partitioned: {len(pre_loop_passes)} pre-loop, {len(loop_passes)} loops, {len(post_loop_passes)} post-loop")
        return pre_loop_passes, loop_passes, post_loop_passes

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
