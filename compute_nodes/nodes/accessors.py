import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode


class ComputeNodePosition(ComputeNode):
    """Get current pixel/thread position."""
    bl_idname = 'ComputeNodePosition'
    bl_label = 'Position'
    bl_icon = 'AXIS_TOP'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        self.outputs.new('NodeSocketVector', "Coordinate")
        self.outputs.new('NodeSocketVector', "Normalized")
        self.outputs.new('NodeSocketInt', "Global Index")

    def draw_label(self):
        self._draw_node_color()
        return self.bl_label


class ComputeNodeSample(ComputeNode):
    """Sample a Grid at given coordinates."""
    bl_idname = 'ComputeNodeSample'
    bl_label = 'Sample'
    bl_icon = 'EYEDROPPER'
    node_category = "TEXTURE"
    
    def init(self, context):
        self.apply_node_color()
        # Input: Grid to sample (cyan)
        self.inputs.new('ComputeSocketGrid', "Grid")
        # Input: coordinates for sampling
        self.inputs.new('NodeSocketVector', "Coordinate")
        # Output: sampled color (yellow) - returns to Field domain
        self.outputs.new('NodeSocketColor', "Color")
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label



