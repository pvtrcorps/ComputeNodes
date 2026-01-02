
import bpy
from .graph_extract import extract_graph
from .planner.passes import ComputePass
from .planner.loops import PassLoop
from .ir.resources import ImageDesc
from .planner.scheduler import schedule_passes
from .codegen.glsl import ShaderGenerator
from .runtime import TextureManager, ShaderManager, ComputeExecutor


# =============================================================================
# ExecutionContext - Encapsulates all runtime state
# =============================================================================

class ExecutionContext:
    """
    Encapsulates runtime state for a single graph execution.
    
    Benefits over global singletons:
    - Thread-safe: each execution gets its own context
    - Testable: can be mocked/injected in tests
    - Stateless between executions: no stale data issues
    """
    _instance = None  # Optional cached instance for performance
    
    def __init__(self, fresh: bool = False):
        """
        Initialize execution context.
        
        Args:
            fresh: If True, create new managers. If False, reuse cached managers.
        """
        if fresh or ExecutionContext._instance is None:
            self.texture_mgr = TextureManager()
            self.shader_mgr = ShaderManager()
            self.executor = ComputeExecutor(self.texture_mgr, self.shader_mgr)
            if not fresh:
                ExecutionContext._instance = self
        else:
            # Reuse cached instance for performance
            cached = ExecutionContext._instance
            self.texture_mgr = cached.texture_mgr
            self.shader_mgr = cached.shader_mgr
            self.executor = cached.executor
    
    @classmethod
    def get(cls, fresh: bool = False) -> 'ExecutionContext':
        """Factory method to get an execution context."""
        return cls(fresh=fresh)
    
    @classmethod
    def reset(cls):
        """Clear cached instance (useful for testing)."""
        cls._instance = None


def get_executor():
    """Backward-compatible accessor for executor."""
    return ExecutionContext.get().executor


def _generate_shader_for_item(item, generator):
    """Recursively generate GLSL for passes and PassLoops."""
    if isinstance(item, PassLoop):
        # Generate shaders for all body passes inside the loop
        for body_pass in item.body_passes:
            _generate_shader_for_item(body_pass, generator)
    else:
        # Regular ComputePass
        item.source = generator.generate(item)
        item.display_source = item.source

def execute_compute_tree(tree, context):
    """Core execution logic for a Compute Node Tree"""
    try:
        # Setup Logging
        from .logger import setup_logger, log_info
        setup_logger()  # Default to INFO
        
        # 1. Extract Graph
        log_info(f"Extracting graph from {tree.name}...")
        graph = extract_graph(tree)
        
        # 2. Analysis & Planning
        passes = schedule_passes(graph)
        
        # 3. Code Generation (handles PassLoop recursively)
        generator = ShaderGenerator(graph)
        for p in passes:
            _generate_shader_for_item(p, generator)
            
        # 4. Execution
        executor = get_executor()
        
        # Resolution Handling - Use ImageDesc.size directly (image may not exist yet)
        width, height = 512, 512  # Fallback
        
        for res in graph.resources:
            if isinstance(res, ImageDesc) and res.access.name in {'WRITE', 'READ_WRITE'}:
                # Use the size from the ImageDesc (set by Output node properties)
                if res.size != (0, 0):
                    width = res.size[0]
                    height = res.size[1]
                    break
        
        # Fallback to scene resolution if still default
        if width == 512 and height == 512:
            render = context.scene.render
            scale = render.resolution_percentage / 100.0
            width = int(render.resolution_x * scale)
            height = int(render.resolution_y * scale)

        # PROFILING: Propagate settings to Graph
        graph.profile_execution = getattr(tree, 'profile_execution', False)
        if graph.profile_execution:
            graph.execution_time_total = 0.0
            # Reset node times? Done by executor overwriting, but good ensuring validity
            
        executor.execute_graph(graph, passes, context_width=width, context_height=height)
        
        # PROFILING: Sync results back to Tree
        if graph.profile_execution:
            tree.execution_time_total = getattr(graph, 'execution_time_total', 0.0)
        
        # Force redraw (if UI is available)
        if hasattr(context, "window_manager") and context.window_manager:
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'IMAGE_EDITOR' or area.type == 'VIEW_3D':
                        area.tag_redraw()
                    
        return len(passes)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise e
