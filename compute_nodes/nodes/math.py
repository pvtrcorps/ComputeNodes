import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape

class ComputeNodeMath(ComputeNode):
    bl_idname = 'ComputeNodeMath'
    bl_label = 'Math'
    node_category = "MATH"
    
    operation: EnumProperty(
        name="Operation",
        items=[
            ('ADD', "Add", "A + B"),
            ('SUB', "Subtract", "A - B"),
            ('MUL', "Multiply", "A * B"),
            ('DIV', "Divide", "A / B"),
            ('MULTIPLY_ADD', "Multiply Add", "A * B + C"),
            ('SIN', "Sine", "sin(A)"),
            ('COS', "Cosine", "cos(A)"),
            ('TAN', "Tangent", "tan(A)"),
            ('ASIN', "Arcsine", "asin(A)"),
            ('ACOS', "Arccosine", "acos(A)"),
            ('ATAN', "Arctangent", "atan(A)"),
            ('ATAN2', "Arctangent 2", "atan2(A, B)"),
            ('SINH', "Hyperbolic Sine", "sinh(A)"),
            ('COSH', "Hyperbolic Cosine", "cosh(A)"),
            ('TANH', "Hyperbolic Tangent", "tanh(A)"),
            ('POW', "Power", "A ^ B"),
            ('LOG', "Logarithm", "log(A)"),
            ('SQRT', "Square Root", "sqrt(A)"),
            ('INVERSE_SQRT', "Inverse Square Root", "1 / sqrt(A)"),
            ('EXP', "Exponent", "exp(A)"),
            ('MIN', "Minimum", "min(A, B)"),
            ('MAX', "Maximum", "max(A, B)"),
            ('LESS_THAN', "Less Than", "A < B"),
            ('GREATER_THAN', "Greater Than", "A > B"),
            ('SIGN', "Sign", "sign(A)"),
            ('COMPARE', "Compare", "Compare A and B with Epsilon C"),
            ('SMOOTH_MIN', "Smooth Minimum", "smin(A, B, C)"),
            ('SMOOTH_MAX', "Smooth Maximum", "smax(A, B, C)"),
            ('ROUND', "Round", "round(A)"),
            ('FLOOR', "Floor", "floor(A)"),
            ('CEIL', "Ceil", "ceil(A)"),
            ('TRUNC', "Truncate", "trunc(A)"),
            ('FRACT', "Fraction", "fract(A)"),
            ('MODULO', "Modulo", "A % B"),
            ('WRAP', "Wrap", "Wrap A between Min B and Max C"),
            ('SNAP', "Snap", "Snap A to increment B"),
            ('PINGPONG', "Ping-Pong", "PingPong A with Scale B"),
            ('ABS', "Absolute", "abs(A)"),
            ('RADIANS', "Radians", "deg -> rad"),
            ('DEGREES', "Degrees", "rad -> deg"),
        ],
        default='ADD',
        update=lambda s,c: s.update_sockets(c)
    )
    
    def update_sockets(self, context):
        op = self.operation
        
        # 1-Input Operations (Unary)
        unary_ops = {
            'SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN', 'SINH', 'COSH', 'TANH',
            'LOG', 'SQRT', 'INVERSE_SQRT', 'EXP', 'SIGN', 'ROUND', 'FLOOR', 
            'CEIL', 'TRUNC', 'FRACT', 'ABS', 'RADIANS', 'DEGREES'
        }
        
        # 3-Input Operations (Ternary)
        ternary_ops = {
            'MULTIPLY_ADD', 'WRAP', 'COMPARE', 'SMOOTH_MIN', 'SMOOTH_MAX'
        }
        
        # Default is Binary (2 Inputs)
        
        # Determine visibility
        show_input_1 = op not in unary_ops
        show_input_2 = op in ternary_ops
        
        # Update Sockets
        if 'Value_001' in self.inputs:
             self.inputs['Value_001'].hide = not show_input_1
        if 'Value_002' in self.inputs:
             self.inputs['Value_002'].hide = not show_input_2

        # Special labels? 
        # Blender changes labels based on op (e.g. "Exponent" for POW, "Epsilon" for COMPARE)
        if op == 'POW':
             self.inputs[1].name = "Exponent"
        elif op == 'COMPARE':
             if 'Value_002' in self.inputs: self.inputs['Value_002'].name = "Epsilon"
        else:
             # Reset defaults if needed, though hard to track original names without metadata
             # For MVP, generic names 'Value' are usually fine or 'Value' 'Value_001' etc.
             pass
    
    def init(self, context):
        # All inputs/outputs are dynamic (adapt to connected data structure)
        in0 = self.inputs.new('NodeSocketFloat', "Value")
        set_socket_shape(in0, 'dynamic')
        in1 = self.inputs.new('NodeSocketFloat', "Value") # Value_001
        set_socket_shape(in1, 'dynamic')
        in2 = self.inputs.new('NodeSocketFloat', "Value") # Value_002 (For Ternary)
        set_socket_shape(in2, 'dynamic')
        out = self.outputs.new('NodeSocketFloat', "Value")
        set_socket_shape(out, 'dynamic')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "operation")
        
    def draw_label(self):
        self._draw_node_color()
        return self.operation.replace("_", " ").title()

class ComputeNodeBooleanMath(ComputeNode):
    bl_idname = 'ComputeNodeBooleanMath'
    bl_label = 'Boolean Math'
    node_category = "MATH"
    
    operation: EnumProperty(
        name="Operation",
        items=[
            ('AND', "And", "A and B"),
            ('OR', "Or", "A or B"),
            ('NOT', "Not", "Not A"),
            ('NAND', "Nand", "Not (A and B)"),
            ('NOR', "Nor", "Not (A or B)"),
            ('XNOR', "Xnor", "A == B"),
            ('XOR', "Xor", "A != B"),
            ('IMPLY', "Imply", "Not A or B"),
            ('NIMPLY', "Nimply", "A and Not B"),
        ],
        default='AND',
        update=lambda s,c: s.update_sockets(c)
    )
    
    def update_sockets(self, context):
        op = self.operation
        if 'Boolean_001' in self.inputs:
            self.inputs['Boolean_001'].hide = (op == 'NOT')
            
    def init(self, context):
        in0 = self.inputs.new('NodeSocketBool', "Boolean")
        set_socket_shape(in0, 'dynamic')
        in1 = self.inputs.new('NodeSocketBool', "Boolean") # Boolean_001
        set_socket_shape(in1, 'dynamic')
        out = self.outputs.new('NodeSocketBool', "Boolean")
        set_socket_shape(out, 'dynamic')
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "operation")
        
    def draw_label(self):
        self._draw_node_color()
        return self.operation.replace("_", " ").title()
