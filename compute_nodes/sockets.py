import bpy
from bpy.types import NodeSocket

# -----------------------------------------------------------------------------
# Blender 5.1+ Socket Shape Support
# -----------------------------------------------------------------------------

# Check if we're on Blender 5.1+ which has new socket shapes (LINE, VOLUME_GRID, LIST)
# These were announced for 5.0 but only landed in 5.1 Alpha
BLENDER_5_1 = bpy.app.version >= (5, 1, 0)

# Shape mapping for our data model
SOCKET_SHAPES = {
    'single': 'LINE' if BLENDER_5_1 else 'CIRCLE',       # Single value (constants)
    'field': 'DIAMOND',                                   # Field (lazy per-pixel)
    'grid': 'VOLUME_GRID' if BLENDER_5_1 else 'SQUARE',  # Materialized grid
    'list': 'LIST' if BLENDER_5_1 else 'SQUARE_DOT',     # Array/buffer data
    'dynamic': 'CIRCLE',                                  # Flexible (adapts to input)
}


def set_socket_shape(socket, structure: str):
    """
    Set socket display shape based on data structure type.
    
    This aligns with Blender 5.0's new socket shape vocabulary:
    - 'single': LINE shape - constant/single values (Value, Vector, Color inputs)
    - 'field': DIAMOND shape - lazy per-pixel evaluation (Position, Noise, etc.)
    - 'grid': VOLUME_GRID shape - materialized buffers (Capture output, Sample input)
    - 'list': LIST shape - array/buffer data (future SSBO support)
    - 'dynamic': CIRCLE shape - flexible, adapts to inputs (Math nodes)
    
    Args:
        socket: The NodeSocket to configure
        structure: One of 'single', 'field', 'grid', 'list', 'dynamic'
    """
    shape = SOCKET_SHAPES.get(structure, 'CIRCLE')
    try:
        socket.display_shape = shape
    except (AttributeError, TypeError):
        pass  # Older Blender or read-only socket


def get_shape_for_socket_type(socket_type: str) -> str:
    """
    Determine the appropriate shape structure based on socket type (bl_idname).
    
    Used for dynamic socket creation in Repeat Zones and Node Groups.
    
    Args:
        socket_type: The socket bl_idname (e.g., 'NodeSocketFloat', 'ComputeSocketGrid')
    
    Returns:
        Structure string for set_socket_shape ('single', 'field', 'grid', 'list', 'dynamic')
    """
    if 'Grid' in socket_type:
        return 'grid'
    elif 'Buffer' in socket_type:
        return 'list'
    else:
        # Standard Blender sockets in dynamic contexts are flexible
        # They adapt to what's connected (Field or Single value)
        return 'dynamic'


def apply_shape_for_socket(socket):
    """
    Apply the appropriate display_shape to a socket based on its type.
    
    Convenience function that combines get_shape_for_socket_type and set_socket_shape.
    
    Args:
        socket: The NodeSocket to configure
    """
    structure = get_shape_for_socket_type(socket.bl_idname)
    set_socket_shape(socket, structure)


# -----------------------------------------------------------------------------
# Custom Socket Classes
# -----------------------------------------------------------------------------

class ComputeSocketGrid(NodeSocket):
    """
    Custom socket for Grid handles (materialized data with defined domain).
    
    A Grid represents data captured at a specific resolution:
    - Grid2D: width x height (images, heightfields)
    - Grid3D: width x height x depth (volumes)
    - Grid1D: width only (arrays, LUTs)
    
    Use this for outputs of Capture, Resize, Image Input and inputs of Sample.
    Visual: Cyan color + VOLUME_GRID shape to distinguish from Fields.
    """
    bl_idname = 'ComputeSocketGrid'
    bl_label = 'Grid'
    
    def init_socket(self, node, socket_type):
        """Called when socket is created - set display shape."""
        set_socket_shape(self, 'grid')
    
    def draw_color(self, context, node):
        return (1.0, 0.85, 0.2, 1.0)  # Cyan

    def draw(self, context, layout, node, text):
        # Ensure shape is set (in case init_socket wasn't called)
        set_socket_shape(self, 'grid')
        layout.label(text=text)


class ComputeSocketBuffer(NodeSocket):
    """Custom socket for buffer data (future SSBO support). Uses LIST shape."""
    bl_idname = 'ComputeSocketBuffer'
    bl_label = 'Buffer'
    
    def init_socket(self, node, socket_type):
        """Called when socket is created - set display shape."""
        set_socket_shape(self, 'list')
    
    def draw_color(self, context, node):
        return (0.2, 0.8, 0.2, 1.0)  # Green

    def draw(self, context, layout, node, text):
        # Ensure shape is set
        set_socket_shape(self, 'list')
        layout.label(text=text)

class ComputeSocketEmpty(NodeSocket):
    """
    Invisible/Ghost socket for adding new inputs/outputs dynamically.
    """
    bl_idname = 'ComputeSocketEmpty'
    bl_label = 'New Socket'
    
    def draw_color(self, context, node):
        return (0.4, 0.4, 0.4, 0.4)  # Semi-transparent gray

    def draw(self, context, layout, node, text):
        layout.label(text="") # No text

class ComputeSocketReroute(NodeSocket):
    """
    Custom socket for Reroute nodes that dynamically adapts its color
    based on the connected socket type by recursively tracing the connection chain.
    """
    bl_idname = 'ComputeSocketReroute'
    bl_label = 'Reroute'
    
    def draw(self, context, layout, node, text):
        pass  # Reroute sockets don't draw content
    
    def draw_color(self, context, node):
        """
        Dynamically compute color by tracing back through the connection chain.
        This ensures reroute nodes visually match their source socket type.
        """
        visited = set()
        
        def get_source_color(socket):
            """Recursively find the source socket's color."""
            # Prevent infinite loops
            if socket in visited:
                return None
            visited.add(socket)
            
            # If not linked, return default gray
            if not socket.is_linked:
                return (0.5, 0.5, 0.5, 1.0)
            
            # Get the connected socket
            link = socket.links[0]
            source_socket = link.from_socket
            
            # If source is also a reroute, recurse
            if source_socket.node.bl_idname == "NodeReroute":
                target_socket = source_socket.node.inputs[0]
                color = get_source_color(target_socket)
                if color:
                    return color
            else:
                # Found the actual source - use its draw_color if available
                if hasattr(source_socket, 'draw_color'):
                    return source_socket.draw_color(context, source_socket.node)
                # Fallback to standard socket colors
                elif hasattr(source_socket, 'type'):
                    # Standard Blender socket type colors
                    type_colors = {
                        'VALUE': (0.63, 0.63, 0.63, 1.0),  # Gray
                        'INT': (0.13, 0.52, 0.15, 1.0),     # Green
                        'BOOLEAN': (0.8, 0.65, 0.84, 1.0),  # Pink
                        'VECTOR': (0.39, 0.39, 0.78, 1.0),  # Blue
                        'RGBA': (0.78, 0.78, 0.16, 1.0),    # Yellow
                    }
                    return type_colors.get(source_socket.type, (0.5, 0.5, 0.5, 1.0))
            
            return (0.5, 0.5, 0.5, 1.0)  # Fallback gray
        
        # Trace color from input
        if self.node.inputs and self.node.inputs[0].is_linked:
            color = get_source_color(self.node.inputs[0])
            if color:
                return color
        
        # Default gray for unconnected reroutes
        return (0.5, 0.5, 0.5, 1.0)

# Export for registration
socket_classes = [ComputeSocketGrid, ComputeSocketBuffer, ComputeSocketEmpty, ComputeSocketReroute]

def map_socket_type(interface_type):
    """Map Blender interface socket type to our socket types."""
    # Clean, explicit mapping for scalability
    SOCKET_MAPPING = {
        # Standard Blender Types (Fields)
        'NodeSocketFloat': 'NodeSocketFloat',
        'NodeSocketInt': 'NodeSocketInt',
        'NodeSocketBool': 'NodeSocketBool',
        'NodeSocketVector': 'NodeSocketVector',
        'NodeSocketColor': 'NodeSocketColor',
        'NodeSocketString': 'NodeSocketString',
        'NodeSocketRotation': 'NodeSocketVector', # Map rotation to vector
        
        # Custom Types (Grids)
        'ComputeSocketGrid': 'ComputeSocketGrid',
        'ComputeSocketBuffer': 'ComputeSocketBuffer',
        
        # Internal Repeat Types (if needed)
        'FLOAT': 'NodeSocketFloat',
        'VECTOR': 'NodeSocketVector', 
        'COLOR': 'NodeSocketColor',
        'GRID': 'ComputeSocketGrid',
    }
    
    # Default to Grid if unknown (or maybe Float?)
    return SOCKET_MAPPING.get(interface_type, 'ComputeSocketGrid')

