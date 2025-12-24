import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode

class ComputeNodePosition(ComputeNode):
    bl_idname = 'ComputeNodePosition'
    bl_label = 'Position'
    bl_icon = 'AXIS_TOP'
    
    def init(self, context):
        self.outputs.new('NodeSocketVector', "Coordinate") # Grid Index (int) or UV?
        self.outputs.new('NodeSocketVector', "Normalized")
        self.outputs.new('NodeSocketInt', "Global Index")

class ComputeNodeSample(ComputeNode):
    bl_idname = 'ComputeNodeSample'
    bl_label = 'Sample Image'
    bl_icon = 'EYEDROPPER'
    
    def init(self, context):
        self.inputs.new('ComputeSocketImage', "Image")
        self.inputs.new('NodeSocketVector', "Coordinate")
        self.outputs.new('NodeSocketColor', "Color")
