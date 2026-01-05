# Context Path (Breadcrumbs) Drawing for Node Groups
# Displays navigation breadcrumbs when inside Node Groups (like native Blender)

import bpy
import blf

_context_path_handle = None


def draw_context_path():
    """Draw breadcrumbs in the editor area (like native Blender), positioned after the TOOLS panel."""
    context = bpy.context
    
    # Check we're in node editor
    if not context.space_data or context.space_data.type != 'NODE_EDITOR':
        return
    
    # Check we have a ComputeNodeTree
    if context.space_data.tree_type != 'ComputeNodeTree':
        return
    
    # Check if overlay is enabled
    if hasattr(context.space_data, 'overlay') and hasattr(context.space_data.overlay, 'show_context_path'):
        if not context.space_data.overlay.show_context_path:
            return
    
    # Get the path
    path = context.space_data.path
    if not path or len(path) <= 1:
        return  # Only show when inside a group (path length > 1)
    
    # Build path string with nice separator
    path_parts = []
    for elem in path:
        if elem.node_tree:
            path_parts.append(elem.node_tree.name)
    
    if not path_parts:
        return
    
    path_string = "  ›  ".join(path_parts)
    
    # Get UI scale
    ui_scale = context.preferences.system.ui_scale
    
    # Find the TOOLS region width to offset our drawing
    tools_width = 0
    for region in context.area.regions:
        if region.type == 'TOOLS':
            tools_width = region.width
            break
    
    # Drawing position: after TOOLS panel, near top of editor
    region = context.region
    x = tools_width + 15 * ui_scale  # Offset past toolbar + padding
    y = region.height - 25 * ui_scale  # Near top
    
    # Light text color for visibility on dark background
    text_color = (0.85, 0.85, 0.85, 1.0)
    
    # Draw with shadow for readability
    font_id = 0
    font_size = int(13 * ui_scale)
    blf.size(font_id, font_size)
    
    # Shadow (black, offset)
    blf.color(font_id, 0.0, 0.0, 0.0, 0.8)
    blf.position(font_id, x + 1, y - 1, 0)
    blf.draw(font_id, path_string)
    
    # Main text
    blf.color(font_id, text_color[0], text_color[1], text_color[2], 1.0)
    blf.position(font_id, x, y, 0)
    blf.draw(font_id, path_string)


def register():
    """Register the draw handler."""
    global _context_path_handle
    
    if _context_path_handle is None:
        _context_path_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_context_path, (), 'WINDOW', 'POST_PIXEL'
        )


def unregister():
    """Unregister the draw handler."""
    global _context_path_handle
    
    if _context_path_handle is not None:
        bpy.types.SpaceNodeEditor.draw_handler_remove(_context_path_handle, 'WINDOW')
        _context_path_handle = None
