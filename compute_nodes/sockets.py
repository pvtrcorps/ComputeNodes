import bpy
from bpy.types import NodeSocket


class ComputeSocketGrid(NodeSocket):
    """
    Custom socket for Grid handles (materialized data with defined domain).
    
    A Grid represents data captured at a specific resolution:
    - Grid2D: width x height (images, heightfields)
    - Grid3D: width x height x depth (volumes)
    - Grid1D: width only (arrays, LUTs)
    
    Use this for outputs of Capture, Resize, Image Input and inputs of Sample.
    Visual: Cyan color to distinguish from procedural Color/Field values (yellow).
    """
    bl_idname = 'ComputeSocketGrid'
    bl_label = 'Grid'
    
    def draw_color(self, context, node):
        return (0.2, 0.8, 0.9, 1.0)  # Cyan

    def draw(self, context, layout, node, text):
        layout.label(text=text)


class ComputeSocketBuffer(NodeSocket):
    """Custom socket for buffer data (future SSBO support)"""
    bl_idname = 'ComputeSocketBuffer'
    bl_label = 'Buffer'
    
    def draw_color(self, context, node):
        return (0.2, 0.8, 0.2, 1.0)  # Green

    def draw(self, context, layout, node, text):
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

