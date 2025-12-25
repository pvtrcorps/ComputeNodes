# Resize Node - For multi-resolution workflows (Grid → Grid)
import bpy
from bpy.props import IntProperty, EnumProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid


class ComputeNodeResize(ComputeNode):
    """
    Resize/Scale a Grid to a new resolution.
    
    Grid Architecture:
    - Input: Grid (from Capture, ImageInput, or another Resize)
    - Output: Grid at new resolution
    - Supports 2D and 3D grids
    - Uses bilinear/trilinear interpolation
    """
    bl_idname = 'ComputeNodeResize'
    bl_label = 'Resize'
    bl_icon = 'FULLSCREEN_ENTER'
    
    # Dimensions mode (consistent with Capture)
    dimensions: EnumProperty(
        name="Dimensions",
        items=[
            ('2D', "2D", "Image: width × height"),
            ('3D', "3D", "Volume: width × height × depth"),
        ],
        default='2D',
        description="Grid dimensionality"
    )
    
    # Target dimensions (same naming as Capture)
    width: IntProperty(
        name="Width",
        default=512,
        min=1,
        max=16384,
        description="Target width in pixels/voxels"
    )
    
    height: IntProperty(
        name="Height", 
        default=512,
        min=1,
        max=16384,
        description="Target height in pixels/voxels"
    )
    
    depth: IntProperty(
        name="Depth",
        default=64,
        min=1,
        max=2048,
        description="Target depth in voxels (for 3D)"
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
        self.inputs.new('ComputeSocketGrid', "Grid")
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dimensions")
        col = layout.column(align=True)
        col.prop(self, "width")
        col.prop(self, "height")
        if self.dimensions == '3D':
            col.prop(self, "depth")
        layout.prop(self, "interpolation")


node_classes = [ComputeNodeResize]

