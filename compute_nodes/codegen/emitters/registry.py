# Emitter Registry
# Maps OpCode -> emitter function

from ...ir.ops import OpCode
from ...ir.graph import Op
from typing import Dict, Callable, Any, Optional

from ..shader_context import ShaderContext

# Emitter signature: (op: Op, ctx: ShaderContext) -> str
EmitterType = Callable[[Op, ShaderContext], str]

from .arithmetic import emit_add, emit_sub, emit_mul, emit_div, emit_mod
from .arithmetic import emit_multiply_add, emit_wrap, emit_snap, emit_pingpong
from .math_funcs import emit_trig, emit_hyperbolic, emit_exp_log
from .math_funcs import emit_rounding, emit_minmax, emit_smooth, emit_compare
from .vector import emit_dot, emit_cross, emit_length, emit_distance
from .vector import emit_normalize, emit_reflect, emit_refract, emit_faceforward, emit_project
from .types import emit_constant, emit_builtin, emit_swizzle, emit_cast, emit_select
from .images import emit_image_store, emit_image_load, emit_image_size, emit_sample
from .textures import emit_noise, emit_white_noise, emit_voronoi
from .control_flow import emit_loop_start, emit_loop_end, emit_pass_loop_begin, emit_pass_loop_end, emit_pass_loop_read, emit_pass_loop_write
from .converter import emit_separate_xyz, emit_combine_xy, emit_combine_xyz, emit_separate_color, emit_combine_color, emit_map_range, emit_clamp_range
from .blur import emit_blur


# Registry mapping OpCode to emitter function
EMITTER_REGISTRY: Dict[OpCode, EmitterType] = {
    # Arithmetic
    OpCode.ADD: emit_add,
    OpCode.SUB: emit_sub,
    OpCode.MUL: emit_mul,
    OpCode.DIV: emit_div,
    OpCode.MOD: emit_mod,
    OpCode.MULTIPLY_ADD: emit_multiply_add,
    OpCode.WRAP: emit_wrap,
    OpCode.SNAP: emit_snap,
    OpCode.PINGPONG: emit_pingpong,
    
    # Math functions - Trig
    OpCode.SIN: lambda op, ctx: emit_trig('sin', op, ctx),
    OpCode.COS: lambda op, ctx: emit_trig('cos', op, ctx),
    OpCode.TAN: lambda op, ctx: emit_trig('tan', op, ctx),
    OpCode.ASIN: lambda op, ctx: emit_trig('asin', op, ctx),
    OpCode.ACOS: lambda op, ctx: emit_trig('acos', op, ctx),
    OpCode.ATAN: lambda op, ctx: emit_trig('atan', op, ctx),
    OpCode.ATAN2: lambda op, ctx: emit_trig('atan2', op, ctx),
    
    # Hyperbolic
    OpCode.SINH: lambda op, ctx: emit_hyperbolic('sinh', op, ctx),
    OpCode.COSH: lambda op, ctx: emit_hyperbolic('cosh', op, ctx),
    OpCode.TANH: lambda op, ctx: emit_hyperbolic('tanh', op, ctx),
    
    # Conversion
    OpCode.RADIANS: lambda op, ctx: emit_exp_log('radians', op, ctx),
    OpCode.DEGREES: lambda op, ctx: emit_exp_log('degrees', op, ctx),
    
    # Exponential
    OpCode.POW: lambda op, ctx: emit_exp_log('pow', op, ctx),
    OpCode.EXP: lambda op, ctx: emit_exp_log('exp', op, ctx),
    OpCode.LOG: lambda op, ctx: emit_exp_log('log', op, ctx),
    OpCode.SQRT: lambda op, ctx: emit_exp_log('sqrt', op, ctx),
    OpCode.INVERSE_SQRT: lambda op, ctx: emit_exp_log('inversesqrt', op, ctx),
    
    # Rounding
    OpCode.ABS: lambda op, ctx: emit_rounding('abs', op, ctx),
    OpCode.SIGN: lambda op, ctx: emit_rounding('sign', op, ctx),
    OpCode.FLOOR: lambda op, ctx: emit_rounding('floor', op, ctx),
    OpCode.CEIL: lambda op, ctx: emit_rounding('ceil', op, ctx),
    OpCode.FRACT: lambda op, ctx: emit_rounding('fract', op, ctx),
    OpCode.TRUNC: lambda op, ctx: emit_rounding('trunc', op, ctx),
    OpCode.ROUND: lambda op, ctx: emit_rounding('round', op, ctx),
    
    # Min/Max
    OpCode.MIN: lambda op, ctx: emit_minmax('min', op, ctx),
    OpCode.MAX: lambda op, ctx: emit_minmax('max', op, ctx),
    OpCode.CLAMP: lambda op, ctx: emit_minmax('clamp', op, ctx),
    OpCode.MIX: lambda op, ctx: emit_minmax('mix', op, ctx),
    
    # Smooth operations
    OpCode.SMOOTH_MIN: emit_smooth,
    OpCode.SMOOTH_MAX: emit_smooth,
    
    # Compare
    OpCode.COMPARE: emit_compare,
    OpCode.LT: lambda op, ctx: f"{ctx.lhs}({ctx.param(op.inputs[0])} < {ctx.param(op.inputs[1])}) ? 1.0 : 0.0;",
    OpCode.GT: lambda op, ctx: f"{ctx.lhs}({ctx.param(op.inputs[0])} > {ctx.param(op.inputs[1])}) ? 1.0 : 0.0;",
    
    # Vector
    OpCode.DOT: emit_dot,
    OpCode.CROSS: emit_cross,
    OpCode.LENGTH: emit_length,
    OpCode.DISTANCE: emit_distance,
    OpCode.NORMALIZE: emit_normalize,
    OpCode.REFLECT: emit_reflect,
    OpCode.REFRACT: emit_refract,
    OpCode.FACEFORWARD: emit_faceforward,
    OpCode.PROJECT: emit_project,
    
    # Types
    OpCode.CONSTANT: emit_constant,
    OpCode.BUILTIN: emit_builtin,
    OpCode.SWIZZLE: emit_swizzle,
    OpCode.CAST: emit_cast,
    OpCode.SELECT: emit_select,
    
    # Images
    OpCode.IMAGE_STORE: emit_image_store,
    OpCode.IMAGE_LOAD: emit_image_load,
    OpCode.IMAGE_SIZE: emit_image_size,
    OpCode.SAMPLE: emit_sample,
    
    # Textures
    OpCode.NOISE: emit_noise,
    OpCode.WHITE_NOISE: emit_white_noise,
    OpCode.VORONOI: emit_voronoi,
    
    # Control Flow
    OpCode.LOOP_START: emit_loop_start,
    OpCode.LOOP_END: emit_loop_end,
    
    # Multi-Pass Loop (no-ops - handled by executor)
    OpCode.PASS_LOOP_BEGIN: emit_pass_loop_begin,
    OpCode.PASS_LOOP_END: emit_pass_loop_end,
    OpCode.PASS_LOOP_READ: emit_pass_loop_read,
    OpCode.PASS_LOOP_WRITE: emit_pass_loop_write,
    
    # Converter
    OpCode.SEPARATE_XYZ: emit_separate_xyz,
    OpCode.COMBINE_XY: emit_combine_xy,
    OpCode.COMBINE_XYZ: emit_combine_xyz,
    OpCode.SEPARATE_COLOR: emit_separate_color,
    OpCode.COMBINE_COLOR: emit_combine_color,
    OpCode.MAP_RANGE: emit_map_range,
    OpCode.CLAMP_RANGE: emit_clamp_range,
    
    # Image Processing
    OpCode.BLUR: emit_blur,
}


def get_emitter(opcode: OpCode) -> Optional[EmitterType]:
    """Get emitter function for an OpCode, or None if not found."""
    return EMITTER_REGISTRY.get(opcode)


__all__ = ['EMITTER_REGISTRY', 'get_emitter']
