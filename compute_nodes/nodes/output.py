import bpy
from bpy.props import StringProperty, IntProperty, EnumProperty
from ..nodetree import ComputeNode

FORMAT_ITEMS = [
    ('RGBA8', "RGBA 8-bit", "Standard 8-bit per channel"),
    ('RGBA16F', "RGBA 16-bit Float", "Half precision floating point"),
    ('RGBA32F', "RGBA 32-bit Float", "Full precision floating point"),
    ('R32F', "Grayscale 32-bit", "Single channel float"),
]


class ComputeNodeOutput(ComputeNode):
    """Output node that auto-creates/writes to a Blender Image datablock."""
    bl_idname = 'ComputeNodeOutput'
    bl_label = 'Output'
    bl_icon = 'OUTPUT'
    
    output_name: StringProperty(
        name="Name",
        description="Name of the output image (will be created if it doesn't exist)",
        default="ComputeOutput"
    )
    
    width: IntProperty(
        name="Width",
        description="Width of the output image in pixels",
        default=1024,
        min=1,
        max=16384,
        subtype='PIXEL'
    )
    
    height: IntProperty(
        name="Height", 
        description="Height of the output image in pixels",
        default=1024,
        min=1,
        max=16384,
        subtype='PIXEL'
    )
    
    format: EnumProperty(
        name="Format",
        description="Pixel format of the output image",
        items=FORMAT_ITEMS,
        default='RGBA32F'
    )
    
    def init(self, context):
        self.inputs.new('NodeSocketColor', "Color")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "output_name", text="")
        row = layout.row(align=True)
        row.prop(self, "width", text="W")
        row.prop(self, "height", text="H")
        layout.prop(self, "format")
    
    def update(self):
        pass
