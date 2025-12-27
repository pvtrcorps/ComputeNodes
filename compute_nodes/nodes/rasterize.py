# Capture Node - Materializes a Field to a Grid at specified resolution
import bpy
from bpy.props import IntProperty, EnumProperty
from ..nodetree import ComputeNode


def update_dimensions(self, context):
    """Update socket visibility based on 2D/3D mode."""
    if 'Depth' in self.inputs:
        # Hide socket in 2D mode, show in 3D mode
        self.inputs['Depth'].hide = (self.dim_mode == '2D')


class ComputeNodeCapture(ComputeNode):
    """
    Capture (Materialize) a procedural field to a Grid.
    
    This node evaluates a Field (lazy procedural data) at every point of
    a grid with the specified resolution, creating materialized data.
    
    The output Grid can then be sampled by other nodes (Sample, etc.)
    at arbitrary coordinates with interpolation.
    
    Grid Architecture:
    - Grid1D: width only (future)
    - Grid2D: width x height
    - Grid3D: width x height x depth
    
    Resolution can be set via:
    - Input sockets (dynamic/connected values, e.g., from GridInfo or loop Iteration)
    - Socket default values (static values when not connected)
    """
    bl_idname = 'ComputeNodeCapture'
    bl_label = 'Capture'
    bl_icon = 'RENDERLAYERS'
    node_category = "GRID"
    
    # Grid dimensions mode
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
    
    def init(self, context):
        self.apply_node_color()
        # Input: procedural field/color value
        self.inputs.new('NodeSocketColor', "Field")
        # Resolution inputs - allow dynamic values
        self.inputs.new('NodeSocketInt', "Width")
        self.inputs.new('NodeSocketInt', "Height")
        self.inputs.new('NodeSocketInt', "Depth")
        # Output: Grid handle (cyan socket)
        self.outputs.new('ComputeSocketGrid', "Grid")
        
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


# Export for registration
node_classes = [ComputeNodeCapture]

