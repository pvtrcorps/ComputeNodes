import bpy
from bpy.props import PointerProperty
from ..nodetree import ComputeNode


class ComputeNodeImageInput(ComputeNode):
    """Load a Blender image as a Grid (sampleable data)."""
    bl_idname = 'ComputeNodeImageInput'
    bl_label = 'Image Input'
    bl_icon = 'IMAGE_DATA'
    node_category = "INPUT"
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        self.apply_node_color()
        # Output: Grid handle (cyan)
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageWrite(ComputeNode):
    """Write to a Blender image datablock (storage target)."""
    bl_idname = 'ComputeNodeImageWrite'
    bl_label = 'Image Write (Storage)'
    bl_icon = 'IMAGE_DATA'
    node_category = "OUTPUT"
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        self.apply_node_color()
        # Output: Grid handle (cyan) for chaining
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageInfo(ComputeNode):
    """Get information about a Grid (size, etc)."""
    bl_idname = 'ComputeNodeImageInfo'
    bl_label = 'Grid Info'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # Input: Grid handle (cyan)
        self.inputs.new('ComputeSocketGrid', "Grid")
        self.outputs.new('NodeSocketVector', "Size")  # vec2 (w, h)
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label



