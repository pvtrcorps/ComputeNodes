import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape


class ComputeNodePosition(ComputeNode):
    """Get current pixel/thread position."""
    bl_idname = 'ComputeNodePosition'
    bl_label = 'Position'
    bl_icon = 'AXIS_TOP'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # All outputs are Fields (per-pixel values)
        coord = self.outputs.new('NodeSocketVector', "Coordinate")
        set_socket_shape(coord, 'field')
        normalized = self.outputs.new('NodeSocketVector', "Normalized")
        set_socket_shape(normalized, 'field')
        idx = self.outputs.new('NodeSocketInt', "Global Index")
        set_socket_shape(idx, 'field')

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
        # Input: Grid to sample (VOLUME_GRID shape)
        grid_in = self.inputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_in, 'grid')
        # Input: coordinates for sampling (field input)
        coord_in = self.inputs.new('NodeSocketVector', "Coordinate")
        set_socket_shape(coord_in, 'field')
        # Output: sampled color - returns to Field domain
        color_out = self.outputs.new('NodeSocketColor', "Color")
        set_socket_shape(color_out, 'field')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label



