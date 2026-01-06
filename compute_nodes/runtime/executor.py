"""
ComputeExecutor for Compute Nodes runtime.

Orchestrates the execution of compute graphs by delegating to specialized
components:
- PassRunner: Executes individual compute passes
- LoopExecutor: Handles multi-pass loops with ping-pong buffering
- ResourceResolver: Resolves resources to GPU textures
- SequenceExporter: Exports Grid3D to Z-slice sequences
"""

import logging

# Components
from .textures import TextureManager
from .shaders import ShaderManager
from .gpu_ops import GPUOps
from .resource_resolver import ResourceResolver
from .sequence_exporter import SequenceExporter
from .pass_runner import PassRunner
from .loop_executor import LoopExecutor
from ..planner.passes import ComputePass
from ..planner.loops import PassLoop

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """
    Orchestrates the execution of a compute graph.
    
    Acts as the main entry point for graph execution, delegating
    specialized tasks to sub-components:
    - PassRunner: Single pass execution (shader, bind, dispatch)
    - LoopExecutor: Multi-pass loops with ping-pong buffering
    - ResourceResolver: Texture allocation and readback
    """
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        
        # Core GPU operations
        self.gpu_ops = GPUOps()
        
        # Resource management
        self.resolver = ResourceResolver(texture_mgr)
        
        # Pass execution (using new modular components)
        self.pass_runner = PassRunner(shader_mgr, self.gpu_ops)
        self.loop_executor = LoopExecutor(
            self.pass_runner, 
            self.resolver, 
            texture_mgr, 
            self.gpu_ops
        )
        
        # Sequence export
        self.sequence_exporter = SequenceExporter()

    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """
        Execute the entire graph by running passes in order.
        
        Args:
            graph: IR Graph with resources and ops
            passes: List of ComputePass and PassLoop items
            context_width: Default width for unspecified resources
            context_height: Default height for unspecified resources
        """
        # Phase 1: Resolve Resources to GPU Textures
        texture_map = self.resolver.resolve_resources(graph, context_width, context_height)
        
        # Phase 2: Execute Passes
        for item in passes:
            # Robust check for Loop (handles module reloading)
            if 'PassLoop' in str(type(item)) or hasattr(item, 'body_passes'):
                self.loop_executor.execute(
                    graph, item, texture_map, context_width, context_height
                )
            else:
                self.pass_runner.run(
                    graph, item, texture_map, context_width, context_height
                )

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
        logger.debug("Graph execution completed")

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
