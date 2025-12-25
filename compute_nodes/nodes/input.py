import bpy
from bpy.props import PointerProperty
from ..nodetree import ComputeNode


class ComputeNodeImageInput(ComputeNode):
    """Load a Blender image as a Grid (sampleable data)."""
    bl_idname = 'ComputeNodeImageInput'
    bl_label = 'Image Input'
    bl_icon = 'IMAGE_DATA'
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        # Output: Grid handle (cyan)
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageWrite(ComputeNode):
    """Write to a Blender image datablock (storage target)."""
    bl_idname = 'ComputeNodeImageWrite'
    bl_label = 'Image Write (Storage)'
    bl_icon = 'IMAGE_DATA'
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        # Output: Grid handle (cyan) for chaining
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageInfo(ComputeNode):
    """Get information about a Grid (size, etc)."""
    bl_idname = 'ComputeNodeImageInfo'
    bl_label = 'Grid Info'
    
    def init(self, context):
        # Input: Grid handle (cyan)
        self.inputs.new('ComputeSocketGrid', "Grid")
        self.outputs.new('NodeSocketVector', "Size")  # vec2 (w, h)



