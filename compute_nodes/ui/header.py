
import bpy

def draw_header_controls(self, context):
    """Draw execution controls in the Node Editor Header."""
    layout = self.layout
    
    # Check context
    if not context.space_data or context.space_data.tree_type != 'ComputeNodeTree':
        return
        
    tree = context.space_data.node_tree
    if not tree:
        return
        
    # Spacer to separate from standard menus
    layout.separator_spacer()
    
    # Execution Controls Row
    row = layout.row(align=True)
    
    # 1. Execute Button
    row.operator("compute.execute_graph", text="", icon='PLAY')
    
    # 2. Auto-Execute Toggle
    row.prop(tree, "auto_execute", text="", icon='FILE_REFRESH')
    
    # 3. Profiling Controls
    # Group them visually
    row.separator()
    row.prop(tree, "profile_execution", text="", icon='TIME', toggle=True)
    
    # Show time if profiling is enabled
    if tree.profile_execution:
        # Draw as a label in a box style or just text?
        # Header usually prefers simple text or buttons.
        # Let's align it nicely.
        sub = row.row(align=True)
        # Using a label with an icon looks good
        if tree.execution_time_total > 0:
            sub.label(text=f"{tree.execution_time_total:.2f} ms")
        else:
            sub.label(text="... ms")

def register():
    bpy.types.NODE_HT_header.append(draw_header_controls)

def unregister():
    try:
        bpy.types.NODE_HT_header.remove(draw_header_controls)
    except:
        pass
