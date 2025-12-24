import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode

class ComputeNodeVectorMath(ComputeNode):
    bl_idname = 'ComputeNodeVectorMath'
    bl_label = 'Vector Math'
    bl_icon = 'ADD'
    
    operation: EnumProperty(
        name="Operation",
        items=[
            ('ADD', "Add", "A + B"),
            ('SUB', "Subtract", "A - B"),
            ('MUL', "Multiply", "A * B"),
            ('DIV', "Divide", "A / B"),
            ('MULTIPLY_ADD', "Multiply Add", "A * B + C"),
            ('CROSS', "Cross Product", "A x B"),
            ('PROJECT', "Project", "Project A onto B"),
            ('REFLECT', "Reflect", "Reflect A around B"),
            ('REFRACT', "Refract", "Refract A through B with IOR C"),
            ('FACEFORWARD', "Faceforward", "Faceforward A relative to B and C"),
            ('DOT', "Dot Product", "A . B"),
            ('DISTANCE', "Distance", "Distance between A and B"),
            ('LENGTH', "Length", "Length of A"),
            ('SCALE', "Scale", "A * Scale"),
            ('NORMALIZE', "Normalize", "Normalize A"),
            ('ABS', "Absolute", "abs(A)"),
            ('MIN', "Minimum", "min(A, B)"),
            ('MAX', "Maximum", "max(A, B)"),
            ('FLOOR', "Floor", "floor(A)"),
            ('CEIL', "Ceil", "ceil(A)"),
            ('FRACT', "Fraction", "fract(A)"),
            ('MODULO', "Modulo", "A % B"),
            ('WRAP', "Wrap", "Wrap A between Min B and Max C"),
            ('SNAP', "Snap", "Snap A to increment B"),
            ('SINE', "Sine", "sin(A)"),
            ('COSINE', "Cosine", "cos(A)"),
            ('TANGENT', "Tangent", "tan(A)"),
        ],
        default='ADD',
        update=lambda s,c: s.update_sockets(c)
    )
    
    def update_sockets(self, context):
        op = self.operation
        
        # 1-Input (Unary)
        unary_ops = {
            'LENGTH', 'NORMALIZE', 'ABS', 'FLOOR', 'CEIL', 'FRACT', 
            'SINE', 'COSINE', 'TANGENT'
        }
        
        # 3-Input (Ternary)
        ternary_ops = {
            'MULTIPLY_ADD', 'WRAP', 'REFRACT', 'FACEFORWARD'
        }
        
        # Scale: Vec * Float. Hide Vec2 input, show Scale input?
        # Standard: Vector, Vector.
        # Scale uses Input[0] (Vector) and Input[3] (Scale Float).
        
        show_input_1 = op not in unary_ops
        show_input_2 = op in ternary_ops # Vector 3
        show_scale = (op == 'SCALE')
        show_ior = (op == 'REFRACT') # Usually 'IOR' is Input[2] (Float) or [3]?
        # Blender: Refract Inputs: Vector, Normal, IOR.
        # My node: Vector, Vector. I need more sockets.
        
        # Update visibility
        if 'Vector_001' in self.inputs:
             self.inputs['Vector_001'].hide = not show_input_1 or op == 'SCALE' 
        
        if 'Vector_002' in self.inputs:
             self.inputs['Vector_002'].hide = not show_input_2
             
        if 'Scale' in self.inputs:
             self.inputs['Scale'].hide = not (show_scale or show_ior)
             # Reuse Scale input for IOR? Or separate? 
             # Let's rename if used for IOR
             if show_ior: self.inputs['Scale'].name = "IOR"
             elif show_scale: self.inputs['Scale'].name = "Scale"

        # Outputs
        # Some output Float, some Vector.
        # Vector Output: Vector Index 0
        # Float Output: Value Index 1
        
        float_out_ops = {'DOT', 'DISTANCE', 'LENGTH'}
        
        if 'Value' in self.outputs:
             self.outputs['Value'].hide = op not in float_out_ops
        if 'Vector' in self.outputs:
             self.outputs['Vector'].hide = op in float_out_ops
    
    def init(self, context):
        self.inputs.new('NodeSocketVector', "Vector")
        self.inputs.new('NodeSocketVector', "Vector") # Vector_001
        self.inputs.new('NodeSocketVector', "Vector") # Vector_002
        self.inputs.new('NodeSocketFloat', "Scale")   # Scale / IOR
        
        self.outputs.new('NodeSocketVector', "Vector")
        self.outputs.new('NodeSocketFloat', "Value")
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "operation")
        
    def draw_label(self):
        return self.operation.replace("_", " ").title()
