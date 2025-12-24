import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode

class ComputeNodeSwitch(ComputeNode):
    bl_idname = 'ComputeNodeSwitch'
    bl_label = 'Switch'
    bl_icon = 'QUESTION'
    
    data_type: EnumProperty(
        name="Data Type",
        items=[
            ('FLOAT', "Float", "Scalar float"),
            ('VEC3', "Vector", "Vec3"),
            ('RGBA', "Color", "Vec4/Color"),
        ],
        default='FLOAT',
        update=lambda s,c: s.update()
    )
    
    def init(self, context):
        self.inputs.new('NodeSocketBool', "Switch") 
        self.inputs.new('NodeSocketFloat', "False")
        self.inputs.new('NodeSocketFloat', "True")
        self.outputs.new('NodeSocketFloat', "Output")
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "data_type", text="")
        
    def update(self):
         if self.data_type == 'FLOAT':
            self._update_sockets('NodeSocketFloat')
         elif self.data_type == 'VEC3':
            self._update_sockets('NodeSocketVector')
         elif self.data_type == 'RGBA':
            self._update_sockets('NodeSocketColor')

    def _update_sockets(self, socket_type):
        # Index 0 is Switch (Bool), 1 is False, 2 is True
        if len(self.inputs) > 2 and self.inputs[1].bl_idname != socket_type:
            # Recreate False/True inputs
            self.inputs.remove(self.inputs[2])
            self.inputs.remove(self.inputs[1])
            self.inputs.new(socket_type, "False")
            self.inputs.new(socket_type, "True")
            
            self.outputs.remove(self.outputs[0])
            self.outputs.new(socket_type, "Output")

class ComputeNodeMix(ComputeNode):
    bl_idname = 'ComputeNodeMix'
    bl_label = 'Mix'
    bl_icon = 'GROUP_VCOL'
    
    data_type: EnumProperty(
        name="Data Type",
        items=[
            ('FLOAT', "Float", "Scalar float"),
            ('VEC3', "Vector", "Vec3"),
            ('RGBA', "Color", "Vec4/Color"),
        ],
        default='FLOAT',
        update=lambda s,c: s.update()
    )
    
    # Blending modes for Color (and maybe Vector implied?)
    blend_type: EnumProperty(
        name="Blend Mode",
        items=[
            ('MIX', "Mix", "Linear Interpolation"),
            ('ADD', "Add", "A + B"),
            ('MULTIPLY', "Multiply", "A * B"),
            ('SUBTRACT', "Subtract", "A - B"),
            ('DIVIDE', "Divide", "A / B"),
        ],
        default='MIX',
        update=lambda s,c: s.update()
    )

    def init(self, context):
        self.inputs.new('NodeSocketFloat', "Factor")
        self.inputs.new('NodeSocketFloat', "A")
        self.inputs.new('NodeSocketFloat', "B")
        self.outputs.new('NodeSocketFloat', "Result")

    def draw_buttons(self, context, layout):
        layout.prop(self, "data_type", text="")
        if self.data_type == 'RGBA':
            layout.prop(self, "blend_type", text="")

    def update(self):
         if self.data_type == 'FLOAT':
            self._update_sockets('NodeSocketFloat')
         elif self.data_type == 'VEC3':
            self._update_sockets('NodeSocketVector')
         elif self.data_type == 'RGBA':
            self._update_sockets('NodeSocketColor')

    def _update_sockets(self, socket_type):
        # Index 0 is Factor, 1 is A, 2 is B
        if len(self.inputs) > 2 and self.inputs[1].bl_idname != socket_type:
            self.inputs.remove(self.inputs[2])
            self.inputs.remove(self.inputs[1])
            self.inputs.new(socket_type, "A")
            self.inputs.new(socket_type, "B")
            
            self.outputs.remove(self.outputs[0])
            self.outputs.new(socket_type, "Result")

class ComputeNodeRepeatInput(ComputeNode):
    bl_idname = 'ComputeNodeRepeatInput'
    bl_label = 'Repeat Zone (Input)'
    bl_icon = 'LOOP_FORWARDS'
    
    def init(self, context):
        self.inputs.new('NodeSocketInt', "Iterations")
        
        # Pairs: Initial (Input) -> Current (Output)
        self.inputs.new('NodeSocketFloat', "Initial Value")
        
        self.outputs.new('NodeSocketInt', "Iteration")
        self.outputs.new('NodeSocketFloat', "Current Value")
        
    def draw_buttons(self, context, layout):
        layout.label(text="Loop Start")

class ComputeNodeRepeatOutput(ComputeNode):
    bl_idname = 'ComputeNodeRepeatOutput'
    bl_label = 'Repeat Zone (Output)'
    bl_icon = 'LOOP_BACK'
    
    def init(self, context):
        # Pairs: Next (Input) -> Final (Output)
        self.inputs.new('NodeSocketFloat', "Next Value")
        self.outputs.new('NodeSocketFloat', "Final Result")
        
    def draw_buttons(self, context, layout):
        layout.label(text="Loop End")
