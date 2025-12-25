# Blur Node - Gaussian blur for 2D and 3D Grids
import bpy
from bpy.props import IntProperty, FloatProperty, EnumProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid


class ComputeNodeBlur(ComputeNode):
    """Blur - Applies Gaussian blur to a Grid.
    
    Grid Architecture:
    - Input: Grid (from Capture, Resize, ImageInput)
    - Input: Radius (optional Field for variable blur)
    - Output: Grid (same dimensions as input)
    
    Features:
    - 2D and 3D grids (1D future)
    - Per-axis control (blur X, Y, Z independently)
    - Variable blur via Field input
    - Proper separable Gaussian kernel
    """
    bl_idname = 'ComputeNodeBlur'
    bl_label = 'Blur'
    bl_icon = 'MATFLUID'
    
    # Dimensions (consistent with Capture/Resize)
    dimensions: EnumProperty(
        name="Dimensions",
        items=[
            ('2D', "2D", "Image: width × height"),
            ('3D', "3D", "Volume: width × height × depth"),
        ],
        default='2D',
        description="Grid dimensionality"
    )
    
    # Blur radius
    radius: IntProperty(
        name="Radius",
        description="Blur radius in pixels (used when Radius socket not connected)",
        default=4,
        min=1,
        max=64
    )
    
    # Per-axis control
    blur_x: BoolProperty(
        name="X",
        description="Blur along X axis",
        default=True
    )
    
    blur_y: BoolProperty(
        name="Y", 
        description="Blur along Y axis",
        default=True
    )
    
    blur_z: BoolProperty(
        name="Z",
        description="Blur along Z axis (3D only)",
        default=True
    )
    
    # Iterations for stronger blur
    iterations: IntProperty(
        name="Iterations",
        description="Number of blur passes",
        default=1,
        min=1,
        max=8
    )
    
    def init(self, context):
        # Grid input
        self.inputs.new('ComputeSocketGrid', "Grid")
        # Radius field input (optional, for variable blur)
        self.inputs.new('NodeSocketFloat', "Radius")
        self.inputs["Radius"].hide_value = True  # Only show when connected
        
        # Output
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dimensions")
        layout.prop(self, "radius")
        
        # Per-axis toggles
        row = layout.row(align=True)
        row.prop(self, "blur_x", toggle=True)
        row.prop(self, "blur_y", toggle=True)
        if self.dimensions == '3D':
            row.prop(self, "blur_z", toggle=True)
        
        layout.prop(self, "iterations")
        
        # Hint for variable blur
        if self.inputs["Radius"].is_linked:
            layout.label(text="Variable blur from Field", icon='INFO')
    
    def update(self):
        pass


node_classes = [ComputeNodeBlur]
