# Control Flow Node Handlers
# Handles: ComputeNodePosition, ComputeNodeSwitch, ComputeNodeMix

from typing import Optional, Any
from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_position(node, ctx):
    """
    Handle ComputeNodePosition node.
    
    Outputs:
    - Coordinate: raw ivec3 from gl_GlobalInvocationID
    - Normalized: vec3(x/w, y/h, z/d) using u_dispatch uniforms
    - Global Index: linearized index (y * width + x)
    
    For 2D dispatches (depth=1), Z will be 0/1 = 0.
    For 3D dispatches, Z will be properly normalized.
    """
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Builtin: gl_GlobalInvocationID -> uvec3
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_pos = builder.cast(val_gid, DataType.VEC3)
    
    ctx.set_output(0, val_pos)  # "Coordinate"

    # Normalized Output using u_dispatch uniforms (all 3 dimensions)
    if len(node.outputs) > 1:
        # Use u_dispatch_width/height/depth uniforms
        # These are set per-pass to the actual dispatch size
        val_width = builder.builtin("u_dispatch_width", DataType.INT)
        val_height = builder.builtin("u_dispatch_height", DataType.INT)
        val_depth = builder.builtin("u_dispatch_depth", DataType.INT)
        
        # Convert to float for division
        val_width_f = builder.cast(val_width, DataType.FLOAT)
        val_height_f = builder.cast(val_height, DataType.FLOAT)
        val_depth_f = builder.cast(val_depth, DataType.FLOAT)
        
        # Build vec3(width, height, depth) for division
        op_size = builder.add_op(OpCode.COMBINE_XYZ, [val_width_f, val_height_f, val_depth_f])
        val_size_vec3 = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op_size)
        op_size.add_output(val_size_vec3)
        
        # CRITICAL FIX: Add 0.5 texel offset for texel-center sampling
        # Without this, UV = pos/size points to texel corners (0/512, 1/512...)
        # texture() with bilinear filtering expects texel centers ((pos+0.5)/size)
        # In loops with Sample+Capture, this 0.5 texel error accumulates per iteration
        val_half = builder.constant(0.5, DataType.FLOAT)
        val_half_vec3 = builder.add_op(OpCode.COMBINE_XYZ, [val_half, val_half, val_half])
        val_offset = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=val_half_vec3)
        val_half_vec3.add_output(val_offset)
        
        # pos + 0.5
        op_offset_pos = builder.add_op(OpCode.ADD, [val_pos, val_offset])
        val_centered_pos = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op_offset_pos)
        op_offset_pos.add_output(val_centered_pos)
        
        # Normalize: (pos + 0.5) / size -> texel center UVs
        op_div = builder.add_op(OpCode.DIV, [val_centered_pos, val_size_vec3])
        val_norm = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op_div)
        op_div.add_output(val_norm)
        
        ctx.set_output(1, val_norm)


    # Global Index Output
    if len(node.outputs) > 2:
        val_gid_uvec = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_num_wg = builder.builtin("gl_NumWorkGroups", DataType.UVEC3)
        val_wg_size = builder.builtin("gl_WorkGroupSize", DataType.UVEC3)
        
        op_size = builder.add_op(OpCode.MUL, [val_num_wg, val_wg_size])
        val_size = builder._new_value(ValueKind.SSA, DataType.UVEC3, origin=op_size)
        op_size.add_output(val_size)
        
        val_x = builder.swizzle(val_gid_uvec, "x")
        val_y = builder.swizzle(val_gid_uvec, "y")
        val_width = builder.swizzle(val_size, "x")
        
        op_mul_idx = builder.add_op(OpCode.MUL, [val_y, val_width])
        val_y_w = builder._new_value(ValueKind.SSA, DataType.UINT, origin=op_mul_idx)
        op_mul_idx.add_output(val_y_w)
        
        op_add_idx = builder.add_op(OpCode.ADD, [val_y_w, val_x])
        val_idx_uint = builder._new_value(ValueKind.SSA, DataType.UINT, origin=op_add_idx)
        op_add_idx.add_output(val_idx_uint)
        
        val_idx_int = builder.cast(val_idx_uint, DataType.INT)
        
        ctx.set_output(2, val_idx_int)

    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_pos


def handle_switch(node, ctx):
    """Handle ComputeNodeSwitch node (If/Else)."""
    builder = ctx.builder
    
    val_sw = ctx.input_float(0, default=0.0)
    val_false = ctx.get_input(1)
    val_true = ctx.get_input(2)
    
    if val_false is None: val_false = builder.constant(0.0, DataType.FLOAT)
    if val_true is None: val_true = builder.constant(0.0, DataType.FLOAT)
    
    target_type = DataType.FLOAT
    if node.data_type == 'VEC3': target_type = DataType.VEC3
    elif node.data_type == 'RGBA': target_type = DataType.VEC4
    
    val_sw = builder.cast(val_sw, DataType.FLOAT)
    val_false = builder.cast(val_false, target_type)
    val_true = builder.cast(val_true, target_type)
    
    op = builder.add_op(OpCode.SELECT, [val_false, val_true, val_sw])
    val_res = builder._new_value(ValueKind.SSA, target_type, origin=op)
    op.add_output(val_res)
    
    ctx.set_output(0, val_res)
    return val_res


def handle_mix(node, ctx):
    """Handle ComputeNodeMix node."""
    builder = ctx.builder
    
    val_fac = ctx.input_float(0, default=0.5)
    val_a = ctx.get_input(1)
    val_b = ctx.get_input(2)
    
    if val_a is None: val_a = builder.constant(0.0, DataType.FLOAT)
    if val_b is None: val_b = builder.constant(0.0, DataType.FLOAT)
    
    target_type = DataType.FLOAT
    if node.data_type == 'VEC3': target_type = DataType.VEC3
    elif node.data_type == 'RGBA': target_type = DataType.VEC4
    
    val_fac = builder.cast(val_fac, DataType.FLOAT)
    val_a = builder.cast(val_a, target_type)
    val_b = builder.cast(val_b, target_type)
    
    val_blend = val_b
    
    mode = 'MIX'
    if hasattr(node, "blend_type") and node.data_type == 'RGBA':
        mode = node.blend_type
        
    if mode == 'ADD':
        op_add = builder.add_op(OpCode.ADD, [val_a, val_b])
        val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_add)
        op_add.add_output(val_blend)
    elif mode == 'MULTIPLY':
        op_mul = builder.add_op(OpCode.MUL, [val_a, val_b])
        val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_mul)
        op_mul.add_output(val_blend)
    elif mode == 'SUBTRACT':
        op_sub = builder.add_op(OpCode.SUB, [val_a, val_b])
        val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_sub)
        op_sub.add_output(val_blend)
    elif mode == 'DIVIDE':
        op_div = builder.add_op(OpCode.DIV, [val_a, val_b])
        val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_div)
        op_div.add_output(val_blend)
    
    op_mix = builder.add_op(OpCode.SELECT, [val_a, val_blend, val_fac])
    val_res = builder._new_value(ValueKind.SSA, target_type, origin=op_mix)
    op_mix.add_output(val_res)
    
    ctx.set_output(0, val_res)
    return val_res
