import bpy
from bpy.types import NodeSocket

class ComputeSocketImage(NodeSocket):
    bl_idname = 'ComputeSocketImage'
    bl_label = 'Image'
    
    default_value: bpy.props.PointerProperty(type=bpy.types.Image, name="Image")

    # Custom color for Image sockets (e.g. Orange)
    def draw_color(self, context, node):
        return (1.0, 0.6, 0.2, 1.0) 

    def draw(self, context, layout, node, text):
        if self.is_output or self.is_linked:
            layout.label(text=text)
        else:
            layout.template_ID(self, "default_value", open="image.open", text=text)

class ComputeSocketBuffer(NodeSocket):
    bl_idname = 'ComputeSocketBuffer'
    bl_label = 'Buffer'
    
    # Custom color for Buffer sockets (e.g. Greenish)
    def draw_color(self, context, node):
        return (0.2, 0.8, 0.2, 1.0) 

    def draw(self, context, layout, node, text):
        layout.label(text=text)
