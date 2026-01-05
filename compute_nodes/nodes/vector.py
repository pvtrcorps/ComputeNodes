import bpy
from bpy.props import EnumProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape

class ComputeNodeVectorMath(ComputeNode):
    bl_idname = 'ComputeNodeVectorMath'
    bl_label = 'Vector Math'
    bl_icon = 'ADD'
    node_category = "VECTOR"
    
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
        # All inputs/outputs are dynamic (adapt to data structure)
        v0 = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(v0, 'dynamic')
        v1 = self.inputs.new('NodeSocketVector', "Vector") # Vector_001
        set_socket_shape(v1, 'dynamic')
        v2 = self.inputs.new('NodeSocketVector', "Vector") # Vector_002
        set_socket_shape(v2, 'dynamic')
        sc = self.inputs.new('NodeSocketFloat', "Scale")   # Scale / IOR
        set_socket_shape(sc, 'dynamic')
        
        out_v = self.outputs.new('NodeSocketVector', "Vector")
        set_socket_shape(out_v, 'dynamic')
        out_f = self.outputs.new('NodeSocketFloat', "Value")
        set_socket_shape(out_f, 'dynamic')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "operation")
        
    def draw_label(self):
        self._draw_node_color()
        return self.operation.replace("_", " ").title()


class ComputeNodeVectorRotate(ComputeNode):
    bl_idname = 'ComputeNodeVectorRotate'
    bl_label = 'Vector Rotate'
    bl_icon = 'FORCE_MAGNETIC'
    node_category = "VECTOR"
    
    rotation_type: EnumProperty(
        name="Rotation Type",
        items=[
            ('AXIS_ANGLE', "Axis Angle", "Rotate around an arbitrary axis"),
            ('X_AXIS', "X Axis", "Rotate around X axis"),
            ('Y_AXIS', "Y Axis", "Rotate around Y axis"),
            ('Z_AXIS', "Z Axis", "Rotate around Z axis"),
            ('EULER_XYZ', "Euler", "Rotate using Euler angles"),
        ],
        default='AXIS_ANGLE',
        update=lambda s,c: s.update_sockets(c)
    )
    
    invert: bpy.props.BoolProperty(name="Invert", default=False)
    
    def update_sockets(self, context):
        mode = self.rotation_type
        
        # Axis input
        if 'Axis' in self.inputs:
            self.inputs['Axis'].hide = (mode != 'AXIS_ANGLE')
            
        # Angle input
        if 'Angle' in self.inputs:
            self.inputs['Angle'].hide = (mode == 'EULER_XYZ')
            
        # Rotation (Euler) input
        if 'Rotation' in self.inputs:
            self.inputs['Rotation'].hide = (mode != 'EULER_XYZ')
            
    def init(self, context):
        v = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(v, 'dynamic')
        c = self.inputs.new('NodeSocketVector', "Center")
        c.default_value = (0.0, 0.0, 0.0)
        set_socket_shape(c, 'dynamic')
        ax = self.inputs.new('NodeSocketVector', "Axis")
        ax.default_value = (0.0, 0.0, 1.0)
        set_socket_shape(ax, 'dynamic')
        ang = self.inputs.new('NodeSocketFloat', "Angle")
        ang.default_value = 0.0
        set_socket_shape(ang, 'dynamic')
        rot = self.inputs.new('NodeSocketVector', "Rotation")
        rot.default_value = (0.0, 0.0, 0.0)
        set_socket_shape(rot, 'dynamic')
        
        out = self.outputs.new('NodeSocketVector', "Vector")
        set_socket_shape(out, 'dynamic')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "rotation_type", text="")
        layout.prop(self, "invert")
        
    def draw_label(self):
        self._draw_node_color()
        return "Vector Rotate"
