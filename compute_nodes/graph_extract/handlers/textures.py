# Texture Node Handlers
# Handles: ComputeNodeNoiseTexture, ComputeNodeWhiteNoise, ComputeNodeVoronoiTexture

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_noise_texture(node, ctx):
    """Handle ComputeNodeNoiseTexture node."""
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Inputs: [Vector, W, Scale, Detail, Roughness, Lacunarity, Offset]
    val_vec = ctx.get_input(0)
    val_w = ctx.get_input(1)
    val_scale = ctx.input_float(2, default=5.0)
    val_detail = ctx.input_float(3, default=2.0)
    val_rough = ctx.input_float(4, default=0.5)
    val_lacu = ctx.input_float(5, default=2.0)
    val_offset = ctx.input_float(6, default=0.0)
    
    # Default Vector to Position
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    elif val_vec.type != DataType.VEC3:
        val_vec = builder.cast(val_vec, DataType.VEC3)
    
    if val_w is None:
        val_w = builder.constant(0.0, DataType.FLOAT)
    elif val_w.type != DataType.FLOAT:
        val_w = builder.cast(val_w, DataType.FLOAT)
    
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
    ctx.set_output(0, val_fac)
    ctx.set_output(1, val_col)
    
    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_fac


def handle_white_noise(node, ctx):
    """Handle ComputeNodeWhiteNoise node."""
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    val_vec = ctx.get_input(0)
    val_w = ctx.input_float(1, default=0.0)
    
    # Defaults
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    elif val_vec.type != DataType.VEC3:
        val_vec = builder.cast(val_vec, DataType.VEC3)
    
    inputs = [val_vec, val_w]
    attrs = {'dimensions': str(node.dim_mode)}  # Use dim_mode property!
    
    op = builder.add_op(OpCode.WHITE_NOISE, inputs, attrs)
    
    # Outputs
    val_val = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    op.add_output(val_val)
    op.add_output(val_col)
    
    ctx.set_output(0, val_val)
    ctx.set_output(1, val_col)
    
    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_val


def handle_voronoi_texture(node, ctx):
    """Handle ComputeNodeVoronoiTexture node."""
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Inputs
    val_vec = ctx.get_input(0)
    val_w = ctx.input_float(1, default=0.0)
    val_scale = ctx.input_float(2, default=5.0)
    val_detail = ctx.input_float(3, default=0.0)
    val_rough = ctx.input_float(4, default=0.5)
    val_lacu = ctx.input_float(5, default=2.0)
    val_smooth = ctx.input_float(6, default=1.0)
    val_exp = ctx.input_float(7, default=1.0)
    val_rand = ctx.input_float(8, default=1.0)
    
    # Default Vector
    if val_vec is None:
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_vec = builder.cast(val_gid, DataType.VEC3)
    elif val_vec.type != DataType.VEC3:
        val_vec = builder.cast(val_vec, DataType.VEC3)
    
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
    
    ctx.set_output(0, val_dist)
    ctx.set_output(1, val_col)
    ctx.set_output(2, val_pos)
    ctx.set_output(3, val_out_w)
    ctx.set_output(4, val_rad)
    
    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_dist
