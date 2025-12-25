# Distort Node - High-level helper for displacing/distorting values
import bpy
from bpy.props import IntProperty, FloatProperty
from ..nodetree import ComputeNode


class ComputeNodeDistort(ComputeNode):
    """
    Distort/Warp values using a displacement vector.
    
    This is a HIGH-LEVEL helper node that automatically handles the complexity
    of sampling with offset. If the input is procedural (not a texture), it 
    automatically "bakes" it to an intermediate texture first.
    
    For low-level control, use Rasterize + Sample nodes directly.
    
    Algorithm:
    1. If input is procedural -> auto-bake to texture at specified resolution
    2. Sample texture at (position + offset * strength)
    3. Output distorted color
    """
    bl_idname = 'ComputeNodeDistort'
    bl_label = 'Distort'
    bl_icon = 'MOD_WARP'
    
    # Resolution for auto-bake
    width: IntProperty(
        name="Width",
        default=512,
        min=1,
        max=16384,
        description="Resolution for intermediate texture (when input is procedural)"
    )
    
    height: IntProperty(
        name="Height", 
        default=512,
        min=1,
        max=16384,
        description="Resolution for intermediate texture (when input is procedural)"
    )
    
    # Distortion strength
    strength: FloatProperty(
        name="Strength",
        default=0.1,
        min=-10.0,
        max=10.0,
        description="Distortion strength multiplier"
    )
    
    def init(self, context):
        # Input: color to distort (yellow)
        self.inputs.new('NodeSocketColor', "Color")
        # Input: offset vector for distortion (blue)
        self.inputs.new('NodeSocketVector', "Offset")
        # Output: distorted color (yellow)
        self.outputs.new('NodeSocketColor', "Color")
        
    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "width")
        col.prop(self, "height")
        layout.prop(self, "strength")


# Export for registration
node_classes = [ComputeNodeDistort]
