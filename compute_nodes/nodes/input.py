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
    """Get information about a Grid (dimensions, size)."""
    bl_idname = 'ComputeNodeImageInfo'
    bl_label = 'Grid Info'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # Input: Grid handle (cyan)
        self.inputs.new('ComputeSocketGrid', "Grid")
        # Outputs: Separate integers for each dimension and dimensionality
        self.outputs.new('NodeSocketInt', "Width")
        self.outputs.new('NodeSocketInt', "Height")
        self.outputs.new('NodeSocketInt', "Depth")  # Returns 1 for 2D grids
        self.outputs.new('NodeSocketInt', "Dimensionality")  # 1, 2, or 3
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label


class ComputeNodeValue(ComputeNode):
    """Output a constant float value."""
    bl_idname = 'ComputeNodeValue'
    bl_label = 'Value'
    bl_icon = 'DRIVER'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # Output: Float value
        self.outputs.new('NodeSocketFloat', "Value").default_value = 0.5
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label



