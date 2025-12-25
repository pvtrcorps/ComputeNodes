import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode


class ComputeNodePosition(ComputeNode):
    """Get current pixel/thread position."""
    bl_idname = 'ComputeNodePosition'
    bl_label = 'Position'
    bl_icon = 'AXIS_TOP'
    
    def init(self, context):
        self.outputs.new('NodeSocketVector', "Coordinate")
        self.outputs.new('NodeSocketVector', "Normalized")
        self.outputs.new('NodeSocketInt', "Global Index")


class ComputeNodeSample(ComputeNode):
    """Sample a Grid at given coordinates."""
    bl_idname = 'ComputeNodeSample'
    bl_label = 'Sample'
    bl_icon = 'EYEDROPPER'
    
    def init(self, context):
        # Input: Grid to sample (cyan)
        self.inputs.new('ComputeSocketGrid', "Grid")
        # Input: coordinates for sampling
        self.inputs.new('NodeSocketVector', "Coordinate")
        # Output: sampled color (yellow) - returns to Field domain
        self.outputs.new('NodeSocketColor', "Color")



