
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
        
    # Execution Controls Row
    # We place them next to the menus (Left aligned)
    # layout.separator_spacer() # Removed to align left
    
    # Execution Controls Row
    row = layout.row(align=True)
    
    # 1. Execute Button
    row.operator("compute.execute_graph", text="", icon='PLAY')
    
    # 2. Auto-Execute Toggle
    row.prop(tree, "auto_execute", text="", icon='FILE_REFRESH')
    
    # Separator
    row.separator()
    
    # 3. Profiling Controls (Combined Block)
    # [ Time Icon (Toggle) ] [ 12.34 ms ]
    
    sub = row.row(align=True)
    sub.prop(tree, "profile_execution", text="", icon='TIME', toggle=True)
    
    # Time label - Always visible to prevent layout jump
    # We use a row for the label so we can enable/disable it visually
    label_row = sub.row(align=True)
    label_row.enabled = tree.profile_execution  # Dim text when disabled
    
    if tree.execution_time_total > 0:
        time_text = f" {tree.execution_time_total:.2f} ms " 
    else:
        time_text = " 0.00 ms "
        
    # Using a flat operator or standard label? 
    # Label is better but alignment in header can be tricky.
    # We add a small box or align it.
    label_row.label(text=time_text)

def register():
    bpy.types.NODE_HT_header.append(draw_header_controls)

def unregister():
    try:
        bpy.types.NODE_HT_header.remove(draw_header_controls)
    except Exception:
        pass
