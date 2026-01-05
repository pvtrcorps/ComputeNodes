
import bpy
from bpy.props import EnumProperty, BoolProperty
from ..nodetree import ComputeNode
from ..sockets import set_socket_shape

class ComputeNodeNoiseTexture(ComputeNode):
    bl_idname = 'ComputeNodeNoiseTexture'
    bl_label = 'Noise Texture'
    bl_icon = 'TEXTURE'
    node_category = "TEXTURE"
    
    def update_sockets(self, context):
        self.inputs['Vector'].hide = (self.dim_mode == '1D')
        self.inputs['W'].hide = (self.dim_mode not in {'1D', '4D'})

    dim_mode: EnumProperty(
        name="Dimensions",
        items=[
            ('1D', "1D", "Use 1D noise"),
            ('2D', "2D", "Use 2D noise"),
            ('3D', "3D", "Use 3D noise"),
            ('4D', "4D", "Use 4D noise"),
        ],
        default='3D',
        update=update_sockets
    )
    
    normalize: BoolProperty(
        name="Normalize",
        description="If true, normalize the noise output to a 0.0 to 1.0 range",
        default=True,
        update=lambda s,c: s.update()
    )
    
    def init(self, context):
        self.apply_node_color()
        # Inputs accept both single values and fields (dynamic)
        vec = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(vec, 'dynamic')
        w = self.inputs.new('NodeSocketFloat', "W")
        set_socket_shape(w, 'dynamic')
        scale = self.inputs.new('NodeSocketFloat', "Scale")
        scale.default_value = 5.0
        set_socket_shape(scale, 'dynamic')
        detail = self.inputs.new('NodeSocketFloat', "Detail")
        detail.default_value = 2.0
        set_socket_shape(detail, 'dynamic')
        rough = self.inputs.new('NodeSocketFloat', "Roughness")
        rough.default_value = 0.5
        set_socket_shape(rough, 'dynamic')
        lac = self.inputs.new('NodeSocketFloat', "Lacunarity")
        lac.default_value = 2.0
        set_socket_shape(lac, 'dynamic')
        offset = self.inputs.new('NodeSocketFloat', "Offset")
        offset.default_value = 0.0
        set_socket_shape(offset, 'dynamic')
        
        # Outputs are always Fields (per-pixel procedural)
        fac = self.outputs.new('NodeSocketFloat', "Fac")
        set_socket_shape(fac, 'field')
        col = self.outputs.new('NodeSocketColor', "Color")
        set_socket_shape(col, 'field')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dim_mode", text="")
        layout.prop(self, "normalize")
        
    def draw_label(self):
        self._draw_node_color()
        return "Noise Texture"

class ComputeNodeWhiteNoise(ComputeNode):
    bl_idname = 'ComputeNodeWhiteNoise'
    bl_label = 'White Noise'
    bl_icon = 'TEXTURE'
    node_category = "TEXTURE"
    
    def update_sockets(self, context):
        self.inputs['Vector'].hide = (self.dim_mode == '1D')
        self.inputs['W'].hide = (self.dim_mode not in {'1D', '4D'})

    dim_mode: EnumProperty(
        name="Dimensions",
        items=[
            ('1D', "1D", "Use 1D noise"),
            ('2D', "2D", "Use 2D noise"),
            ('3D', "3D", "Use 3D noise"),
            ('4D', "4D", "Use 4D noise"),
        ],
        default='3D',
        update=update_sockets
    )
    
    def init(self, context):
        self.apply_node_color()
        vec = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(vec, 'dynamic')
        w = self.inputs.new('NodeSocketFloat', "W")
        set_socket_shape(w, 'dynamic')
        
        # Outputs are Fields
        val = self.outputs.new('NodeSocketFloat', "Value")
        set_socket_shape(val, 'field')
        col = self.outputs.new('NodeSocketColor', "Color")
        set_socket_shape(col, 'field')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dim_mode", text="")
        

    def draw_label(self):
        self._draw_node_color()
        return "White Noise"

class ComputeNodeVoronoiTexture(ComputeNode):
    bl_idname = 'ComputeNodeVoronoiTexture'
    bl_label = 'Voronoi Texture'
    bl_icon = 'TEXTURE'
    node_category = "TEXTURE"
    
    def update_sockets(self, context):
        # Inputs
        self.inputs['Vector'].hide = (self.dim_mode == '1D')
        self.inputs['W'].hide = (self.dim_mode not in {'1D', '4D'})
        self.inputs['Smoothness'].hide = (self.feature != 'SMOOTH_F1')
        self.inputs['Exponent'].hide = (self.metric != 'MINKOWSKI')
        
        # Outputs
        show_col_pos = (self.feature in {'F1', 'F2', 'SMOOTH_F1'})
        self.outputs['Color'].hide = not show_col_pos
        self.outputs['Position'].hide = not show_col_pos
        self.outputs['Radius'].hide = (self.feature != 'N_SPHERE_RADIUS')
        self.outputs['W'].hide = True # Usually not used in standard Voronoi node?

    dim_mode: EnumProperty(
        name="Dimensions",
        items=[
            ('1D', "1D", "Use 1D noise"),
            ('2D', "2D", "Use 2D noise"),
            ('3D', "3D", "Use 3D noise"),
            ('4D', "4D", "Use 4D noise"),
        ],
        default='3D',
        update=update_sockets
    )
    
    feature: EnumProperty(
        name="Feature",
        items=[
            ('F1', "F1", "F1"),
            ('F2', "F2", "F2"),
            ('SMOOTH_F1', "Smooth F1", "Smooth F1"),
            ('DISTANCE_TO_EDGE', "Distance to Edge", "Distance to Edge"),
            ('N_SPHERE_RADIUS', "N-Sphere Radius", "N-Sphere Radius"),
        ],
        default='F1',
        update=update_sockets
    )
    
    metric: EnumProperty(
        name="Metric",
        items=[
            ('EUCLIDEAN', "Euclidean", "Euclidean"),
            ('MANHATTAN', "Manhattan", "Manhattan"),
            ('CHEBYCHEV', "Chebychev", "Chebychev"),
            ('MINKOWSKI', "Minkowski", "Minkowski"),
        ],
        default='EUCLIDEAN',
        update=update_sockets
    )
    
    normalize: BoolProperty(
        name="Normalize",
        description="Normalize the distance output",
        default=False,
        update=lambda s,c: s.update()
    )
    
    def init(self, context):
        self.apply_node_color()
        # Inputs are dynamic
        vec = self.inputs.new('NodeSocketVector', "Vector")
        set_socket_shape(vec, 'dynamic')
        w = self.inputs.new('NodeSocketFloat', "W")
        set_socket_shape(w, 'dynamic')
        scale = self.inputs.new('NodeSocketFloat', "Scale")
        scale.default_value = 5.0
        set_socket_shape(scale, 'dynamic')
        detail = self.inputs.new('NodeSocketFloat', "Detail")
        detail.default_value = 0.0
        set_socket_shape(detail, 'dynamic')
        rough = self.inputs.new('NodeSocketFloat', "Roughness")
        rough.default_value = 0.5
        set_socket_shape(rough, 'dynamic')
        lac = self.inputs.new('NodeSocketFloat', "Lacunarity")
        lac.default_value = 2.0
        set_socket_shape(lac, 'dynamic')
        smooth = self.inputs.new('NodeSocketFloat', "Smoothness")
        smooth.default_value = 1.0
        set_socket_shape(smooth, 'dynamic')
        exp = self.inputs.new('NodeSocketFloat', "Exponent")
        exp.default_value = 1.0
        set_socket_shape(exp, 'dynamic')
        rand = self.inputs.new('NodeSocketFloat', "Randomness")
        rand.default_value = 1.0
        set_socket_shape(rand, 'dynamic')
        
        # Outputs are Fields (per-pixel procedural)
        dist = self.outputs.new('NodeSocketFloat', "Distance")
        set_socket_shape(dist, 'field')
        col = self.outputs.new('NodeSocketColor', "Color")
        set_socket_shape(col, 'field')
        pos = self.outputs.new('NodeSocketVector', "Position")
        set_socket_shape(pos, 'field')
        w_out = self.outputs.new('NodeSocketFloat', "W")
        set_socket_shape(w_out, 'field')
        rad = self.outputs.new('NodeSocketFloat', "Radius")
        set_socket_shape(rad, 'field')
        
        self.update_sockets(context)
        
    def draw_buttons(self, context, layout):
        layout.prop(self, "dim_mode", text="")
        layout.prop(self, "feature", text="")
        layout.prop(self, "metric", text="")
        layout.prop(self, "normalize")
        
    def draw_label(self):
        self._draw_node_color()
        return "Voronoi Texture"
