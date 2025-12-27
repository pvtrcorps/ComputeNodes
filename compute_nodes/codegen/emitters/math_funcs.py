# Math Function Emitters
# Handles: Trig, Hyperbolic, Exponential, Rounding, Min/Max, Smooth, Compare


def emit_trig(func_name, op, ctx):
    """Emit trigonometric functions: sin, cos, tan, asin, acos, atan, atan2"""
    lhs = ctx['lhs']
    param = ctx['param']
    
    if func_name == 'atan2':
        return f"{lhs}atan({param(op.inputs[0])}, {param(op.inputs[1])});"
    else:
        return f"{lhs}{func_name}({param(op.inputs[0])});"


def emit_hyperbolic(func_name, op, ctx):
    """Emit hyperbolic functions: sinh, cosh, tanh"""
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{func_name}({param(op.inputs[0])});"


def emit_exp_log(func_name, op, ctx):
    """Emit exponential/logarithmic functions: pow, exp, log, sqrt, inversesqrt, radians, degrees"""
    lhs = ctx['lhs']
    param = ctx['param']
    
    if func_name == 'pow':
        return f"{lhs}pow({param(op.inputs[0])}, {param(op.inputs[1])});"
    else:
        return f"{lhs}{func_name}({param(op.inputs[0])});"


def emit_rounding(func_name, op, ctx):
    """Emit rounding functions: abs, sign, floor, ceil, fract, trunc, round"""
    lhs = ctx['lhs']
    param = ctx['param']
    return f"{lhs}{func_name}({param(op.inputs[0])});"


def emit_minmax(func_name, op, ctx):
    """Emit min/max functions: min, max, clamp"""
    lhs = ctx['lhs']
    param = ctx['param']
    
    if func_name in ('clamp', 'mix'):
        return f"{lhs}{func_name}({param(op.inputs[0])}, {param(op.inputs[1])}, {param(op.inputs[2])});"
    else:
        return f"{lhs}{func_name}({param(op.inputs[0])}, {param(op.inputs[1])});"


def emit_smooth(op, ctx):
    """Emit smooth min/max operations"""
    from ...ir.ops import OpCode
    
    lhs = ctx['lhs']
    param = ctx['param']
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    c = param(op.inputs[2])
    
    if op.opcode == OpCode.SMOOTH_MIN:
        # h = max(c - abs(a - b), 0.0) / c
        # return min(a, b) - h * h * c * 0.25
        return f"{lhs}({c} != 0.0) ? min({a}, {b}) - pow(max({c} - abs({a} - {b}), 0.0), 2.0) / ({c} * 4.0) : min({a}, {b});"
    else:  # SMOOTH_MAX
        return f"{lhs}({c} != 0.0) ? max({a}, {b}) + pow(max({c} - abs({a} - {b}), 0.0), 2.0) / ({c} * 4.0) : max({a}, {b});"


def emit_compare(op, ctx):
    """Emit compare operation: (abs(a - b) <= max(c, 1e-5)) ? 1.0 : 0.0"""
    lhs = ctx['lhs']
    param = ctx['param']
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    c = param(op.inputs[2])
    return f"{lhs}(abs({a} - {b}) <= max({c}, 1e-5)) ? 1.0 : 0.0;"
