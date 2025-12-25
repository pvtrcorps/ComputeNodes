# Capture Node - Materializes a Field to a Grid at specified resolution
import bpy
from bpy.props import IntProperty
from ..nodetree import ComputeNode


class ComputeNodeCapture(ComputeNode):
    """
    Capture (Materialize) a procedural field to a Grid.
    
    This node evaluates a Field (lazy procedural data) at every point of
    a grid with the specified resolution, creating materialized data.
    
    The output Grid can then be sampled by other nodes (Sample, etc.)
    at arbitrary coordinates with interpolation.
    
    Grid Architecture:
    - Grid2D: width x height, depth=1 (current implementation)
    - Grid3D: width x height x depth (future)
    - Grid1D: width only, height=1, depth=1 (future)
    """
    bl_idname = 'ComputeNodeCapture'
    bl_label = 'Capture'
    bl_icon = 'RENDERLAYERS'
    
    # Output resolution
    width: IntProperty(
        name="Width",
        default=512,
        min=1,
        max=16384,
        description="Grid width in pixels"
    )
    
    height: IntProperty(
        name="Height", 
        default=512,
        min=1,
        max=16384,
        description="Grid height in pixels"
    )
    
    def init(self, context):
        # Input: procedural field/color value
        self.inputs.new('NodeSocketColor', "Field")
        # Output: Grid handle (cyan socket)
        self.outputs.new('ComputeSocketGrid', "Grid")
        
    def draw_buttons(self, context, layout):
        col = layout.column(align=True)
        col.prop(self, "width")
        col.prop(self, "height")


# Export for registration
node_classes = [ComputeNodeCapture]

