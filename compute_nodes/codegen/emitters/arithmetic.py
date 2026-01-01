# Arithmetic Operation Emitters
# Handles: ADD, SUB, MUL, DIV, MOD, MULTIPLY_ADD, WRAP, SNAP, PINGPONG


def emit_add(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}{param(op.inputs[0])} + {param(op.inputs[1])};"


def emit_sub(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}{param(op.inputs[0])} - {param(op.inputs[1])};"


def emit_mul(op, ctx):
    """Emit multiplication with inline type coercion for VEC4/VEC3 mismatches."""
    lhs = ctx.lhs
    param = ctx.param
    
    # Get operand representations
    a_str = param(op.inputs[0])
    b_str = param(op.inputs[1])
    
    # Handle VEC4 * VEC3 or VEC3 * VEC4 mismatches
    # This can happen when CAST ops are not properly scheduled
    a_type = op.inputs[0].type
    b_type = op.inputs[1].type
    out_type = op.outputs[0].type if op.outputs else None
    
    from ...ir.types import DataType
    
    # If output is VEC3 but one input is VEC4, swizzle to .rgb
    if out_type == DataType.VEC3:
        if a_type == DataType.VEC4:
            a_str = f"{a_str}.rgb"
        if b_type == DataType.VEC4:
            b_str = f"{b_str}.rgb"
    # If output is VEC4 and mixing with VEC3, wrap VEC3 into VEC4
    elif out_type == DataType.VEC4:
        if a_type == DataType.VEC3 and b_type == DataType.VEC4:
            a_str = f"vec4({a_str}, 1.0)"
        elif b_type == DataType.VEC3 and a_type == DataType.VEC4:
            b_str = f"vec4({b_str}, 1.0)"
    
    return f"{lhs}{a_str} * {b_str};"


def emit_div(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}{param(op.inputs[0])} / {param(op.inputs[1])};"


def emit_mod(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    return f"{lhs}mod({a}, {b});"


def emit_multiply_add(op, ctx):
    """a * b + c"""
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}{param(op.inputs[0])} * {param(op.inputs[1])} + {param(op.inputs[2])};"


def emit_wrap(op, ctx):
    """wrap(val, min, max) = mod(val - min, max - min) + min"""
    lhs = ctx.lhs
    param = ctx.param
    val = param(op.inputs[0])
    v_min = param(op.inputs[1])
    v_max = param(op.inputs[2])
    return f"{lhs}mod({val} - {v_min}, {v_max} - {v_min}) + {v_min};"


def emit_snap(op, ctx):
    """floor(a / b) * b"""
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}floor({param(op.inputs[0])} / {param(op.inputs[1])}) * {param(op.inputs[1])};"


def emit_pingpong(op, ctx):
    """Blender pingpong formula"""
    lhs = ctx.lhs
    param = ctx.param
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    return f"{lhs}({b} != 0.0) ? abs(fract({a} / ({b} * 2.0)) * {b} * 2.0 - {b}) : 0.0;"
