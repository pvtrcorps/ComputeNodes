# Resize Node - For multi-resolution workflows (Grid → Grid)
import bpy
from bpy.props import IntProperty, EnumProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid, set_socket_shape


def update_dimensions(self, context):
    """Update socket visibility based on 2D/3D mode."""
    if 'Depth' in self.inputs:
        # Hide socket in 2D mode, show in 3D mode
        self.inputs['Depth'].hide = (self.dim_mode == '2D')


class ComputeNodeResize(ComputeNode):
    """
    Resize/Scale a Grid to a new resolution.
    
    Grid Architecture:
    - Input: Grid (from Capture, ImageInput, or another Resize)
    - Output: Grid at new resolution
    - Supports 2D and 3D grids
    - Uses bilinear/trilinear interpolation
    
    Resolution can be set via:
    - Node properties (static values)
    - Input sockets (dynamic/connected values, e.g., from loop Iteration)
    """
    bl_idname = 'ComputeNodeResize'
    bl_label = 'Resize'
    bl_icon = 'FULLSCREEN_ENTER'
    node_category = "GRID"
    
    # Dimensions mode (consistent with Capture)
    # Dimensions mode (consistent with Capture)
    dim_mode: EnumProperty(
        name="Dimensions",
        items=[
            ('2D', "2D", "Image: width × height"),
            ('3D', "3D", "Volume: width × height × depth"),
        ],
        default='2D',
        description="Grid dimensionality",
        update=update_dimensions
    )
    
    # Interpolation mode
    interpolation: EnumProperty(
        name="Interpolation",
        items=[
            ('BILINEAR', "Bilinear", "Smooth interpolation"),
            ('NEAREST', "Nearest", "Nearest neighbor (pixelated)"),
        ],
        default='BILINEAR'
    )
    
    def init(self, context):
        self.apply_node_color()
        # Grid I/O uses VOLUME_GRID shape
        grid_in = self.inputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_in, 'grid')
        # Resolution inputs - single values
        w = self.inputs.new('NodeSocketInt', "Width")
        set_socket_shape(w, 'single')
        h = self.inputs.new('NodeSocketInt', "Height")
        set_socket_shape(h, 'single')
        d = self.inputs.new('NodeSocketInt', "Depth")
        set_socket_shape(d, 'single')
        grid_out = self.outputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_out, 'grid')
        
        # Set default values on sockets
        self.inputs['Width'].default_value = 512
        self.inputs['Height'].default_value = 512
        self.inputs['Depth'].default_value = 64
        
        # Hide Depth socket by default (2D mode)
        self.inputs['Depth'].hide = True
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dim_mode")
        layout.prop(self, "interpolation")


node_classes = [ComputeNodeResize]

