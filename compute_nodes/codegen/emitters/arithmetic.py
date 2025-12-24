# Arithmetic Operation Emitters
# Handles: ADD, SUB, MUL, DIV, MOD, MULTIPLY_ADD, WRAP, SNAP, PINGPONG


def emit_add(op, ctx):
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{param(op.inputs[0])} + {param(op.inputs[1])};"


def emit_sub(op, ctx):
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{param(op.inputs[0])} - {param(op.inputs[1])};"


def emit_mul(op, ctx):
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{param(op.inputs[0])} * {param(op.inputs[1])};"


def emit_div(op, ctx):
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{param(op.inputs[0])} / {param(op.inputs[1])};"


def emit_mod(op, ctx):
    lhs = ctx['lhs']
    param = ctx['param']
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    return f"{lhs}mod({a}, {b});"


def emit_multiply_add(op, ctx):
    """a * b + c"""
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{param(op.inputs[0])} * {param(op.inputs[1])} + {param(op.inputs[2])};"


def emit_wrap(op, ctx):
    """wrap(val, min, max) = mod(val - min, max - min) + min"""
    lhs = ctx['lhs']
    param = ctx['param']
    val = param(op.inputs[0])
    v_min = param(op.inputs[1])
    v_max = param(op.inputs[2])
    return f"{lhs}mod({val} - {v_min}, {v_max} - {v_min}) + {v_min};"


def emit_snap(op, ctx):
    """floor(a / b) * b"""
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}floor({param(op.inputs[0])} / {param(op.inputs[1])}) * {param(op.inputs[1])};"


def emit_pingpong(op, ctx):
    """Blender pingpong formula"""
    lhs = ctx['lhs']
    param = ctx['param']
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    return f"{lhs}({b} != 0.0) ? abs(fract({a} / ({b} * 2.0)) * {b} * 2.0 - {b}) : 0.0;"
