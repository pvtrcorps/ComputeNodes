
import bpy
from bpy.props import EnumProperty, FloatProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape


class ComputeNodeSeparateXYZ(ComputeNode):
    """Separates a vector into X, Y, Z components."""
    bl_idname = 'ComputeNodeSeparateXYZ'
    bl_label = 'Separate XYZ'
    node_category = "CONVERTER"
    
    def init(self, context):
        vec = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(vec, 'dynamic')
        
        x = self.outputs.new('NodeSocketFloat', "X")
        set_socket_shape(x, 'dynamic')
        y = self.outputs.new('NodeSocketFloat', "Y")
        set_socket_shape(y, 'dynamic')
        z = self.outputs.new('NodeSocketFloat', "Z")
        set_socket_shape(z, 'dynamic')
        
    def draw_buttons(self, context, layout):
        pass
        
    def draw_label(self):
        self._draw_node_color()
        return "Separate XYZ"


class ComputeNodeCombineXYZ(ComputeNode):
    """Combines X, Y, Z values into a vector."""
    bl_idname = 'ComputeNodeCombineXYZ'
    bl_label = 'Combine XYZ'
    node_category = "CONVERTER"
    
    def init(self, context):
        x = self.inputs.new('NodeSocketFloat', "X")
        set_socket_shape(x, 'dynamic')
        y = self.inputs.new('NodeSocketFloat', "Y")
        set_socket_shape(y, 'dynamic')
        z = self.inputs.new('NodeSocketFloat', "Z")
        set_socket_shape(z, 'dynamic')
        
        vec = self.outputs.new('NodeSocketVector', "Vector")
        set_socket_shape(vec, 'dynamic')
        
    def draw_buttons(self, context, layout):
        pass
        
    def draw_label(self):
        self._draw_node_color()
        return "Combine XYZ"


class ComputeNodeSeparateColor(ComputeNode):
    """Separates a color into its components based on mode."""
    bl_idname = 'ComputeNodeSeparateColor'
    bl_label = 'Separate Color'
    node_category = "CONVERTER"
    
    def update_sockets(self, context):
        """Update socket names based on color mode."""
        mode = self.mode
        
        if mode == 'RGB':
            names = ['Red', 'Green', 'Blue']
        elif mode == 'HSV':
            names = ['Hue', 'Saturation', 'Value']
        elif mode == 'HSL':
            names = ['Hue', 'Saturation', 'Lightness']
        else:
            names = ['Red', 'Green', 'Blue']
            
        # Update output socket names
        if len(self.outputs) >= 3:
            self.outputs[0].name = names[0]
            self.outputs[1].name = names[1]
            self.outputs[2].name = names[2]
    
    mode: EnumProperty(
        name="Mode",
        items=[
            ('RGB', "RGB", "Red, Green, Blue"),
            ('HSV', "HSV", "Hue, Saturation, Value"),
            ('HSL', "HSL", "Hue, Saturation, Lightness"),
        ],
        default='RGB',
        update=update_sockets
    )
    
    def init(self, context):
        col = self.inputs.new('NodeSocketColor', "Color")
        col.default_value = (0.8, 0.8, 0.8, 1.0)
        set_socket_shape(col, 'dynamic')
        
        r = self.outputs.new('NodeSocketFloat', "Red")
        set_socket_shape(r, 'dynamic')
        g = self.outputs.new('NodeSocketFloat', "Green")
        set_socket_shape(g, 'dynamic')
        b = self.outputs.new('NodeSocketFloat', "Blue")
        set_socket_shape(b, 'dynamic')
        a = self.outputs.new('NodeSocketFloat', "Alpha")
        set_socket_shape(a, 'dynamic')
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "mode", text="")
        
    def draw_label(self):
        self._draw_node_color()
        return f"Separate Color"


class ComputeNodeCombineColor(ComputeNode):
    """Combines components into a color based on mode."""
    bl_idname = 'ComputeNodeCombineColor'
    bl_label = 'Combine Color'
    node_category = "CONVERTER"
    
    def update_sockets(self, context):
        """Update socket names based on color mode."""
        mode = self.mode
        
        if mode == 'RGB':
            names = ['Red', 'Green', 'Blue']
        elif mode == 'HSV':
            names = ['Hue', 'Saturation', 'Value']
        elif mode == 'HSL':
            names = ['Hue', 'Saturation', 'Lightness']
        else:
            names = ['Red', 'Green', 'Blue']
            
        # Update input socket names
        if len(self.inputs) >= 3:
            self.inputs[0].name = names[0]
            self.inputs[1].name = names[1]
            self.inputs[2].name = names[2]
    
    mode: EnumProperty(
        name="Mode",
        items=[
            ('RGB', "RGB", "Red, Green, Blue"),
            ('HSV', "HSV", "Hue, Saturation, Value"),
            ('HSL', "HSL", "Hue, Saturation, Lightness"),
        ],
        default='RGB',
        update=update_sockets
    )
    
    def init(self, context):
        r = self.inputs.new('NodeSocketFloat', "Red")
        set_socket_shape(r, 'dynamic')
        g = self.inputs.new('NodeSocketFloat', "Green")
        set_socket_shape(g, 'dynamic')
        b = self.inputs.new('NodeSocketFloat', "Blue")
        set_socket_shape(b, 'dynamic')
        a = self.inputs.new('NodeSocketFloat', "Alpha")
        a.default_value = 1.0
        set_socket_shape(a, 'dynamic')
        
        col = self.outputs.new('NodeSocketColor', "Color")
        set_socket_shape(col, 'dynamic')
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "mode", text="")
        
    def draw_label(self):
        self._draw_node_color()
        return f"Combine Color"


class ComputeNodeMapRange(ComputeNode):
    """Maps a value from one range to another with various interpolation modes."""
    bl_idname = 'ComputeNodeMapRange'
    bl_label = 'Map Range'
    node_category = "CONVERTER"
    
    def update_sockets(self, context):
        """Update socket visibility based on data type and interpolation."""
        is_vector = self.data_type == 'FLOAT_VECTOR'
        is_stepped = self.interpolation_type == 'STEPPED'
        
        # Hide/show float vs vector sockets
        # Float sockets
        for name in ['Value', 'From Min', 'From Max', 'To Min', 'To Max']:
            if name in self.inputs:
                self.inputs[name].hide = is_vector
        if 'Result' in self.outputs:
            self.outputs['Result'].hide = is_vector
            
        # Vector sockets
        for name in ['Vector', 'From Min (Vec)', 'From Max (Vec)', 'To Min (Vec)', 'To Max (Vec)']:
            if name in self.inputs:
                self.inputs[name].hide = not is_vector
        if 'Vector Result' in self.outputs:
            self.outputs['Vector Result'].hide = not is_vector
        
        # Steps socket (only for STEPPED mode, always float)
        if 'Steps' in self.inputs:
            self.inputs['Steps'].hide = not is_stepped
    
    data_type: EnumProperty(
        name="Data Type",
        items=[
            ('FLOAT', "Float", "Use float values"),
            ('FLOAT_VECTOR', "Vector", "Use vector values"),
        ],
        default='FLOAT',
        update=update_sockets
    )
    
    interpolation_type: EnumProperty(
        name="Interpolation Type",
        items=[
            ('LINEAR', "Linear", "Linear interpolation"),
            ('STEPPED', "Stepped Linear", "Stepped linear interpolation"),
            ('SMOOTHSTEP', "Smooth Step", "Smooth Hermite interpolation"),
            ('SMOOTHERSTEP', "Smoother Step", "Ken Perlin's smoother step"),
        ],
        default='LINEAR',
        update=update_sockets
    )
    
    clamp: BoolProperty(
        name="Clamp",
        description="Clamp result to target range",
        default=False,
        update=lambda s, c: s.update()
    )
    
    def init(self, context):
        # Float sockets
        self.inputs.new('NodeSocketFloat', "Value")
        self.inputs.new('NodeSocketFloat', "From Min").default_value = 0.0
        self.inputs.new('NodeSocketFloat', "From Max").default_value = 1.0
        self.inputs.new('NodeSocketFloat', "To Min").default_value = 0.0
        self.inputs.new('NodeSocketFloat', "To Max").default_value = 1.0
        
        # Vector sockets (hidden by default)
        self.inputs.new('NodeSocketVector', "Vector")
        self.inputs.new('NodeSocketVector', "From Min (Vec)").default_value = (0.0, 0.0, 0.0)
        self.inputs.new('NodeSocketVector', "From Max (Vec)").default_value = (1.0, 1.0, 1.0)
        self.inputs.new('NodeSocketVector', "To Min (Vec)").default_value = (0.0, 0.0, 0.0)
        self.inputs.new('NodeSocketVector', "To Max (Vec)").default_value = (1.0, 1.0, 1.0)
        
        # Steps (only for stepped mode)
        self.inputs.new('NodeSocketFloat', "Steps").default_value = 4.0
        
        # Outputs
        self.outputs.new('NodeSocketFloat', "Result")
        self.outputs.new('NodeSocketVector', "Vector Result")
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "data_type", text="")
        layout.prop(self, "interpolation_type", text="")
        layout.prop(self, "clamp")
        
    def draw_label(self):
        self._draw_node_color()
        return "Map Range"


class ComputeNodeClamp(ComputeNode):
    """Clamps a value between minimum and maximum."""
    bl_idname = 'ComputeNodeClamp'
    bl_label = 'Clamp'
    node_category = "CONVERTER"
    
    clamp_type: EnumProperty(
        name="Clamp Type",
        items=[
            ('MINMAX', "Min Max", "Clamp between min and max"),
            ('RANGE', "Range", "Clamp with auto-swap if min > max"),
        ],
        default='MINMAX',
        update=lambda s, c: s.update()
    )
    
    def init(self, context):
        self.inputs.new('NodeSocketFloat', "Value")
        self.inputs.new('NodeSocketFloat', "Min").default_value = 0.0
        self.inputs.new('NodeSocketFloat', "Max").default_value = 1.0
        
        self.outputs.new('NodeSocketFloat', "Result")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "clamp_type", text="")
        
    def draw_label(self):
        self._draw_node_color()
        return "Clamp"
