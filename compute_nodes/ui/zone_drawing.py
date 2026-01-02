# Zone Drawing for Repeat Nodes
# Draws semi-transparent background connecting RepeatInput and RepeatOutput nodes
# Color comes from Blender's theme (repeat_zone)

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
import math

_handle = None


def find_repeat_zones(node_tree):
    """Find all paired RepeatInput/Output pairs in tree."""
    zones = []
    for node in node_tree.nodes:
        if node.bl_idname == 'ComputeNodeRepeatInput':
            if hasattr(node, 'paired_output') and node.paired_output:
                if node.paired_output in node_tree.nodes:
                    output = node_tree.nodes[node.paired_output]
                    zones.append((node, output))
    return zones


def find_nodes_between(input_node, output_node, node_tree):
    """
    Find all nodes connected between RepeatInput and RepeatOutput.
    Traverses from output backwards to input, collecting all nodes in between.
    """
    nodes_in_zone = {input_node, output_node}
    
    # BFS from output node's inputs backwards
    visited = set()
    queue = []
    
    # Start from all inputs of output node
    for socket in output_node.inputs:
        if socket.is_linked:
            for link in socket.links:
                queue.append(link.from_node)
    
    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)
        
        # Stop if we reach the input node
        if node == input_node:
            continue
        
        # Add this node to zone
        nodes_in_zone.add(node)
        
        # Continue traversing backwards
        for socket in node.inputs:
            if socket.is_linked:
                for link in socket.links:
                    from_node = link.from_node
                    if from_node not in visited:
                        queue.append(from_node)
    
    return nodes_in_zone


def get_node_corners(node, padding=15):
    """Get the 4 corners of a node with padding."""
    x, y = node.location
    w = node.width
    # Use dimensions if available, otherwise estimate
    h = node.dimensions[1] if node.dimensions[1] > 0 else 100
    
    return [
        (x - padding, y + padding),           # Top-left
        (x + w + padding, y + padding),       # Top-right
        (x + w + padding, y - h - padding),   # Bottom-right
        (x - padding, y - h - padding),       # Bottom-left
    ]


def convex_hull(points):
    """
    Compute convex hull of 2D points using Graham scan.
    Returns points in counter-clockwise order.
    """
    if len(points) < 3:
        return points
    
    # Find lowest point (and leftmost if tie)
    def lowest(p):
        return (p[1], p[0])
    
    start = min(points, key=lowest)
    
    # Sort by polar angle with respect to start point
    def polar_angle(p):
        dx = p[0] - start[0]
        dy = p[1] - start[1]
        return math.atan2(dy, dx)
    
    def distance(p):
        return (p[0] - start[0])**2 + (p[1] - start[1])**2
    
    sorted_points = sorted(points, key=lambda p: (polar_angle(p), distance(p)))
    
    # Remove duplicates
    unique_points = []
    for p in sorted_points:
        if not unique_points or p != unique_points[-1]:
            unique_points.append(p)
    
    if len(unique_points) < 3:
        return unique_points
    
    # Graham scan
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    
    hull = []
    for p in unique_points:
        while len(hull) >= 2 and cross(hull[-2], hull[-1], p) <= 0:
            hull.pop()
        hull.append(p)
    
    return hull


def get_zone_color():
    """Get repeat zone color from Blender's theme."""
    try:
        theme = bpy.context.preferences.themes[0]
        color = theme.node_editor.repeat_zone
        return tuple(color)  # (R, G, B, A)
    except:
        # Fallback to default orange
        return (0.7, 0.3, 0.1, 0.25)


def triangulate_polygon(vertices):
    """Convert polygon vertices to triangles using fan triangulation."""
    if len(vertices) < 3:
        return []
    
    triangles = []
    for i in range(1, len(vertices) - 1):
        triangles.append((0, i, i + 1))
    
    return triangles


def draw_zone_backgrounds():
    """Draw callback for node editor backdrop."""
    context = bpy.context
    
    # Check we're in node editor
    if not context.space_data or context.space_data.type != 'NODE_EDITOR':
        return
    
    # Check we have a ComputeNodeTree
    tree = context.space_data.edit_tree
    if not tree or tree.bl_idname != 'ComputeNodeTree':
        return
    
    # Find all repeat zones
    zones = find_repeat_zones(tree)
    if not zones:
        return
    
    # Get color from theme
    color = get_zone_color()
    
    # Get region for coordinate conversion
    region = context.region
    
    # Setup shader
    # Setup shaders
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    
    # Get scale once
    ui_scale = context.preferences.system.ui_scale
    
    # Config
    # Standard padding for intermediate nodes and vertical sides
    std_padding = 15 * ui_scale
    # Radius for corner rounding
    corner_radius = 6 * ui_scale
    
    for input_node, output_node in zones:
        try:
            # Find all nodes in this zone
            nodes_in_zone = find_nodes_between(input_node, output_node, tree)
            
            # Collect scaled corner points with specialized padding
            scaled_points = []
            
            for node in nodes_in_zone:
                # Coordinate System Correction (Mixed Logic):
                nx, ny = node.location
                sx = nx * ui_scale
                sy = ny * ui_scale
                
                dim_x = node.dimensions[0]
                dim_y = node.dimensions[1]
                if dim_y < 10: dim_y = 100 * ui_scale
                
                # Determine padding per side
                # Default: standard padding everywhere
                pad_l = std_padding
                pad_r = std_padding
                pad_t = std_padding
                pad_b = std_padding
                
                # Special Constraints for Input/Output nodes
                # "Do not surpass left and right edges" -> Zero/Small outer padding
                if node == input_node:
                    pad_l = -15  # Hard constrain left
                elif node == output_node:
                    pad_r = -15  # Hard constrain right
                
                # Corners in "Canvas Origin Scaled Space"
                corners = [
                    (sx - pad_l, sy + pad_t),
                    (sx + dim_x + pad_r, sy + pad_t),
                    (sx + dim_x + pad_r, sy - dim_y - pad_b),
                    (sx - pad_l, sy - dim_y - pad_b)
                ]
                scaled_points.extend(corners)
            
            if len(scaled_points) < 3:
                continue
            
            # Calculate convex hull
            hull_points = convex_hull(scaled_points)
            
            if len(hull_points) < 3:
                continue
                
            # --- Round Corners (Bevel) ---
            # Subdivide corners
            beveled_points = bevel_corners(hull_points, corner_radius)
            
            # Convert to region coordinates
            v2d = region.view2d
            region_verts = []
            
            for vx, vy in beveled_points:
                rx, ry = v2d.view_to_region(vx, vy, clip=False)
                region_verts.append((rx, ry))
            
            # Triangulate for FILL
            indices = triangulate_polygon(region_verts)
            
            if indices:
                # 1. Draw Fill
                batch = batch_for_shader(shader, 'TRIS', {"pos": region_verts}, indices=indices)
                shader.uniform_float("color", color)
                batch.draw(shader)
                
                # 2. Draw Outline
                # Slightly brighter/more opaque color for outline
                outline_color = (color[0]*1.2, color[1]*1.2, color[2]*1.2, min(color[3]*2.0, 1.0))
                # Or just use theme wire color? Stick to modification of base color.
                
                # Use LINE_LOOP to close the shape
                batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": region_verts})
                shader.uniform_float("color", outline_color)
                # Line width? GPU module usually ignores glLineWidth > 1 on modern drivers.
                # We stick to 1px line for now.
                batch_outline.draw(shader)
            
        except Exception as e:
            # Silently fail
            pass
    
    gpu.state.blend_set('NONE')

def bevel_corners(points, radius, segments=4):
    """
    Round the corners of a polygon (counter-clockwise).
    Replaces each vertex with an arc.
    """
    if len(points) < 3 or radius <= 0:
        return points
        
    new_points = []
    num = len(points)
    
    for i in range(num):
        p_prev = Vector(points[i-1])
        p_curr = Vector(points[i])
        p_next = Vector(points[(i+1) % num])
        
        # Vectors to neighbors
        v1 = (p_prev - p_curr)
        v2 = (p_next - p_curr)
        
        len1 = v1.length
        len2 = v2.length
        
        # Determine max radius for this corner (don't overlap)
        limit = min(len1, len2) / 2.0
        r = min(radius, limit)
        
        if r < 0.1:
            new_points.append(points[i])
            continue
            
        v1.normalize()
        v2.normalize()
        
        # Tangent points
        t1 = p_curr + v1 * r
        t2 = p_curr + v2 * r
        
        # Arc generation (Lerp or Slerp)
        # Using simple linear interpolation of vectors from a virtual center?
        # Or Quadratic Bezier from t1 to t2 with p_curr as control?
        # Bezier is easiest for smooth look.
        
        for j in range(segments + 1):
            t = j / segments
            # Quadratic Bezier: (1-t)^2 P0 + 2(1-t)t P1 + t^2 P2
            # P0=t1, P1=p_curr, P2=t2
            pt = (1-t)**2 * t1 + 2*(1-t)*t * p_curr + t**2 * t2
            new_points.append((pt.x, pt.y))
            
    return new_points


# =============================================================================
# CONTEXT PATH (BREADCRUMBS) DRAWING
# =============================================================================

_context_path_handle = None

def draw_context_path():
    """Draw breadcrumbs in the editor area (like native Blender), positioned after the TOOLS panel."""
    import blf
    
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
    """Register the draw handlers."""
    global _handle, _context_path_handle
    
    # Zone backgrounds
    if _handle is None:
        _handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_zone_backgrounds, (), 'WINDOW', 'BACKDROP'
        )
    
    # Context path overlay (in editor area like native Blender)
    if _context_path_handle is None:
        _context_path_handle = bpy.types.SpaceNodeEditor.draw_handler_add(
            draw_context_path, (), 'WINDOW', 'POST_PIXEL'
        )


def unregister():
    """Unregister the draw handlers."""
    global _handle, _context_path_handle
    
    if _handle is not None:
        bpy.types.SpaceNodeEditor.draw_handler_remove(_handle, 'WINDOW')
        _handle = None
    
    if _context_path_handle is not None:
        bpy.types.SpaceNodeEditor.draw_handler_remove(_context_path_handle, 'WINDOW')
        _context_path_handle = None
