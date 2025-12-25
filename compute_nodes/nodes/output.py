import bpy
from bpy.props import StringProperty, EnumProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid

FORMAT_ITEMS = [
    ('RGBA8', "RGBA 8-bit", "Standard 8-bit per channel"),
    ('RGBA16F', "RGBA 16-bit Float", "Half precision floating point"),
    ('RGBA32F', "RGBA 32-bit Float", "Full precision floating point"),
    ('R32F', "Grayscale 32-bit", "Single channel float"),
]

SAVE_MODE_ITEMS = [
    ('DATABLOCK', "Datablock", "Keep in Blender memory (default)"),
    ('SAVE', "Save to Disk", "Save to external file"),
    ('PACK', "Pack in .blend", "Pack image data into .blend file"),
]

FILE_FORMAT_ITEMS = [
    ('PNG', "PNG", "8/16-bit lossless"),
    ('OPEN_EXR', "OpenEXR", "32-bit float HDR"),
    ('TIFF', "TIFF", "Scientific/print standard"),
]


class ComputeNodeOutputImage(ComputeNode):
    """Output Image - Writes a Grid to a Blender Image datablock.
    
    Grid Architecture:
    - Input MUST be a Grid (from Capture, Resize, ImageInput)
    - Does NOT define resolution - inherits from input Grid
    
    Save Modes:
    - Datablock: Keep in Blender memory (editable in Image Editor)
    - Save to Disk: Write to external file
    - Pack in .blend: Embed in .blend file for portability
    """
    bl_idname = 'ComputeNodeOutputImage'
    bl_label = 'Output Image'
    bl_icon = 'OUTPUT'
    
    output_name: StringProperty(
        name="Name",
        description="Name of the output image",
        default="ComputeOutput"
    )
    
    format: EnumProperty(
        name="Format",
        description="Pixel format of the output image",
        items=FORMAT_ITEMS,
        default='RGBA32F'
    )
    
    save_mode: EnumProperty(
        name="Save Mode",
        description="How to handle the output image",
        items=SAVE_MODE_ITEMS,
        default='DATABLOCK'
    )
    
    # File output options (shown when save_mode == 'SAVE')
    filepath: StringProperty(
        name="File Path",
        description="Output file path (// for relative)",
        default="//output.exr",
        subtype='FILE_PATH'
    )
    
    file_format: EnumProperty(
        name="File Format",
        description="File format for saving",
        items=FILE_FORMAT_ITEMS,
        default='OPEN_EXR'
    )
    
    def init(self, context):
        self.inputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "output_name", text="")
        layout.prop(self, "format")
        
        # Save mode
        layout.prop(self, "save_mode", text="")
        
        # Show file options when saving
        if self.save_mode == 'SAVE':
            box = layout.box()
            box.prop(self, "filepath", text="")
            box.prop(self, "file_format", text="Format")
        elif self.save_mode == 'PACK':
            layout.label(text="Will pack after execution", icon='PACKAGE')
        
        # Hint if not connected
        if not self.inputs[0].is_linked:
            layout.label(text="Connect a Grid", icon='INFO')
    
    def update(self):
        pass

