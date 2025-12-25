# Constant formatting utilities for GLSL code generation

from ...ir.types import DataType


def format_constant(value, dtype: DataType) -> str:
    """Format a Python value as GLSL literal."""
    if value is None:
        return "0.0"
    
    # Handle Vector/Color types from Blender that aren't tuples
    if hasattr(value, '__iter__') and not isinstance(value, (str, tuple, list)):
        value = tuple(value)
    
    if dtype == DataType.FLOAT:
        return f"{float(value)}"
    elif dtype == DataType.INT:
        return f"{int(value)}"
    elif dtype == DataType.BOOL:
        return "true" if value else "false"
    elif dtype == DataType.VEC2:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return f"vec2({float(value[0])}, {float(value[1])})"
        return f"vec2({float(value) if isinstance(value, (int, float)) else 0.0})"
    elif dtype == DataType.VEC3:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return f"vec3({float(value[0])}, {float(value[1])}, {float(value[2])})"
        return f"vec3({float(value) if isinstance(value, (int, float)) else 0.0})"
    elif dtype == DataType.VEC4:
        if isinstance(value, (list, tuple)) and len(value) >= 4:
            return f"vec4({float(value[0])}, {float(value[1])}, {float(value[2])}, {float(value[3])})"
        elif isinstance(value, (list, tuple)) and len(value) == 3:
            # RGB → RGBA
            return f"vec4({float(value[0])}, {float(value[1])}, {float(value[2])}, 1.0)"
        return f"vec4({float(value) if isinstance(value, (int, float)) else 0.0})"
    elif dtype == DataType.IVEC2:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return f"ivec2({int(value[0])}, {int(value[1])})"
        return f"ivec2({int(value) if isinstance(value, (int, float)) else 0})"
    elif dtype == DataType.IVEC3:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return f"ivec3({int(value[0])}, {int(value[1])}, {int(value[2])})"
        return f"ivec3({int(value) if isinstance(value, (int, float)) else 0})"
    elif dtype == DataType.UVEC3:
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return f"uvec3({int(value[0])}, {int(value[1])}, {int(value[2])})"
        return f"uvec3({int(value) if isinstance(value, (int, float)) else 0})"
    else:
        # Fallback: try to format as float
        try:
            if isinstance(value, (int, float)):
                return f"{float(value)}"
            elif isinstance(value, (list, tuple)):
                if len(value) == 3:
                    return f"vec3({float(value[0])}, {float(value[1])}, {float(value[2])})"
                elif len(value) == 4:
                    return f"vec4({float(value[0])}, {float(value[1])}, {float(value[2])}, {float(value[3])})"
            return "0.0"
        except:
            return "0.0"

