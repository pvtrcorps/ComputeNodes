import bpy
from bpy.props import PointerProperty
from ..nodetree import ComputeNode

class ComputeNodeImageInput(ComputeNode):
    bl_idname = 'ComputeNodeImageInput'
    bl_label = 'Image Input'
    bl_icon = 'IMAGE_DATA'
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        self.outputs.new('ComputeSocketImage', "Image")
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")

class ComputeNodeImageWrite(ComputeNode):
    bl_idname = 'ComputeNodeImageWrite'
    bl_label = 'Image Write (Storage)'
    bl_icon = 'IMAGE_DATA'
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        # Outputs a resource handle valid for writing
        self.outputs.new('ComputeSocketImage', "Image")
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")

class ComputeNodeImageInfo(ComputeNode):
    bl_idname = 'ComputeNodeImageInfo'
    bl_label = 'Image Info'
    
    def init(self, context):
        self.inputs.new('ComputeSocketImage', "Image")
        self.outputs.new('NodeSocketVector', "Size") # vec2 (w, h)
        # Maybe format info later
