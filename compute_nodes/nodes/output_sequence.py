# Output Sequence Node - Exports Grid3D as Z-slice image sequence
import bpy
import os
from bpy.props import StringProperty, EnumProperty, IntProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid


FORMAT_ITEMS = [
    ('PNG', "PNG", "8/16-bit lossless, good for preview"),
    ('TIFF', "TIFF", "Scientific standard, multi-bit support"),
    ('OPEN_EXR', "OpenEXR", "32-bit float, HDR, industry standard"),
]


class ComputeNodeOutputSequence(ComputeNode):
    """Output Sequence - Writes Grid3D Z-slices as numbered image files.
    
    Industry-standard Z-stack export compatible with:
    - ImageJ/Fiji (TIFF stack import)
    - Houdini (COP image sequence)  
    - Nuke/Blender (Read with ####)
    
    Grid Architecture:
    - Input MUST be a Grid3D (from Capture with dimensions='3D')
    - Writes {depth} separate image files, one per Z-slice
    - Naming follows Blender convention: base_####.ext
    
    Naming Pattern:
        {directory}/{base_name}{slice:0{padding}d}.{ext}
        Example: //output/slice_0001.exr
    """
    bl_idname = 'ComputeNodeOutputSequence'
    bl_label = 'Output Sequence'
    bl_icon = 'FILE_MOVIE'
    node_category = "OUTPUT"
    
    base_name: StringProperty(
        name="Base Name",
        description="Base filename for slices (number will be appended)",
        default="slice_"
    )
    
    directory: StringProperty(
        name="Directory",
        description="Output directory (// for relative to .blend)",
        default="//output/",
        subtype='DIR_PATH'
    )
    
    format: EnumProperty(
        name="Format",
        description="Image format for slices",
        items=FORMAT_ITEMS,
        default='OPEN_EXR'
    )
    
    padding: IntProperty(
        name="Padding",
        description="Number of digits for slice numbering (e.g., 4 = 0001)",
        default=4,
        min=1,
        max=8
    )
    
    start_index: IntProperty(
        name="Start",
        description="First slice number (usually 0 or 1)",
        default=1,
        min=0
    )
    
    color_depth: EnumProperty(
        name="Color Depth",
        description="Bit depth for PNG/TIFF",
        items=[
            ('8', "8-bit", "Standard 8-bit per channel"),
            ('16', "16-bit", "High precision 16-bit"),
        ],
        default='16'
    )
    
    def init(self, context):
        # Grid input - requires Grid3D from Capture3D
        self.inputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "base_name", text="Name")
        layout.prop(self, "directory", text="")
        
        row = layout.row(align=True)
        row.prop(self, "format", text="")
        if self.format in ('PNG', 'TIFF'):
            row.prop(self, "color_depth", text="")
        
        row = layout.row(align=True)
        row.prop(self, "padding", text="Pad")
        row.prop(self, "start_index", text="Start")
        
        # Show preview
        ext = {'PNG': 'png', 'TIFF': 'tif', 'OPEN_EXR': 'exr'}[self.format]
        preview_first = f"{self.base_name}{self.start_index:0{self.padding}d}.{ext}"
        
        box = layout.box()
        box.scale_y = 0.7
        box.label(text=f"Preview: {preview_first}", icon='FILE_IMAGE')
        
        # Hint if not connected
        if not self.inputs[0].is_linked:
            layout.label(text="Connect a Grid3D", icon='INFO')
            layout.label(text="(Capture with 3D mode)")
    
    def update(self):
        pass


# Export for registration
node_classes = [ComputeNodeOutputSequence]
