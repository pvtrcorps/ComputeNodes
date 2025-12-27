
import bpy
from .graph_extract import extract_graph
from .planner.passes import ComputePass
from .planner.loops import PassLoop
from .ir.resources import ImageDesc
from .planner.scheduler import schedule_passes
from .codegen.glsl import ShaderGenerator
from .runtime import TextureManager, ShaderManager, ComputeExecutor

# Global Runtime Singleton (Simple MVP)
_texture_mgr = None
_shader_mgr = None
_executor = None

def get_executor():
    global _texture_mgr, _shader_mgr, _executor
    if _executor is None:
        _texture_mgr = TextureManager()
        _shader_mgr = ShaderManager()
        _executor = ComputeExecutor(_texture_mgr, _shader_mgr)
    return _executor


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
        # 1. Extract Graph
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

        
        executor.execute_graph(graph, passes, context_width=width, context_height=height)
        
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

class ComputeExecuteOperator(bpy.types.Operator):
    """Execute the current Compute Node Tree on GPU"""
    bl_idname = "compute.execute_graph"
    bl_label = "Execute Compute Graph"
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree:
            self.report({'ERROR'}, "No active node tree")
            return {'CANCELLED'}
            
        try:
            count = execute_compute_tree(tree, context)
            self.report({'INFO'}, f"Executed {count} passes.")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Execution Failed: {e}")
            return {'CANCELLED'}

from bpy.app.handlers import persistent





class COMPUTE_PT_MainPanel(bpy.types.Panel):
    """Creates a Panel in the Compute Node Editor"""
    bl_label = "Compute Runtime"
    bl_idname = "COMPUTE_PT_main"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Compute"

    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ComputeNodeTree'

    def draw(self, context):
        layout = self.layout
        tree = context.space_data.node_tree
        
        row = layout.row(align=True)
        row.operator("compute.execute_graph", icon='PLAY')
        
        if tree:
            row.prop(tree, "auto_execute", text="", icon='FILE_REFRESH')

class COMPUTE_PT_group_interface(bpy.types.Panel):
    """Group Interface Panel for editing sockets"""
    bl_label = "Group Interface"
    bl_idname = "COMPUTE_PT_group_interface"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Group"

    @classmethod
    def poll(cls, context):
        return (context.space_data.tree_type == 'ComputeNodeTree' and
                context.space_data.node_tree is not None)

    def draw(self, context):
        layout = self.layout
        tree = context.space_data.node_tree
        
        # Native Blender Interface Editor
        try:
            layout.template_node_tree_interface(tree.interface)
        except AttributeError:
            # Fallback for older Blender versions if interface API differs
            layout.label(text="Interface editing requires Blender 4.0+")


classes = (
    ComputeExecuteOperator,
    COMPUTE_PT_MainPanel,
    COMPUTE_PT_group_interface,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
