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
    - Uses bilinear interpolation for smooth scaling
    
    This is a Grid→Grid operation, NOT for materializing fields.
    Use Capture to convert fields to grids first.
    """
    bl_idname = 'ComputeNodeResize'
    bl_label = 'Resize'
    bl_icon = 'FULLSCREEN_ENTER'
    
    # Target dimensions
    width: IntProperty(
        name="Width",
        default=512,
        min=1,
        max=16384,
        description="Target width"
    )
    
    height: IntProperty(
        name="Height", 
        default=512,
        min=1,
        max=16384,
        description="Target height"
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
        # Input: Grid (from Capture/ImageInput/etc)
        self.inputs.new('ComputeSocketGrid', "Grid")
        # Output: Grid at new resolution
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "width")
        col.prop(self, "height")
        layout.prop(self, "interpolation")


# Export for registration
node_classes = [ComputeNodeResize]


