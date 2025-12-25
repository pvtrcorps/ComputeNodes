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


# Export for registration
socket_classes = [ComputeSocketGrid, ComputeSocketBuffer]

