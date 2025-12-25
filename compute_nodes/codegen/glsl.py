from typing import Dict, List, Set
from ..ir.graph import Graph, Op, Value, ValueKind
from ..ir.ops import OpCode
from ..ir.types import DataType
from ..ir.resources import ResourceDesc, ResourceType, ImageDesc
from ..planner.passes import ComputePass

from .shader_lib import HASH_GLSL, NOISE_GLSL, FRACTAL_GLSL, TEX_NOISE_GLSL, WHITE_NOISE_GLSL, VORONOI_GLSL, COLOR_GLSL, MAP_RANGE_GLSL

class ShaderGenerator:
    """
    Generates GLSL Compute Shader code from a ComputePass.
    """
    def __init__(self, graph: Graph):
        self.graph = graph

    def generate(self, compute_pass: ComputePass) -> str:
        sections = []
        
        # 1. Header
        sections.append(self._generate_header())
        
        # 2. Bindings / Layouts
        sections.append(self._generate_bindings(compute_pass))
        
        # 3. Main Function
        sections.append(self._generate_main(compute_pass))
        
        return "\n".join(sections)

    def _generate_header(self) -> str:
        lines = [
            # NOTE: layout(local_size_x/y/z) is NOT included here
            # Blender's GPUShaderCreateInfo.local_group_size() handles this
            "",
            # Inject Libraries
            HASH_GLSL,
            NOISE_GLSL,
            FRACTAL_GLSL,
            TEX_NOISE_GLSL,
            WHITE_NOISE_GLSL,
            VORONOI_GLSL,
            COLOR_GLSL,
            MAP_RANGE_GLSL,
            ""
        ]
        return "\n".join(lines)


    def _generate_bindings(self, compute_pass: ComputePass) -> str:
        lines = []
        # Combine reads and writes for binding generation
        # Use indices to lookup descriptions in Graph
        bound_resources = set()
        
        # Sort indices for deterministic binding order
        all_indices = sorted(list(compute_pass.reads_idx | compute_pass.writes_idx))
        
        for binding_idx, res_idx in enumerate(all_indices):
            res = self.graph.resources[res_idx]
            
            # TODO: Determine format based on usage or metadata. Defaulting to rgba32f/float
            # TODO: Determine format based on usage or metadata. Defaulting to rgba32f/float
            # Map Blender/GPUTexture formats to GLSL identifiers
            fmt_map = {
                'RGBA8': 'rgba8',
                'SRGB8_A8': 'rgba8', # Treat sRGB as rgba8 for storage (no auto-conversion in storage)
                'RGBA16F': 'rgba16f',
                'RGBA32F': 'rgba32f',
                'R32F': 'r32f',
                'RGBA8UI': 'rgba8ui',
                'RGBA8I': 'rgba8i',
            }
            raw_fmt = res.format.upper()
            fmt = fmt_map.get(raw_fmt, 'rgba32f') # Fallback to 32f if unknown
            
            # Determine restriction (readonly / writeonly / readwrite)
            # Simplification: If in writes -> volatile/coherent or restrict?
            # GLSL image binding qualifiers: writeonly, readonly
            qualifier = ""
            if res_idx in compute_pass.writes_idx and res_idx not in compute_pass.reads_idx:
                qualifier = "writeonly "
            elif res_idx in compute_pass.reads_idx and res_idx not in compute_pass.writes_idx:
                qualifier = "readonly "
            else:
                qualifier = "" # readwrite default

            if isinstance(res, ImageDesc):
                # image2D vs image3D etc. Assuming 2D
                # Simplified naming to avoid sanitized mismatches
                uniform_name = f"img_{res_idx}" 
                # Remove explicit binding to let Blender/Driver handle it via shader.image()
                # BLENDER API UPDATE: GPUShaderCreateInfo.image() automatically adds the uniform declaration.
                # So we must NOT add it here manually to avoid "redefinition" errors.
                # lines.append(f"layout({fmt}) uniform {qualifier}image2D {uniform_name};")
                pass
            
        lines.append("")
        return "\n".join(lines)

    def _generate_main(self, compute_pass: ComputePass) -> str:
        # Store current pass for emitter context
        self._current_pass = compute_pass
        
        lines = ["void main() {"]
        for op in compute_pass.ops:
            lines.append(self._emit_op(op))
        lines.append("}")
        return "\n".join(lines)


    def _param(self, val: Value) -> str:
        """Resolves a value to its GLSL string representation."""
        # Track emitted IDs for current pass
        if not hasattr(self, '_emitted_ids'):
            self._emitted_ids = set()
        
        if val.kind == ValueKind.SSA:
            # Check if this SSA value has a resource_index (e.g., from Blur output)
            # If so, use the resource binding name instead of SSA variable
            if val.resource_index is not None:
                return f"img_{val.resource_index}"  # Use same name as shader binding
            return f"v{val.id}"
        elif val.kind == ValueKind.CONSTANT:
            # If constant already emitted, use its variable
            if val.id in self._emitted_ids:
                return f"v{val.id}"
            # Otherwise, emit inline
            if val.origin and hasattr(val.origin, 'attrs'):
                const_val = val.origin.attrs.get('value')
                return self._format_constant(const_val, val.type)
            return f"v{val.id}"  # Fallback
        elif val.kind == ValueKind.ARGUMENT:
            # Resource Handle -> Use the uniform name generated in bindings
            return f"img_{val.resource_index}"
        elif val.kind == ValueKind.BUILTIN:
            return val.name_hint
        return "UNKNOWN"
    
    def _format_constant(self, value, dtype: DataType) -> str:
        """Format a Python value as GLSL literal."""
        from .emitters.const import format_constant
        return format_constant(value, dtype)

    def _sanitize_name(self, name: str) -> str:
        # Replace non-alphanumeric chars with underscore
        import re
        s = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        # Collapse multiple underscores to avoid reserved identifiers
        s = re.sub(r'_+', '_', s)
        # Ensure it doesn't start with digit
        if s[0].isdigit():
            s = "_" + s
        return s

    def _type_str(self, dtype: DataType) -> str:
        # Simple mapping
        name = dtype.name.lower() # vec3, float, ivec2
        if name == 'uvec2': return 'uvec2' # check casing
        return name

    def _emit_op(self, op: Op) -> str:
        """Emit GLSL code for an operation using the modular emitter registry."""
        from .emitters import get_emitter
        
        # Ops that handle their own output declarations (multi-output or special)
        self_declaring_ops = {OpCode.IMAGE_STORE, OpCode.SEPARATE_XYZ, OpCode.SEPARATE_COLOR}
        
        # Handle Output definition (if SSA)
        lhs = ""
        if op.outputs and op.opcode not in self_declaring_ops:
            out_val = op.outputs[0]
            type_name = self._type_str(out_val.type)
            lhs = f"    {type_name} v{out_val.id} = "
        else:
            lhs = "    "

        # Build context for emitter
        dispatch = getattr(self, '_current_pass', None)
        dispatch_size = dispatch.dispatch_size if dispatch else (512, 512, 1)
        
        # Build set of op IDs in current pass for cross-pass detection
        current_op_ids = set()
        if dispatch and hasattr(dispatch, 'ops'):
            current_op_ids = {id(op) for op in dispatch.ops}
        
        ctx = {
            'lhs': lhs,
            'param': self._param,
            'type_str': self._type_str,
            'graph': self.graph,
            'dispatch_size': dispatch_size,
            'op_ids': current_op_ids,
        }
        
        # Look up emitter in registry
        emitter = get_emitter(op.opcode)
        
        if emitter is not None:
            result = emitter(op, ctx)
            # Handle callable (lambda) or string result
            if callable(result):
                return result
            return result
        
        # Fallback
        return f"    // Op {op.opcode.name} not implemented"

