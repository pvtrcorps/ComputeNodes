import bpy
from bpy.types import NodeSocket

# NOTE: ComputeSocketImage removed - using native NodeSocketImage instead
# This provides better Blender integration and native UI

class ComputeSocketBuffer(NodeSocket):
    """Custom socket for buffer data (future SSBO support)"""
    bl_idname = 'ComputeSocketBuffer'
    bl_label = 'Buffer'
    
    # Custom color for Buffer sockets (e.g. Greenish)
    def draw_color(self, context, node):
        return (0.2, 0.8, 0.2, 1.0) 

    def draw(self, context, layout, node, text):
        layout.label(text=text)

