from enum import Enum, auto
from typing import Optional
from .types import DataType

class OpCode(Enum):
    # --- Arithmetic ---
    ADD = auto()
    SUB = auto()
    MUL = auto()
    DIV = auto()
    MOD = auto()
    MULTIPLY_ADD = auto()
    WRAP = auto()
    SNAP = auto()
    PINGPONG = auto()
    
    # --- Math / Common ---
    ABS = auto()
    SIGN = auto()
    FLOOR = auto()
    CEIL = auto()
    FRACT = auto()
    TRUNC = auto()
    ROUND = auto()
    MIN = auto()
    MAX = auto()
    SMOOTH_MIN = auto()
    SMOOTH_MAX = auto()
    CLAMP = auto()
    MIX = auto()
    STEP = auto()
    SMOOTHSTEP = auto()
    
    # --- Exponential ---
    POW = auto()
    SQRT = auto()
    INVERSE_SQRT = auto()
    EXP = auto()
    LOG = auto()
    
    # --- Trigonometry ---
    SIN = auto()
    COS = auto()
    TAN = auto()
    ASIN = auto()
    ACOS = auto()
    ATAN = auto()
    ATAN2 = auto()
    SINH = auto()
    COSH = auto()
    TANH = auto()
    RADIANS = auto()
    DEGREES = auto()
    
    # --- Vector ---
    DOT = auto()
    CROSS = auto()
    LENGTH = auto()
    DISTANCE = auto()
    NORMALIZE = auto()
    REFLECT = auto()
    REFRACT = auto()
    FACEFORWARD = auto()
    PROJECT = auto()
    
    # --- Relational (Component-wise) ---
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LE = auto()
    GE = auto()
    COMPARE = auto()
    
    # --- Logic ---
    AND = auto()
    OR = auto()
    NOT = auto()
    SELECT = auto() # Ternary / If-Else
    LOOP_START = auto() # Start of a loop block
    LOOP_END = auto()   # End of a loop block
    
    # --- Constructors / Conversion ---
    CONSTRUCT = auto() # vec3(x,y,z)
    SWIZZLE = auto()   # val.xyz
    CAST = auto()      # float(int_val)
    SEPARATE_XYZ = auto()    # vec3 -> x, y, z
    COMBINE_XY = auto()      # x, y -> vec2
    COMBINE_XYZ = auto()     # x, y, z -> vec3
    SEPARATE_COLOR = auto()  # vec4 -> components (RGB/HSV/HSL mode)
    COMBINE_COLOR = auto()   # components -> vec4 (RGB/HSV/HSL mode)
    MAP_RANGE = auto()       # remap value with interpolation modes
    CLAMP_RANGE = auto()     # clamp with MINMAX/RANGE mode
    
    # --- Resources ---
    SAMPLE = auto()       # texture(sampler, uv)
    NOISE = auto()        # noise_fbm(co, ...)
    WHITE_NOISE = auto()  # white_noise(co, ...)
    VORONOI = auto()      # voronoi_f1(co, ...)
    IMAGE_LOAD = auto()   # imageLoad(img, coord)
    IMAGE_STORE = auto()  # imageStore(img, coord, val)
    IMAGE_SIZE = auto()   # imageSize(img)
    BLUR = auto()         # Gaussian blur kernel
    BUFFER_READ = auto()
    BUFFER_WRITE = auto()
    
    # --- Inputs / Terminal ---
    CONSTANT = auto()
    BUILTIN = auto()     # gl_GlobalInvocationID, etc.
    ARGUMENT = auto()    # Reference to a resource/uniform arg

def infer_arithmetic_type(opcode: OpCode, a: DataType, b: DataType) -> DataType:
    """Infers type for basic arithmetic (ADD, SUB, MUL, DIV)."""
    if a == b:
        # Strict matching: int+int=int, float+float=float
        if a.is_scalar() or a.is_vector():
            return a
    
    # Vector * Scalar interaction
    if a.is_vector() and b.is_scalar() and a.base_type() == b:
        return a
    if b.is_vector() and a.is_scalar() and b.base_type() == a:
        return b
        
    raise TypeError(f"Invalid arithmetic types for {opcode}: {a} vs {b}")

def infer_relational_type(opcode: OpCode, a: DataType, b: DataType) -> DataType:
    """Infers type for relational ops (EQ, LT, GT...); Returns BOOL."""
    # Strict matching for comparison
    if a == b:
        return DataType.BOOL
    
    raise TypeError(f"Cannot compare different types {opcode}: {a} vs {b}")

def infer_binary_type(opcode: OpCode, a: DataType, b: DataType) -> DataType:
    """
    Centralized dispatcher for binary type inference.
    """
    if opcode in {OpCode.ADD, OpCode.SUB, OpCode.MUL, OpCode.DIV, OpCode.MOD}:
        return infer_arithmetic_type(opcode, a, b)
        
    if opcode in {OpCode.EQ, OpCode.NEQ, OpCode.LT, OpCode.GT, OpCode.LE, OpCode.GE}:
        return infer_relational_type(opcode, a, b)
        
    # Fallback or specific internal logic
    raise TypeError(f"No inference rule for binary op {opcode}")
