# Capture Node - Materializes a Field to a Grid at specified resolution
import bpy
from bpy.props import IntProperty, EnumProperty
from ..nodetree import ComputeNode


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
    """
    bl_idname = 'ComputeNodeCapture'
    bl_label = 'Capture'
    bl_icon = 'RENDERLAYERS'
    
    # Grid dimensions
    dimensions: EnumProperty(
        name="Dimensions",
        items=[
            ('2D', "2D", "Image: width × height"),
            ('3D', "3D", "Volume: width × height × depth"),
        ],
        default='2D',
        description="Grid dimensionality"
    )
    
    # Output resolution
    width: IntProperty(
        name="Width",
        default=512,
        min=1,
        max=16384,
        description="Grid width in pixels/voxels"
    )
    
    height: IntProperty(
        name="Height", 
        default=512,
        min=1,
        max=16384,
        description="Grid height in pixels/voxels"
    )
    
    depth: IntProperty(
        name="Depth",
        default=64,
        min=1,
        max=2048,
        description="Grid depth in voxels (for 3D)"
    )
    
    def init(self, context):
        # Input: procedural field/color value
        self.inputs.new('NodeSocketColor', "Field")
        # Output: Grid handle (cyan socket)
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dimensions")
        col = layout.column(align=True)
        col.prop(self, "width")
        col.prop(self, "height")
        if self.dimensions == '3D':
            col.prop(self, "depth")


# Export for registration
node_classes = [ComputeNodeCapture]


