
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
            
            # Profiling Controls
            row = layout.row(align=True)
            row.prop(tree, "profile_execution", toggle=True, icon='TIME')
            if tree.profile_execution:
                row.label(text=f"{tree.execution_time_total:.2f} ms")

# ============================================================================
# UI LIST & PANELS
# ============================================================================

class COMPUTE_OT_add_group_socket(bpy.types.Operator):
    """Add a new socket to the group interface"""
    bl_idname = "compute.add_group_socket"
    bl_label = "Add Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    in_out: bpy.props.EnumProperty(
        items=[('INPUT', "Input", ""), ('OUTPUT', "Output", "")],
        name="Type"
    )
    
    socket_type: bpy.props.EnumProperty(
        items=[
            ('NodeSocketFloat', "Float", "Floating point value", 'usage_float', 0),
            ('NodeSocketInt', "Integer", "Integer value", 'usage_int', 1),
            ('NodeSocketBool', "Boolean", "Boolean value", 'usage_bool', 2),
            ('NodeSocketVector', "Vector", "3D Vector", 'usage_vector', 3),
            ('NodeSocketColor', "Color", "RGBA Color", 'usage_color', 4),
            ('NodeSocketString', "String", "Text string", 'usage_string', 5),
            ('ComputeSocketGrid', "Grid", "Compute Grid Data", 'RENDERLAYERS', 6),
            ('ComputeSocketBuffer', "Buffer", "Compute Buffer Data", 'BUFFER', 7),
        ],
        name="Socket Type"
    )
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree: return {'CANCELLED'}
        
        # Determine name base
        base_name = "Value"
        if "Vector" in self.socket_type: base_name = "Vector"
        if "Color" in self.socket_type: base_name = "Color"
        if "Grid" in self.socket_type: base_name = "Grid"
        
        # New Socket
        tree.interface.new_socket(base_name, in_out=self.in_out, socket_type=self.socket_type)
        
        # Trigger Sync
        try:
            from .nodes.nodegroup import update_parent_groups
            update_parent_groups(tree)
            for node in tree.nodes:
                if hasattr(node, "sync_from_interface"):
                    node.sync_from_interface()
        except:
            pass
            
        return {'FINISHED'}

class COMPUTE_OT_move_group_socket(bpy.types.Operator):
    """Move a socket up or down"""
    bl_idname = "compute.move_group_socket"
    bl_label = "Move Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    socket_name: bpy.props.StringProperty()
    direction: bpy.props.EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])
    
    def execute(self, context):
        tree = context.space_data.node_tree
        interface = tree.interface
        item = interface.items_tree.get(self.socket_name)
        if not item: return {'CANCELLED'}
        
        keys = list(interface.items_tree.keys())
        current_idx = keys.index(item.name)
        
        new_idx = current_idx - 1 if self.direction == 'UP' else current_idx + 1
        
        if 0 <= new_idx < len(keys):
            interface.move(item, new_idx)
            
            # Sync
            try:
                from .nodes.nodegroup import update_parent_groups
                update_parent_groups(tree)
                for node in tree.nodes:
                    if hasattr(node, "sync_from_interface"):
                        node.sync_from_interface()
            except:
                pass
                
        return {'FINISHED'}

class COMPUTE_UL_interface_sockets(bpy.types.UIList):
    """Custom UI List for Group Sockets"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # Determine icon based on type mapping
        # We can try to guess from socket_type string
        icn = 'DOT'
        if 'Vector' in item.socket_type: icn = 'Gm' # Vector/Axes
        elif 'Color' in item.socket_type: icn = 'COLOR'
        elif 'Float' in item.socket_type: icn = 'HOME' # Best we have for float? Or just DOT
        elif 'Int' in item.socket_type: icn = 'LINENUMBERS_ON'
        elif 'Bool' in item.socket_type: icn = 'CHECKBOX_HLT'
        elif 'Grid' in item.socket_type: icn = 'RENDERLAYERS'
        elif 'Buffer' in item.socket_type: icn = 'BUFFER'
        
        # If float, maybe standard circle? 'DOT' is fine.
        
        # Layout: Icon | Name (Editable?)
        layout.label(text="", icon=icn)
        layout.prop(item, "name", text="", emboss=False)

class COMPUTE_PT_group_interface(bpy.types.Panel):
    """Group Interface Panel for editing sockets (Replaces Native)"""
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
        interface = tree.interface
        
        # 1. Socket List (Input / Output separated? Native separates them?)
        # Native combines them? No, template_node_tree_interface usually isolates.
        # But interface.items_tree contains BOTH.
        # UIList iterates a collection. We can't easily filter UIList without 'filter_items' logic which is complex.
        
        # Better strategy: Two lists? But items_tree is mixed.
        # Or just one list showing In/Out icon?
        # The reference addon separates them in logic but maybe draws one list? 
        # "MTX_UL_node_tree_interface_Groups_List" -> generic.
        
        # Let's try drawing ONE list with icons indicating In/Out
        # Actually proper filtering in UIList is the way.
        
        row = layout.row()
        row.template_list(
            "COMPUTE_UL_interface_sockets", "", 
            interface, "items_tree", 
            interface, "active_index", 
            rows=6
        )
        
        col = row.column(align=True)
        # Use menu_enum to allow selecting the specific type defined in the operator
        col.operator_menu_enum("compute.add_group_socket", "socket_type", text="", icon='ADD').in_out = 'INPUT'
        col.operator_menu_enum("compute.add_group_socket", "socket_type", text="", icon='EXPORT').in_out = 'OUTPUT'
        
        col.separator()
        col.operator("compute.move_group_socket", text="", icon='TRIA_UP').direction = 'UP'
        col.operator("compute.move_group_socket", text="", icon='TRIA_DOWN').direction = 'DOWN'
        col.separator()
        
        # Delete helper (need to get name from active)
        if interface.active:
            op = col.operator("compute.remove_group_socket_interface", text="", icon='X')
            op.socket_name = interface.active.name
        
        # 2. Properties of Active Socket
        if interface.active:
            item = interface.active
            
            box = layout.box()
            box.label(text="Socket Properties", icon='PREFERENCES')
            
            # Common
            box.prop(item, "name")
            
            # Allow changing type of existing socket
            # This uses Blender's native enum, which includes ALL types (Standard + Custom)
            box.prop(item, "socket_type")
            
            box.prop(item, "description")
            
            # Type-specific settings (Default, Min, Max)
            # This calls the socket's custom draw method!
            if hasattr(item, "draw"):
                item.draw(context, box)

# ============================================================================
# NATIVE PANEL OVERRIDE
# ============================================================================

class NODE_PT_node_tree_interface(bpy.types.Panel):
    """
    Override Blender's native interface panel to HIDE it for ComputeNodeTree,
    but keep it working for everything else.
    """
    bl_idname = "NODE_PT_node_tree_interface"
    bl_label = "Group Sockets"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Group"
    bl_order = 10
    
    @classmethod
    def poll(cls, context):
        snode = context.space_data
        if snode.type != 'NODE_EDITOR' or not snode.node_tree:
            return False

        ntree = snode.node_tree

        # HIDE for our Addon
        if snode.tree_type == "ComputeNodeTree":
            return False

        # Logic copied from Reference Addon to maintain standard behavior
        if ntree.bl_rna.identifier not in {'GeometryNodeTree', 'ShaderNodeTree', 'CompositorNodeTree'}:
            return False
            
        if snode.tree_type == "ShaderNodeTree" and len(snode.path) <= 1:
            return False
            
        if ntree.id_data and not getattr(ntree.id_data, 'is_user_editable', True):
            return False

        return True
    
    def draw(self, context):
        # Native Drawing Logic
        layout = self.layout
        snode = context.space_data
        if not snode.path: return
        tree = snode.path[-1].node_tree
        
        # Use native widget for everyone else
        layout.template_node_tree_interface(tree.interface)


classes = (
    ComputeExecuteOperator,
    COMPUTE_OT_add_group_socket,
    COMPUTE_OT_move_group_socket,
    COMPUTE_PT_MainPanel,
    COMPUTE_UL_interface_sockets,
    COMPUTE_PT_group_interface,
    NODE_PT_node_tree_interface,
)

def register():
    for cls in classes:
        # Check if native panel is registered, unregister it locally to avoid warning?
        # Actually re-registering overwrites it, which is what we want.
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            bpy.utils.unregister_class(cls)
            bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass
