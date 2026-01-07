# Scalar Expression Evaluator
# Recursively interprets IR Value trees at runtime for dynamic size calculations.
#
# Supports:
# - All Math operations (ADD, SUB, MUL, DIV, POW, etc.)
# - Converters (MapRange, Clamp, Mix)
# - Grid Info (IMAGE_SIZE → width/height)
# - Constants and loop iteration variables

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, Any, Tuple

from ..ir.ops import OpCode
from ..ir.graph import ValueKind

logger = logging.getLogger(__name__)


@dataclass
class EvalContext:
    """Runtime context for expression evaluation."""
    iteration: int = 0
    context_width: int = 512
    context_height: int = 512
    context_depth: int = 1
    grid_sizes: Dict[int, Tuple[int, int, int]] = field(default_factory=dict)


class ScalarEvaluator:
    """
    Evaluates IR Value expressions at runtime to produce scalar results.
    
    Used primarily for dynamic Resize dimensions inside Repeat Zones,
    where the size depends on the loop iteration or other runtime values.
    """
    
    def __init__(self):
        # Cache to avoid redundant evaluations within same context
        self._cache: Dict[int, float] = {}
    
    def evaluate(self, val, context: EvalContext) -> float:
        """
        Recursively evaluate an IR Value tree to a scalar float.
        
        Args:
            val: IR Value to evaluate
            context: Runtime context with iteration, grid sizes, etc.
            
        Returns:
            Evaluated scalar value as float
        """
        if val is None:
            return 0.0
        
        # Check cache
        val_id = id(val)
        if val_id in self._cache:
            return self._cache[val_id]
        
        result = self._evaluate_impl(val, context)
        self._cache[val_id] = result
        return result
    
    def _evaluate_impl(self, val, context: EvalContext) -> float:
        """Internal evaluation implementation."""
        
        # Case 1: Direct constant value attribute
        if hasattr(val, 'constant_value') and val.constant_value is not None:
            return self._to_scalar(val.constant_value)
        
        # Case 2: No origin (leaf value or uninitialized)
        if not hasattr(val, 'origin') or val.origin is None:
            # Try to get default from type
            if hasattr(val, 'type'):
                return 0.0
            return 0.0
        
        op = val.origin
        
        # Case 3: Origin has no opcode (might be a resource reference)
        if not hasattr(op, 'opcode'):
            return 0.0
        
        opcode = op.opcode
        inputs = getattr(op, 'inputs', [])
        attrs = getattr(op, 'attrs', {})
        
        # Dispatch by OpCode
        return self._dispatch(opcode, inputs, attrs, context, val)
    
    def _dispatch(self, opcode: OpCode, inputs: list, attrs: dict, 
                  context: EvalContext, val) -> float:
        """Dispatch evaluation based on OpCode."""
        
        # === CONSTANTS ===
        if opcode == OpCode.CONSTANT:
            return self._to_scalar(attrs.get('value', 0.0))
        
        # === BUILTINS ===
        if opcode == OpCode.BUILTIN:
            name = attrs.get('name', '')
            if 'iteration' in name.lower() or name == 'u_loop_iteration':
                return float(context.iteration)
            if name == 'u_dispatch_width':
                return float(context.context_width)
            if name == 'u_dispatch_height':
                return float(context.context_height)
            return 0.0
        
        # === LOOP ITERATION ===
        # PASS_LOOP_BEGIN produces the iteration output value
        if opcode == OpCode.PASS_LOOP_BEGIN:
            # The iteration output is the first output of PASS_LOOP_BEGIN
            # When we're evaluating this value, return the current iteration
            return float(context.iteration)
        
        # PASS_LOOP_READ for reading state variables (iteration is one of them)
        if opcode == OpCode.PASS_LOOP_READ:
            # Check if this is the iteration variable
            metadata = getattr(val.origin, 'metadata', {})
            if metadata.get('state_name') == 'Iteration' or metadata.get('is_iteration', False):
                return float(context.iteration)
            # For other loop reads, return 0 (can't evaluate grid state as scalar)
            return 0.0
        
        # === ARITHMETIC (Binary) ===
        if opcode == OpCode.ADD:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return a + b
        
        if opcode == OpCode.SUB:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return a - b
        
        if opcode == OpCode.MUL:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return a * b
        
        if opcode == OpCode.DIV:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            if abs(b) < 1e-10:
                return 0.0  # Avoid division by zero
            return a / b
        
        if opcode == OpCode.MOD:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            if abs(b) < 1e-10:
                return 0.0
            return a % b
        
        if opcode == OpCode.POW:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            try:
                return math.pow(a, b)
            except (ValueError, OverflowError):
                return 0.0
        
        # === ARITHMETIC (Unary) ===
        if opcode == OpCode.ABS:
            return abs(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.SIGN:
            v = self._eval_input(inputs, 0, context)
            if v > 0: return 1.0
            if v < 0: return -1.0
            return 0.0
        
        if opcode == OpCode.FLOOR:
            return math.floor(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.CEIL:
            return math.ceil(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.FRACT:
            v = self._eval_input(inputs, 0, context)
            return v - math.floor(v)
        
        if opcode == OpCode.TRUNC:
            return math.trunc(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.ROUND:
            return round(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.SQRT:
            v = self._eval_input(inputs, 0, context)
            if v < 0:
                return 0.0
            return math.sqrt(v)
        
        if opcode == OpCode.INVERSE_SQRT:
            v = self._eval_input(inputs, 0, context)
            if v <= 0:
                return 0.0
            return 1.0 / math.sqrt(v)
        
        if opcode == OpCode.EXP:
            try:
                return math.exp(self._eval_input(inputs, 0, context))
            except OverflowError:
                return float('inf')
        
        if opcode == OpCode.LOG:
            v = self._eval_input(inputs, 0, context)
            if v <= 0:
                return 0.0
            return math.log(v)
        
        # === TRIGONOMETRY ===
        if opcode == OpCode.SIN:
            return math.sin(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.COS:
            return math.cos(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.TAN:
            return math.tan(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.ASIN:
            v = self._eval_input(inputs, 0, context)
            v = max(-1.0, min(1.0, v))
            return math.asin(v)
        
        if opcode == OpCode.ACOS:
            v = self._eval_input(inputs, 0, context)
            v = max(-1.0, min(1.0, v))
            return math.acos(v)
        
        if opcode == OpCode.ATAN:
            return math.atan(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.ATAN2:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return math.atan2(a, b)
        
        if opcode == OpCode.RADIANS:
            return math.radians(self._eval_input(inputs, 0, context))
        
        if opcode == OpCode.DEGREES:
            return math.degrees(self._eval_input(inputs, 0, context))
        
        # === MIN/MAX/CLAMP ===
        if opcode == OpCode.MIN:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return min(a, b)
        
        if opcode == OpCode.MAX:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return max(a, b)
        
        if opcode == OpCode.CLAMP:
            v = self._eval_input(inputs, 0, context)
            lo = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            hi = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 1.0
            return max(lo, min(hi, v))
        
        if opcode == OpCode.CLAMP_RANGE:
            v = self._eval_input(inputs, 0, context)
            lo = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            hi = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 1.0
            clamp_type = attrs.get('clamp_type', 'MINMAX')
            if clamp_type == 'RANGE':
                # Swap if needed
                if lo > hi:
                    lo, hi = hi, lo
            return max(lo, min(hi, v))
        
        # === MIX / LERP ===
        if opcode == OpCode.MIX:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            t = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.5
            return a * (1.0 - t) + b * t
        
        # === MAP_RANGE ===
        if opcode == OpCode.MAP_RANGE:
            value = self._eval_input(inputs, 0, context)
            from_min = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            from_max = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 1.0
            to_min = self._eval_input(inputs, 3, context) if len(inputs) > 3 else 0.0
            to_max = self._eval_input(inputs, 4, context) if len(inputs) > 4 else 1.0
            
            # Normalize to 0-1
            range_from = from_max - from_min
            if abs(range_from) < 1e-10:
                t = 0.0
            else:
                t = (value - from_min) / range_from
            
            # Apply interpolation
            interp = attrs.get('interpolation_type', 'LINEAR')
            if interp == 'SMOOTHSTEP':
                t = t * t * (3.0 - 2.0 * t)
            elif interp == 'SMOOTHERSTEP':
                t = t * t * t * (t * (t * 6.0 - 15.0) + 10.0)
            
            # Clamp if specified
            if attrs.get('clamp', False):
                t = max(0.0, min(1.0, t))
            
            # Map to output range
            return to_min + t * (to_max - to_min)
        
        # === RELATIONAL ===
        if opcode == OpCode.LT:
            return 1.0 if self._eval_input(inputs, 0, context) < self._eval_input(inputs, 1, context) else 0.0
        
        if opcode == OpCode.GT:
            return 1.0 if self._eval_input(inputs, 0, context) > self._eval_input(inputs, 1, context) else 0.0
        
        if opcode == OpCode.LE:
            return 1.0 if self._eval_input(inputs, 0, context) <= self._eval_input(inputs, 1, context) else 0.0
        
        if opcode == OpCode.GE:
            return 1.0 if self._eval_input(inputs, 0, context) >= self._eval_input(inputs, 1, context) else 0.0
        
        if opcode == OpCode.EQ:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return 1.0 if abs(a - b) < 1e-6 else 0.0
        
        if opcode == OpCode.NEQ:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            return 0.0 if abs(a - b) < 1e-6 else 1.0
        
        # === IMAGE SIZE (Grid Info) ===
        if opcode == OpCode.IMAGE_SIZE:
            if inputs and len(inputs) > 0:
                img_val = inputs[0]
                if hasattr(img_val, 'resource_index') and img_val.resource_index is not None:
                    res_idx = img_val.resource_index
                    if res_idx in context.grid_sizes:
                        size = context.grid_sizes[res_idx]
                        # Return as vec3-like, but we're scalar so return width by default
                        # The SWIZZLE will extract the right component
                        return float(size[0])  # Width
            return float(context.context_width)
        
        # === SWIZZLE (extract component) ===
        if opcode == OpCode.SWIZZLE:
            component = attrs.get('components', 'x')
            if inputs and len(inputs) > 0:
                # For IMAGE_SIZE result, we need to handle specially
                input_val = inputs[0]
                if hasattr(input_val, 'origin') and input_val.origin:
                    input_op = input_val.origin
                    if hasattr(input_op, 'opcode') and input_op.opcode == OpCode.IMAGE_SIZE:
                        # Get the grid size
                        if input_op.inputs and len(input_op.inputs) > 0:
                            img_val = input_op.inputs[0]
                            if hasattr(img_val, 'resource_index') and img_val.resource_index is not None:
                                res_idx = img_val.resource_index
                                if res_idx in context.grid_sizes:
                                    size = context.grid_sizes[res_idx]
                                    if component == 'x' or component == 'r':
                                        return float(size[0])  # Width
                                    elif component == 'y' or component == 'g':
                                        return float(size[1])  # Height
                                    elif component == 'z' or component == 'b':
                                        return float(size[2]) if len(size) > 2 else 1.0  # Depth
                        # Fallback to context
                        if component == 'x' or component == 'r':
                            return float(context.context_width)
                        elif component == 'y' or component == 'g':
                            return float(context.context_height)
                        elif component == 'z' or component == 'b':
                            return float(context.context_depth)
                
                # Regular scalar input - just return it
                return self.evaluate(input_val, context)
            return 0.0
        
        # === CAST ===
        if opcode == OpCode.CAST:
            if inputs and len(inputs) > 0:
                return self._eval_input(inputs, 0, context)
            return 0.0
        
        # === SELECT (Ternary) ===
        if opcode == OpCode.SELECT:
            cond = self._eval_input(inputs, 0, context) if len(inputs) > 0 else 0.0
            a = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            b = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.0
            return b if cond > 0.5 else a
        
        # === MULTIPLY_ADD ===
        if opcode == OpCode.MULTIPLY_ADD:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            c = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.0
            return a * b + c
        
        # === SMOOTHSTEP ===
        if opcode == OpCode.SMOOTHSTEP:
            edge0 = self._eval_input(inputs, 0, context)
            edge1 = self._eval_input(inputs, 1, context)
            x = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.5
            # Clamp x to 0-1 range based on edges
            if abs(edge1 - edge0) < 1e-10:
                t = 0.0
            else:
                t = (x - edge0) / (edge1 - edge0)
            t = max(0.0, min(1.0, t))
            return t * t * (3.0 - 2.0 * t)
        
        # === STEP ===
        if opcode == OpCode.STEP:
            edge = self._eval_input(inputs, 0, context)
            x = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            return 1.0 if x >= edge else 0.0
        
        # === PINGPONG ===
        if opcode == OpCode.PINGPONG:
            v = self._eval_input(inputs, 0, context)
            scale = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 1.0
            if abs(scale) < 1e-10:
                return 0.0
            # pingpong(v, scale) = scale - abs(mod(v, 2*scale) - scale)
            t = v % (2.0 * scale)
            return scale - abs(t - scale)
        
        # === SNAP ===
        if opcode == OpCode.SNAP:
            v = self._eval_input(inputs, 0, context)
            increment = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 1.0
            if abs(increment) < 1e-10:
                return v
            return math.floor(v / increment + 0.5) * increment
        
        # === WRAP ===
        if opcode == OpCode.WRAP:
            v = self._eval_input(inputs, 0, context)
            lo = self._eval_input(inputs, 1, context) if len(inputs) > 1 else 0.0
            hi = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 1.0
            range_size = hi - lo
            if abs(range_size) < 1e-10:
                return lo
            return lo + ((v - lo) % range_size)
        
        # === COMPARE ===
        if opcode == OpCode.COMPARE:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            epsilon = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.00001
            return 1.0 if abs(a - b) <= epsilon else 0.0
        
        # === SMOOTH_MIN / SMOOTH_MAX ===
        if opcode == OpCode.SMOOTH_MIN:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            k = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.1
            if k <= 0:
                return min(a, b)
            h = max(0.0, min(1.0, 0.5 + 0.5 * (b - a) / k))
            return a * h + b * (1.0 - h) - k * h * (1.0 - h)
        
        if opcode == OpCode.SMOOTH_MAX:
            a = self._eval_input(inputs, 0, context)
            b = self._eval_input(inputs, 1, context)
            k = self._eval_input(inputs, 2, context) if len(inputs) > 2 else 0.1
            if k <= 0:
                return max(a, b)
            h = max(0.0, min(1.0, 0.5 + 0.5 * (a - b) / k))
            return a * h + b * (1.0 - h) + k * h * (1.0 - h)
        
        # === IMAGE_SIZE (Grid Info) ===
        # Returns size of texture from grid_sizes dict
        if opcode == OpCode.IMAGE_SIZE:
            # Get resource index from input
            if inputs and len(inputs) > 0:
                img_val = inputs[0]
                res_idx = getattr(img_val, 'resource_index', None)
                if res_idx is not None and res_idx in context.grid_sizes:
                    size = context.grid_sizes[res_idx]
                    # Return as tuple (width, height, depth)
                    return size
            # Fallback to context dimensions
            return (context.context_width, context.context_height, context.context_depth)
        
        # === SWIZZLE ===
        # Extract component from vector/tuple
        if opcode == OpCode.SWIZZLE:
            vec = self._eval_input(inputs, 0, context)
            mask = attrs.get('mask', 'x')
            
            # Handle tuple/list results from IMAGE_SIZE
            if isinstance(vec, (tuple, list)):
                idx_map = {'x': 0, 'y': 1, 'z': 2, 'w': 3}
                idx = idx_map.get(mask, 0)
                if idx < len(vec):
                    return float(vec[idx])
                return 0.0
            # Scalar passthrough
            return float(vec) if isinstance(vec, (int, float)) else 0.0
        
        # === UNKNOWN ===
        logger.warning(f"ScalarEvaluator: Unknown opcode {opcode}, returning 0")
        return 0.0
    
    def _eval_input(self, inputs: list, idx: int, context: EvalContext) -> float:
        """Evaluate input at index, or return 0 if not available."""
        if idx < len(inputs):
            return self.evaluate(inputs[idx], context)
        return 0.0
    
    def _to_scalar(self, value) -> float:
        """Convert any value to scalar float."""
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)):
            # Take first component
            if len(value) > 0:
                return float(value[0])
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    
    def clear_cache(self):
        """Clear evaluation cache between iterations."""
        self._cache.clear()
