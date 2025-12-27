# Texture Node Handlers
# Handles: ComputeNodeNoiseTexture, ComputeNodeWhiteNoise, ComputeNodeVoronoiTexture

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_noise_texture(node, ctx):
    """Handle ComputeNodeNoiseTexture node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Inputs: [Vector, W, Scale, Detail, Roughness, Lacunarity, Offset]
    val_vec = get_socket_value(node.inputs[0]) 
    val_w = get_socket_value(node.inputs[1])
    val_scale = get_socket_value(node.inputs[2])
    val_detail = get_socket_value(node.inputs[3])
    val_rough = get_socket_value(node.inputs[4])
    val_lacu = get_socket_value(node.inputs[5])
    val_offset = get_socket_value(node.inputs[6])
    
    # Default Vector to Position
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    
    # Defaults for others
    if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
    if val_scale is None: val_scale = builder.constant(5.0, DataType.FLOAT)
    if val_detail is None: val_detail = builder.constant(2.0, DataType.FLOAT)
    if val_rough is None: val_rough = builder.constant(0.5, DataType.FLOAT)
    if val_lacu is None: val_lacu = builder.constant(2.0, DataType.FLOAT)
    if val_offset is None: val_offset = builder.constant(0.0, DataType.FLOAT)
    
    # Ensure types
    if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
    if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
    
    inputs = [val_vec, val_w, val_scale, val_detail, val_rough, val_lacu, val_offset]
    
    attrs = {
        'dimensions': str(node.dim_mode),     # Use dim_mode property, not dimensions!
        'normalize': bool(node.normalize)     # Convert to bool
    }
    
    op = builder.add_op(OpCode.NOISE, inputs, attrs)
    
    # Outputs: Fac (Float), Color (Color/Vec4)
    val_fac = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    op.add_output(val_fac)
    op.add_output(val_col)
    
    # Map Sockets
    key_fac = get_socket_key(node.outputs[0])
    socket_value_map[key_fac] = val_fac
    
    key_col = get_socket_key(node.outputs[1])
    socket_value_map[key_col] = val_col
    
    if output_socket_needed:
        req_key = get_socket_key(output_socket_needed)
        if req_key in socket_value_map:
            return socket_value_map[req_key]
    return val_fac


def handle_white_noise(node, ctx):
    """Handle ComputeNodeWhiteNoise node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    val_vec = get_socket_value(node.inputs[0]) 
    val_w = get_socket_value(node.inputs[1])
    
    # Defaults
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    
    if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
    
    if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
    if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
    
    inputs = [val_vec, val_w]
    attrs = {'dimensions': str(node.dim_mode)}  # Use dim_mode property!
    
    op = builder.add_op(OpCode.WHITE_NOISE, inputs, attrs)
    
    # Outputs
    val_val = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    op.add_output(val_val)
    op.add_output(val_col)
    
    key_val = get_socket_key(node.outputs[0])
    socket_value_map[key_val] = val_val
    
    key_col = get_socket_key(node.outputs[1])
    socket_value_map[key_col] = val_col
    
    if output_socket_needed:
        req_key = get_socket_key(output_socket_needed)
        if req_key in socket_value_map:
            return socket_value_map[req_key]
    return val_val


def handle_voronoi_texture(node, ctx):
    """Handle ComputeNodeVoronoiTexture node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Inputs
    val_vec = get_socket_value(node.inputs[0])
    val_w = get_socket_value(node.inputs[1])
    val_scale = get_socket_value(node.inputs[2])
    val_detail = get_socket_value(node.inputs[3])
    val_rough = get_socket_value(node.inputs[4])
    val_lacu = get_socket_value(node.inputs[5])
    val_smooth = get_socket_value(node.inputs[6])
    val_exp = get_socket_value(node.inputs[7])
    val_rand = get_socket_value(node.inputs[8])
    
    # Defaults
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    
    if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
    if val_scale is None: val_scale = builder.constant(5.0, DataType.FLOAT)
    if val_detail is None: val_detail = builder.constant(0.0, DataType.FLOAT)
    if val_rough is None: val_rough = builder.constant(0.5, DataType.FLOAT)
    if val_lacu is None: val_lacu = builder.constant(2.0, DataType.FLOAT)
    if val_smooth is None: val_smooth = builder.constant(1.0, DataType.FLOAT)
    if val_exp is None: val_exp = builder.constant(1.0, DataType.FLOAT)
    if val_rand is None: val_rand = builder.constant(1.0, DataType.FLOAT)

    # Type Casting
    if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
    if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
    if val_scale.type != DataType.FLOAT: val_scale = builder.cast(val_scale, DataType.FLOAT)
    if val_detail.type != DataType.FLOAT: val_detail = builder.cast(val_detail, DataType.FLOAT)
    if val_rough.type != DataType.FLOAT: val_rough = builder.cast(val_rough, DataType.FLOAT)
    if val_lacu.type != DataType.FLOAT: val_lacu = builder.cast(val_lacu, DataType.FLOAT)
    if val_smooth.type != DataType.FLOAT: val_smooth = builder.cast(val_smooth, DataType.FLOAT)
    if val_exp.type != DataType.FLOAT: val_exp = builder.cast(val_exp, DataType.FLOAT)
    if val_rand.type != DataType.FLOAT: val_rand = builder.cast(val_rand, DataType.FLOAT)
    
    inputs = [val_vec, val_w, val_scale, val_detail, val_rough, val_lacu, val_smooth, val_exp, val_rand]
    
    attrs = {
        'dimensions': str(node.dim_mode),    # Use dim_mode property!
        'feature': str(node.feature),        # Convert EnumProperty to string
        'metric': str(node.metric),          # Convert EnumProperty to string
        'normalize': bool(node.normalize)    # Convert to bool
    }
    
    op = builder.add_op(OpCode.VORONOI, inputs, attrs)
    
    # Outputs: Distance, Color, Position, W, Radius
    val_dist = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    val_pos = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op)
    val_out_w = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    val_rad = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    
    op.add_output(val_dist)
    op.add_output(val_col)
    op.add_output(val_pos)
    op.add_output(val_out_w)
    op.add_output(val_rad)
    
    socket_value_map[get_socket_key(node.outputs[0])] = val_dist
    socket_value_map[get_socket_key(node.outputs[1])] = val_col
    socket_value_map[get_socket_key(node.outputs[2])] = val_pos
    socket_value_map[get_socket_key(node.outputs[3])] = val_out_w
    socket_value_map[get_socket_key(node.outputs[4])] = val_rad
    
    if output_socket_needed:
        req_key = get_socket_key(output_socket_needed)
        if req_key in socket_value_map:
            return socket_value_map[req_key]
    return val_dist
