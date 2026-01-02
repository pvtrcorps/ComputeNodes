# Math Node Handlers
# Handles: ComputeNodeMath, ComputeNodeVectorMath

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_math(node, ctx):
    """Handle ComputeNodeMath node (scalar math operations)."""
    builder = ctx.builder
    
    val_a = ctx.input_float(0)
    val_b = ctx.input_float(1)
    
    op_str = node.operation
    
    op_map = {
        'LESS_THAN': OpCode.LT,
        'GREATER_THAN': OpCode.GT,
        'MODULO': OpCode.MOD,
    }
    
    opcode = op_map.get(op_str)
    if opcode is None:
        opcode = getattr(OpCode, op_str, OpCode.ADD)
    
    inputs = [val_a, val_b]

    # Check for 3rd input (Ternary)
    # MULTIPLY_ADD, WRAP, MIX, etc.
    if opcode in {OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.COMPARE, OpCode.SMOOTH_MIN, OpCode.SMOOTH_MAX, OpCode.CLAMP, OpCode.MIX}:
        if len(node.inputs) > 2:
            inputs.append(ctx.input_float(2))
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
    
    ctx.set_output(0, val_out)
    return val_out


def handle_vector_math(node, ctx):
    """Handle ComputeNodeVectorMath node (vector math operations)."""
    builder = ctx.builder
    
    val_a = ctx.input_vec3(0)
    val_b = ctx.input_vec3(1)
    
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
            inputs.append(ctx.input_vec3(2))
    
    # Mixed Inputs - SCALE uses MUL (vec * scalar)
    if op_str == 'SCALE':
        opcode = OpCode.MUL
        if len(node.inputs) > 3:
            inputs = [val_a, ctx.input_float(3, default=1.0)]
        else:
            inputs = [val_a, builder.constant(1.0, DataType.FLOAT)]
            
    elif opcode == OpCode.REFRACT:
        if len(node.inputs) > 3:
            # IOR input
            inputs = [val_a, val_b, ctx.input_float(3, default=1.45)]
    
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
        ctx.set_output(1, val_res) # Value output
        
        # Also cast to vec3 for Vector output if needed?
        # Standard behavior: Vector output gets casted vector
        val_vec = builder.cast(val_res, DataType.VEC3)
        ctx.set_output(0, val_vec)
    else:
        ctx.set_output(0, val_res) # Vector output
        ctx.set_output(1, builder.constant(0.0, DataType.FLOAT)) # Value output (dummy)
        
    return val_res
