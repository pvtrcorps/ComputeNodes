# Math Node Handlers
# Handles: ComputeNodeMath, ComputeNodeVectorMath

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_math(node, ctx):
    """Handle ComputeNodeMath node (scalar math operations)."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_a = get_socket_value(node.inputs[0])
    val_b = get_socket_value(node.inputs[1])
    
    if val_a is None: val_a = builder.constant(0.0, DataType.FLOAT)
    if val_b is None: val_b = builder.constant(0.0, DataType.FLOAT)

    if val_a.type != DataType.FLOAT: val_a = builder.cast(val_a, DataType.FLOAT)
    if val_b.type != DataType.FLOAT: val_b = builder.cast(val_b, DataType.FLOAT)
    
    op_str = node.operation
    
    op_map = {
        'LESS_THAN': OpCode.LT,
        'GREATER_THAN': OpCode.GT,
        'MODULO': OpCode.MOD,
    }
    
    opcode = op_map.get(op_str)
    if opcode is None:
        opcode = getattr(OpCode, op_str, OpCode.ADD)
    
    # Check for 3rd input (Ternary)
    val_c = None
    if opcode in {OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.COMPARE, OpCode.SMOOTH_MIN, OpCode.SMOOTH_MAX, OpCode.CLAMP, OpCode.MIX}:
        if len(node.inputs) > 2:
            val_c = get_socket_value(node.inputs[2])
    
    inputs = [val_a, val_b]
    if val_c:
        if val_c.type != DataType.FLOAT: val_c = builder.cast(val_c, DataType.FLOAT)
        inputs.append(val_c)
    elif opcode == OpCode.COMPARE:
        if len(inputs) < 3:
            inputs.append(builder.constant(0.00001, DataType.FLOAT))

    val_out = None
    try:
        op = builder.add_op(opcode, inputs)
        val_out = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
        op.add_output(val_out)
    except TypeError as e:
        raise TypeError(f"Node '{node.name}': {e}") from e
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_out
    return val_out


def handle_vector_math(node, ctx):
    """Handle ComputeNodeVectorMath node (vector math operations)."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    val_a = get_socket_value(node.inputs[0])
    val_b = get_socket_value(node.inputs[1])
    
    if val_a is None: val_a = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
    if val_b is None: val_b = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)

    if val_a.type != DataType.VEC3: val_a = builder.cast(val_a, DataType.VEC3)
    if val_b.type != DataType.VEC3: val_b = builder.cast(val_b, DataType.VEC3)
    
    op_str = node.operation
    
    op_map = {
        'MINIMUM': OpCode.MIN,
        'MAXIMUM': OpCode.MAX,
        'MODULO': OpCode.MOD,
        'SINE': OpCode.SIN,
        'COSINE': OpCode.COS,
        'TANGENT': OpCode.TAN,
        'FRACTION': OpCode.FRACT,
    }
    opcode = op_map.get(op_str)
    if opcode is None:
        opcode = getattr(OpCode, op_str, OpCode.ADD)
    
    res_type = DataType.VEC3
    is_float_out = False
    
    inputs = [val_a, val_b]
    
    # Unary
    if opcode in {OpCode.LENGTH, OpCode.NORMALIZE, OpCode.ABS, OpCode.FLOOR, OpCode.CEIL, OpCode.FRACT, OpCode.SIN, OpCode.COS, OpCode.TAN}:
        inputs = [val_a]
    
    # Ternary
    if opcode in {OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.REFRACT, OpCode.FACEFORWARD}:
        if len(node.inputs) > 2:
            val_c = get_socket_value(node.inputs[2])
            if val_c is None: val_c = builder.constant((0, 0, 0), DataType.VEC3)
            inputs.append(val_c)
    
    # Mixed Inputs - SCALE uses MUL (vec * scalar)
    if op_str == 'SCALE':
        opcode = OpCode.MUL
        if len(node.inputs) > 3:
            val_scale = get_socket_value(node.inputs[3])
            if val_scale is None: val_scale = builder.constant(1.0, DataType.FLOAT)
            inputs = [val_a, val_scale]
        else:
            inputs = [val_a, builder.constant(1.0, DataType.FLOAT)]
            
    elif opcode == OpCode.REFRACT:

        if len(node.inputs) > 3:
            val_ior = get_socket_value(node.inputs[3])
            if val_ior is None: val_ior = builder.constant(1.45, DataType.FLOAT)
            inputs = [val_a, val_b, val_ior]
    
    res_type = DataType.VEC3
    is_float_out = False
    
    if opcode in {OpCode.DOT, OpCode.DISTANCE}:
        res_type = DataType.FLOAT
        is_float_out = True
    elif opcode == OpCode.LENGTH:
        res_type = DataType.FLOAT
        is_float_out = True
    elif opcode == OpCode.NORMALIZE:
        res_type = DataType.VEC3
    elif opcode == OpCode.CROSS:
        res_type = DataType.VEC3
    elif opcode == OpCode.REFLECT:
        res_type = DataType.VEC3
    
    # Create Op
    op = builder.add_op(opcode, inputs)
    val_res = builder._new_value(ValueKind.SSA, res_type, origin=op)
    op.add_output(val_res)
    
    if is_float_out:
        out_key_val = get_socket_key(node.outputs[1])
        socket_value_map[out_key_val] = val_res
        
        val_vec = builder.cast(val_res, DataType.VEC3)
        out_key_vec = get_socket_key(node.outputs[0])
        socket_value_map[out_key_vec] = val_vec
    else:
        out_key_vec = get_socket_key(node.outputs[0])
        socket_value_map[out_key_vec] = val_res
        
        out_key_val = get_socket_key(node.outputs[1])
        socket_value_map[out_key_val] = builder.constant(0.0, DataType.FLOAT)
        
    if output_socket_needed:
        req_key = get_socket_key(output_socket_needed)
        if req_key in socket_value_map:
            return socket_value_map[req_key]
    return val_res
