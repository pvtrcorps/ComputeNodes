import bpy


# =============================================================================
# UI Lists
# =============================================================================

class COMPUTE_UL_interface_sockets(bpy.types.UIList):
    """Custom UI List for Group Sockets"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # Determine icon based on type mapping
        # We can try to guess from socket_type string
        icn = 'DOT'
        if 'Vector' in item.socket_type: icn = 'IPO'  # Vector/Axes
        elif 'Color' in item.socket_type: icn = 'COLOR'
        elif 'Float' in item.socket_type: icn = 'HOME'  # Best we have for float? Or just DOT
        elif 'Int' in item.socket_type: icn = 'LINENUMBERS_ON'
        elif 'Bool' in item.socket_type: icn = 'CHECKBOX_HLT'
        elif 'Grid' in item.socket_type: icn = 'RENDERLAYERS'
        elif 'Buffer' in item.socket_type: icn = 'BUFFER'
        
        # If float, maybe standard circle? 'DOT' is fine.
        
        # Layout: Icon | Name (Editable?)
        layout.label(text="", icon=icn)
        layout.prop(item, "name", text="", emboss=False)


# =============================================================================
# Panels
# =============================================================================

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


# =============================================================================
# Native Panel Override
# =============================================================================

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


# =============================================================================
# Registration
# =============================================================================

classes = (
    COMPUTE_UL_interface_sockets,
    COMPUTE_PT_group_interface,
    NODE_PT_node_tree_interface,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
