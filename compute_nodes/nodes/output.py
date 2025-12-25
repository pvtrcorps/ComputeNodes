import bpy
from bpy.props import StringProperty, EnumProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid

FORMAT_ITEMS = [
    ('RGBA8', "RGBA 8-bit", "Standard 8-bit per channel"),
    ('RGBA16F', "RGBA 16-bit Float", "Half precision floating point"),
    ('RGBA32F', "RGBA 32-bit Float", "Full precision floating point"),
    ('R32F', "Grayscale 32-bit", "Single channel float"),
]


class ComputeNodeOutputImage(ComputeNode):
    """Output Image - Writes a Grid to a Blender Image datablock.
    
    Grid Architecture:
    - Input MUST be a Grid (from Capture, Resize, ImageInput)
    - Does NOT define resolution - inherits from input Grid
    - If a Field (Color) is connected, extraction will error
    
    Future output nodes:
    - Output Volume: Grid3D → OpenVDB
    - Output Sequence: Grid2D[] → Image sequence
    - Output Attribute: Grid → Mesh attribute
    """
    bl_idname = 'ComputeNodeOutputImage'
    bl_label = 'Output Image'
    bl_icon = 'OUTPUT'
    
    output_name: StringProperty(
        name="Name",
        description="Name of the output image (will be created if it doesn't exist)",
        default="ComputeOutput"
    )
    
    format: EnumProperty(
        name="Format",
        description="Pixel format of the output image",
        items=FORMAT_ITEMS,
        default='RGBA32F'
    )
    
    def init(self, context):
        # Grid input - requires materialized grid (from Capture/Resize/ImageInput)
        self.inputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "output_name", text="")
        layout.prop(self, "format")
        
        # Show hint if no grid connected
        if not self.inputs[0].is_linked:
            layout.label(text="Connect a Grid", icon='INFO')
            layout.label(text="(use Capture for fields)")
    
    def update(self):
        pass

