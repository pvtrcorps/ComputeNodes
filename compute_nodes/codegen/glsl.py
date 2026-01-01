from typing import Dict, List, Set, Any
from ..ir.graph import Graph, Op, Value, ValueKind
from ..ir.ops import OpCode
from ..ir.types import DataType
from ..ir.resources import ResourceDesc, ResourceType, ImageDesc
from ..planner.passes import ComputePass

# Tree-shaking registry for selective GLSL inclusion
from .shader_lib.registry import (
    generate_selective_header, 
    get_bundle_requirements,
    OPCODE_BUNDLE_REQUIREMENTS
)

# Mapping from OpCode to bundle keys
OPCODE_TO_BUNDLE_KEY = {
    OpCode.NOISE: 'noise',
    OpCode.WHITE_NOISE: 'white_noise',
    OpCode.VORONOI: 'voronoi',
    OpCode.SEPARATE_COLOR: 'separate_color',
    OpCode.COMBINE_COLOR: 'combine_color',
    OpCode.MAP_RANGE: 'map_range',
    OpCode.CLAMP_RANGE: 'map_range',  # Uses same bundle
}


class ShaderGenerator:
    """
    Generates GLSL Compute Shader code from a ComputePass.
    
    Uses tree-shaking to include only required GLSL library functions,
    dramatically reducing shader compilation time.
    """
    def __init__(self, graph: Graph):
        self.graph = graph

    def generate(self, compute_pass: ComputePass) -> str:
        # Initialize tracking for tree-shaking
        self._required_bundles: Set[str] = set()
        self._required_funcs: Set[str] = set()
        
        # Create resource index -> sequential binding slot mapping
        # GPU has max 8 binding slots (0-7), so we must remap sparse indices
        all_indices: List[int] = sorted(list(compute_pass.reads_idx | compute_pass.writes_idx))
        self._binding_map: Dict[int, int] = {res_idx: slot for slot, res_idx in enumerate(all_indices)}
        
        from ..logger import log_debug
        log_debug(f"Generating GLSL for pass (Ops: {len(compute_pass.ops)})...")
        
        # 1. Generate main first to discover required GLSL functions
        main_section = self._generate_main(compute_pass)
        
        # 2. Generate bindings
        bindings_section = self._generate_bindings(compute_pass)
        
        # 3. Generate selective header based on discovered requirements
        header_section = self._generate_selective_header()
        
        return "\n".join([header_section, bindings_section, main_section])

    def _generate_selective_header(self) -> str:
        """Generate minimal GLSL header with only needed functions."""
        return generate_selective_header(
            self._required_funcs, 
            self._required_bundles
        )

    def _generate_bindings(self, compute_pass: ComputePass) -> str:
        lines = []
        # Combine reads and writes for binding generation
        # Use indices to lookup descriptions in Graph
        bound_resources = set()
        
        # Sort indices for deterministic binding order
        all_indices = sorted(list(compute_pass.reads_idx | compute_pass.writes_idx))
        
        for binding_idx, res_idx in enumerate(all_indices):
            res = self.graph.resources[res_idx]
            
            # Map Blender/GPUTexture formats to GLSL identifiers
            fmt_map = {
                'RGBA8': 'rgba8',
                'SRGB8_A8': 'rgba8',
                'RGBA16F': 'rgba16f',
                'RGBA32F': 'rgba32f',
                'R32F': 'r32f',
                'RGBA8UI': 'rgba8ui',
                'RGBA8I': 'rgba8i',
            }
            raw_fmt = res.format.upper()
            fmt = fmt_map.get(raw_fmt, 'rgba32f')
            
            # Determine restriction (readonly / writeonly / readwrite)
            qualifier = ""
            if res_idx in compute_pass.writes_idx and res_idx not in compute_pass.reads_idx:
                qualifier = "writeonly "
            elif res_idx in compute_pass.reads_idx and res_idx not in compute_pass.writes_idx:
                qualifier = "readonly "
            else:
                qualifier = ""

            if isinstance(res, ImageDesc):
                # Use sequential binding slot for uniform name
                uniform_name = f"img_{binding_idx}" 
                # GPUShaderCreateInfo.image() handles uniform declaration
                pass
            
        lines.append("")
        # Standard uniforms
        # Use define to construct vector from existing push constants (Vulkan safe)
        lines.append("#define u_dispatch_size ivec3(u_dispatch_width, u_dispatch_height, u_dispatch_depth)")
        return "\n".join(lines)

    def _generate_main(self, compute_pass: ComputePass) -> str:
        # Store current pass for emitter context
        self._current_pass = compute_pass
        
        # Track emitted operations to prevent duplicate declarations
        self._emitted_op_ids = set()
        
        lines = ["void main() {"]
        for op in compute_pass.ops:
            # Track required GLSL for tree-shaking
            self._track_glsl_requirements(op)
            lines.append(self._emit_op(op))
        lines.append("}")
        return "\n".join(lines)

    def _track_glsl_requirements(self, op: Op):
        """Track which GLSL library bundles are needed for this operation."""
        if op.opcode in OPCODE_TO_BUNDLE_KEY:
            bundle_key = OPCODE_TO_BUNDLE_KEY[op.opcode]
            bundles = get_bundle_requirements(bundle_key)
            self._required_bundles.update(bundles)

    def _param(self, val: Value) -> str:
        """Resolves a value to its GLSL string representation."""
        # Track emitted IDs for current pass
        if not hasattr(self, '_emitted_ids'):
            self._emitted_ids = set()
        
        if val.kind == ValueKind.SSA:
            if val.resource_index is not None:
                # Use sequential binding slot from mapping
                slot = self._binding_map.get(val.resource_index, val.resource_index)
                return f"img_{slot}"
            return f"v{val.id}"
        elif val.kind == ValueKind.CONSTANT:
            if val.id in self._emitted_ids:
                return f"v{val.id}"
            if val.origin and hasattr(val.origin, 'attrs'):
                const_val = val.origin.attrs.get('value')
                return self._format_constant(const_val, val.type)
            return f"v{val.id}"
        elif val.kind == ValueKind.ARGUMENT:
            # Use sequential binding slot from mapping
            slot = self._binding_map.get(val.resource_index, val.resource_index)
            return f"img_{slot}"
        elif val.kind == ValueKind.BUILTIN:
            return val.name_hint
        return "UNKNOWN"
    
    def _format_constant(self, value: Any, dtype: DataType) -> str:
        """Format a Python value as GLSL literal."""
        from .emitters.const import format_constant
        return format_constant(value, dtype)

    def _sanitize_name(self, name: str) -> str:
        import re
        s = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        s = re.sub(r'_+', '_', s)
        if s[0].isdigit():
            s = "_" + s
        return s

    def _type_str(self, dtype: DataType) -> str:
        name = dtype.name.lower()
        if name == 'uvec2': return 'uvec2'
        return name

    def _emit_op(self, op: Op) -> str:
        """Emit GLSL code for an operation using the modular emitter registry."""
        from .emitters import get_emitter
        
        # Check if this op was already emitted (prevents duplicate declarations)
        op_id = id(op)
        if op_id in self._emitted_op_ids:
            return ""  # Skip duplicate
        self._emitted_op_ids.add(op_id)
        
        # Ops that handle their own output declarations
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
        
        current_op_ids = set()
        if dispatch and hasattr(dispatch, 'ops'):
            current_op_ids = {id(op) for op in dispatch.ops}
        
        dispatch_info = {
            'dispatch_size': dispatch_size,
            'op_ids': current_op_ids,
            # Pass-specific read/write info for sampler vs image detection
            'reads_idx': dispatch.reads_idx if dispatch else set(),
            'writes_idx': dispatch.writes_idx if dispatch else set(),
            # Binding map for resource index -> sequential slot mapping
            'binding_map': self._binding_map,
        }
        
        from .shader_context import ShaderContext
        ctx = ShaderContext(self, op, lhs, dispatch_info)
        
        emitter = get_emitter(op.opcode)
        
        if emitter is not None:
            result = emitter(op, ctx)
            
            # If emitter returns empty string, skip entire operation
            # (e.g., placeholder constants that should not be emitted)
            if result == "":
                return ""
            
            if callable(result):
                return result
            return result
        
        return f"    // Op {op.opcode.name} not implemented"
