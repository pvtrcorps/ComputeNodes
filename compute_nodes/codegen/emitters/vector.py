# Vector Operation Emitters
# Handles: DOT, CROSS, LENGTH, DISTANCE, NORMALIZE, REFLECT, REFRACT, FACEFORWARD, PROJECT


def emit_dot(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}dot({param(op.inputs[0])}, {param(op.inputs[1])});"


def emit_cross(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}cross({param(op.inputs[0])}, {param(op.inputs[1])});"


def emit_length(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}length({param(op.inputs[0])});"


def emit_distance(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}distance({param(op.inputs[0])}, {param(op.inputs[1])});"


def emit_normalize(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}normalize({param(op.inputs[0])});"


def emit_reflect(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}reflect({param(op.inputs[0])}, {param(op.inputs[1])});"


def emit_refract(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}refract({param(op.inputs[0])}, {param(op.inputs[1])}, {param(op.inputs[2])});"


def emit_faceforward(op, ctx):
    lhs = ctx.lhs
    param = ctx.param
    return f"{lhs}faceforward({param(op.inputs[0])}, {param(op.inputs[1])}, {param(op.inputs[2])});"


def emit_project(op, ctx):
    """dot(a, b) / dot(b, b) * b"""
    lhs = ctx.lhs
    param = ctx.param
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    return f"{lhs}dot({a}, {b}) / dot({b}, {b}) * {b};"
