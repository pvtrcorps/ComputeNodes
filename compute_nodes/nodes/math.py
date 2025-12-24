import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode

class ComputeNodeMath(ComputeNode):
    bl_idname = 'ComputeNodeMath'
    bl_label = 'Math'
    bl_icon = 'ADD'
    
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
        self.inputs.new('NodeSocketFloat', "Value")
        self.inputs.new('NodeSocketFloat', "Value") # Value_001
        self.inputs.new('NodeSocketFloat', "Value") # Value_002 (For Ternary)
        self.outputs.new('NodeSocketFloat', "Value")
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "operation")
        
    def draw_label(self):
        return self.operation.replace("_", " ").title()
