import bpy
from bpy.props import PointerProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape


class ComputeNodeImageInput(ComputeNode):
    """Load a Blender image as a Grid (sampleable data)."""
    bl_idname = 'ComputeNodeImageInput'
    bl_label = 'Image Input'
    node_category = "INPUT"
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        self.apply_node_color()
        # Output: Grid handle (VOLUME_GRID shape)
        grid_out = self.outputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_out, 'grid')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageWrite(ComputeNode):
    """Write to a Blender image datablock (storage target)."""
    bl_idname = 'ComputeNodeImageWrite'
    bl_label = 'Image Write (Storage)'
    node_category = "OUTPUT"
    
    image: PointerProperty(type=bpy.types.Image, name="Image")
    
    def init(self, context):
        self.apply_node_color()
        # Output: Grid handle for chaining
        grid_out = self.outputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_out, 'grid')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "image", open="image.open")


class ComputeNodeImageInfo(ComputeNode):
    """Get information about a Grid (dimensions, size)."""
    bl_idname = 'ComputeNodeImageInfo'
    bl_label = 'Grid Info'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # Input: Grid handle
        grid_in = self.inputs.new('ComputeSocketGrid', "Grid")
        set_socket_shape(grid_in, 'grid')
        # Outputs: Single values (grid metadata, not per-pixel)
        w = self.outputs.new('NodeSocketInt', "Width")
        set_socket_shape(w, 'single')
        h = self.outputs.new('NodeSocketInt', "Height")
        set_socket_shape(h, 'single')
        d = self.outputs.new('NodeSocketInt', "Depth")  # Returns 1 for 2D grids
        set_socket_shape(d, 'single')
        dim = self.outputs.new('NodeSocketInt', "Dimensionality")  # 1, 2, or 3
        set_socket_shape(dim, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label


class ComputeNodeValue(ComputeNode):
    """Output a constant float value."""
    bl_idname = 'ComputeNodeValue'
    bl_label = 'Value'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        # Output: Single constant value
        out = self.outputs.new('NodeSocketFloat', "Value")
        out.default_value = 0.5
        set_socket_shape(out, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label

    def draw_buttons(self, context, layout):
        if self.outputs:
             layout.prop(self.outputs[0], "default_value", text="Value")



class ComputeNodeInputVector(ComputeNode):
    """Output a constant vector value."""
    bl_idname = 'ComputeNodeInputVector'
    bl_label = 'Vector'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        out = self.outputs.new('NodeSocketVector', "Vector")
        out.default_value = (0.0, 0.0, 0.0)
        set_socket_shape(out, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        # Draw explicit vector fields
        if self.outputs:
            col = layout.column(align=True)
            socket = self.outputs[0]
            col.prop(socket, "default_value", index=0, text="X")
            col.prop(socket, "default_value", index=1, text="Y")
            col.prop(socket, "default_value", index=2, text="Z")


class ComputeNodeInputColor(ComputeNode):
    """Output a constant color value."""
    bl_idname = 'ComputeNodeInputColor'
    bl_label = 'Color'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        out = self.outputs.new('NodeSocketColor', "Color")
        out.default_value = (0.5, 0.5, 0.5, 1.0)
        set_socket_shape(out, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        if self.outputs:
            layout.template_color_picker(self.outputs[0], "default_value", value_slider=True)
            layout.prop(self.outputs[0], "default_value", text="")


class ComputeNodeInputBool(ComputeNode):
    """Output a constant boolean value."""
    bl_idname = 'ComputeNodeInputBool'
    bl_label = 'Boolean'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        out = self.outputs.new('NodeSocketBool', "Boolean")
        out.default_value = False
        set_socket_shape(out, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label

    def draw_buttons(self, context, layout):
        if self.outputs:
             layout.prop(self.outputs[0], "default_value", text="Value")


class ComputeNodeInputInt(ComputeNode):
    """Output a constant integer value."""
    bl_idname = 'ComputeNodeInputInt'
    bl_label = 'Integer'
    node_category = "INPUT"
    
    def init(self, context):
        self.apply_node_color()
        out = self.outputs.new('NodeSocketInt', "Integer")
        out.default_value = 0
        set_socket_shape(out, 'single')
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def draw_buttons(self, context, layout):
        if self.outputs:
             layout.prop(self.outputs[0], "default_value", text="Value")
