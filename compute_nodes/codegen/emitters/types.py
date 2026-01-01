# Type Operation Emitters
# Handles: CONSTANT, BUILTIN, SWIZZLE, CAST, SELECT

from ...ir.graph import ValueKind
from ...ir.types import DataType


def emit_constant(op, ctx):
    """Emit constant value declaration.
    
    Skips auto-sampling placeholders (0.5, 0.5) that are used only for
    cross-pass UV coordination and never actually referenced in shader code.
    """
    lhs = ctx.lhs
    type_str = ctx.type_str
    
    val = op.attrs.get('value')
    
    # Skip auto-sampling placeholders to avoid unused variables
    # These are created during graph extraction for cross-pass UV coordination
    # but replaced with inline expressions during emission
    # NOTE: Only skip (0.5, 0.5) family - (0.0, 0.0, 0.0) are legitimate defaults!
    if val in [(0.5, 0.5), (0.5, 0.5, 0.5)]:
        return ""  # Don't emit - will be inlined when actually used
    
    s_val = ""
    
    # Handle Vector types
    if hasattr(val, "__len__") and not isinstance(val, str):
        comps = []
        for v in val:
            s_v = str(v)
            if isinstance(v, float) and '.' not in s_v and 'e' not in s_v:
                s_v += ".0"
            comps.append(s_v)
        
        type_name = type_str(op.outputs[0].type)
        s_val = f"{type_name}({', '.join(comps)})"
    else:
        # Scalar
        if isinstance(val, bool):
            s_val = "true" if val else "false"
        else:
            s_val = str(val)
            if isinstance(val, float) and '.' not in s_val and 'e' not in s_val:
                s_val += ".0"
                
    return f"{lhs}{s_val};"


def emit_builtin(op, ctx):
    """Emit builtin variable assignment."""
    lhs = ctx.lhs
    glsl_name = op.attrs.get('name')
    return f"{lhs}{glsl_name};"


def emit_swizzle(op, ctx):
    """Emit swizzle operation."""
    lhs = ctx.lhs
    param = ctx.param
    mask = op.attrs.get('mask', 'xy')
    return f"{lhs}{param(op.inputs[0])}.{mask};"


def emit_select(op, ctx):
    """Emit select/mix operation."""
    lhs = ctx.lhs
    param = ctx.param
    a = param(op.inputs[0])
    b = param(op.inputs[1])
    t = param(op.inputs[2])
    return f"{lhs}mix({a}, {b}, {t});"


def emit_cast(op, ctx):
    """Emit type cast operation with comprehensive Blender-matching behavior."""
    lhs = ctx.lhs
    param = ctx.param
    type_str = ctx.type_str
    
    target_type = type_str(op.outputs[0].type)
    src_val = op.inputs[0]

    # 1. Vector (Vec3) -> Float : Average
    if src_val.type == DataType.VEC3 and op.outputs[0].type == DataType.FLOAT:
        return f"{lhs}dot({param(src_val)}, vec3(0.33333333));"
        
    # 2. Color (Vec4) -> Float : Luminance
    if src_val.type == DataType.VEC4 and op.outputs[0].type == DataType.FLOAT:
        return f"{lhs}dot({param(src_val)}.rgb, vec3(0.2126, 0.7152, 0.0722));"
        
    # 3. Float -> Color (Vec4) : Replicate RGB, Alpha = 1.0
    if src_val.type == DataType.FLOAT and op.outputs[0].type == DataType.VEC4:
        return f"{lhs}vec4(vec3({param(src_val)}), 1.0);"
        
    # 4. Vector (Vec3) -> Color (Vec4) : Append Alpha 1.0
    if src_val.type == DataType.VEC3 and op.outputs[0].type == DataType.VEC4:
        return f"{lhs}vec4({param(src_val)}, 1.0);"
        
    # 5. Color (Vec4) -> Vector (Vec3) : Drop Alpha
    if src_val.type == DataType.VEC4 and op.outputs[0].type == DataType.VEC3:
        return f"{lhs}{param(src_val)}.rgb;"

    # 6. Float -> Bool : != 0.0
    if src_val.type == DataType.FLOAT and op.outputs[0].type == DataType.BOOL:
        return f"{lhs}({param(src_val)} != 0.0);"
        
    # 7. Int -> Bool : != 0
    if src_val.type == DataType.INT and op.outputs[0].type == DataType.BOOL:
        return f"{lhs}({param(src_val)} != 0);"
        
    # 8. Vector/Color -> Bool : LengthSq > 0
    if src_val.type in (DataType.VEC3, DataType.VEC4) and op.outputs[0].type == DataType.BOOL:
        return f"{lhs}(dot({param(src_val)}, {param(src_val)}) > 0.000001);"
        
    # 9. Bool -> Float : 1.0 or 0.0
    if src_val.type == DataType.BOOL and op.outputs[0].type == DataType.FLOAT:
        return f"{lhs}({param(src_val)} ? 1.0 : 0.0);"
    
    # Vec2 -> Vec3 : Pad with 0.0
    if src_val.type == DataType.VEC2 and op.outputs[0].type == DataType.VEC3:
        return f"{lhs}vec3({param(src_val)}, 0.0);"

    # IVEC2 -> VEC3 : Convert to float and pad with 0.0 (for Image Info size)
    if src_val.type == DataType.IVEC2 and op.outputs[0].type == DataType.VEC3:
        return f"{lhs}vec3(vec2({param(src_val)}), 0.0);"
    
    # IVEC2 -> VEC2 : Convert to float
    if src_val.type == DataType.IVEC2 and op.outputs[0].type == DataType.VEC2:
        return f"{lhs}vec2({param(src_val)});"
    
    # IVEC2 -> FLOAT : Use first component
    if src_val.type == DataType.IVEC2 and op.outputs[0].type == DataType.FLOAT:
        return f"{lhs}float({param(src_val)}.x);"

    # Generic Cast (Constructor style)
    return f"{lhs}{target_type}({param(src_val)});"

