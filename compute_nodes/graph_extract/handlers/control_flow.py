# Control Flow Node Handlers
# Handles: ComputeNodePosition, ComputeNodeSwitch, ComputeNodeMix, ComputeNodeRepeatOutput, ComputeNodeRepeatInput

from typing import Optional, Any
from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_position(node, ctx):
    """Handle ComputeNodePosition node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Builtin: gl_GlobalInvocationID -> uvec3
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_pos = builder.cast(val_gid, DataType.VEC3)
    
    out_key = get_socket_key(node.outputs[0])  # "Coordinate"
    socket_value_map[out_key] = val_pos

    # Normalized Output using u_dispatch uniforms (correct size)
    if len(node.outputs) > 1:
        # Use u_dispatch_width/height uniforms instead of gl_WorkGroups
        # These are set per-pass to the actual dispatch/output size
        val_width = builder.builtin("u_dispatch_width", DataType.INT)
        val_height = builder.builtin("u_dispatch_height", DataType.INT)
        
        # Build vec2(width, height) for division
        val_width_f = builder.cast(val_width, DataType.FLOAT)
        val_height_f = builder.cast(val_height, DataType.FLOAT)
        
        # Construct size vec2 using combine
        op_size = builder.add_op(OpCode.COMBINE_XY, [val_width_f, val_height_f])
        val_size_vec2 = builder._new_value(ValueKind.SSA, DataType.VEC2, origin=op_size)
        op_size.add_output(val_size_vec2)
        
        # Get xy position as vec2
        val_pos_xy = builder.swizzle(val_pos, "xy")
        
        # Normalize: pos.xy / size
        op_div = builder.add_op(OpCode.DIV, [val_pos_xy, val_size_vec2])
        val_norm_xy = builder._new_value(ValueKind.SSA, DataType.VEC2, origin=op_div)
        op_div.add_output(val_norm_xy)
        
        # Extend vec2 to vec3 using CONSTRUCT(vec2, 0) - which GLSL supports directly
        # Use CAST to vec3 which will become vec3(v, 0) or just output the vec2
        # Actually, let's extract x,y and use COMBINE_XYZ properly
        val_norm_x = builder.swizzle(val_norm_xy, "x")
        val_norm_y = builder.swizzle(val_norm_xy, "y")
        val_zero = builder.constant(0.0, DataType.FLOAT)
        
        op_extend = builder.add_op(OpCode.COMBINE_XYZ, [val_norm_x, val_norm_y, val_zero])
        val_norm = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op_extend)
        op_extend.add_output(val_norm)
        
        out_key_norm = get_socket_key(node.outputs[1])
        socket_value_map[out_key_norm] = val_norm

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
        
        out_key_idx = get_socket_key(node.outputs[2])
        socket_value_map[out_key_idx] = val_idx_int

    if output_socket_needed:
        req_key = get_socket_key(output_socket_needed)
        if req_key in socket_value_map:
            return socket_value_map[req_key]
    return val_pos


def handle_switch(node, ctx):
    """Handle ComputeNodeSwitch node (If/Else)."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_sw = get_socket_value(node.inputs[0])
    val_false = get_socket_value(node.inputs[1])
    val_true = get_socket_value(node.inputs[2])
    
    if val_sw is None: val_sw = builder.constant(0.0, DataType.FLOAT)
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
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_res
    return val_res


def handle_mix(node, ctx):
    """Handle ComputeNodeMix node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_fac = get_socket_value(node.inputs[0])
    val_a = get_socket_value(node.inputs[1])
    val_b = get_socket_value(node.inputs[2])
    
    if val_fac is None: val_fac = builder.constant(0.5, DataType.FLOAT)
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
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_res
    return val_res


def handle_repeat_output(node, ctx):
    """Handle ComputeNodeRepeatOutput node (Repeat Zone End)."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    def find_repeat_input(start_socket) -> Optional[Any]:
        stack = [start_socket]
        visited = set()
        while stack:
            sock = stack.pop()
            if sock in visited: continue
            visited.add(sock)
            
            if sock.is_linked:
                link = sock.links[0]
                nd = link.from_node
                if nd.bl_idname == 'ComputeNodeRepeatInput':
                    return nd
                for inp in nd.inputs:
                    stack.append(inp)
        return None

    repeat_input_node = find_repeat_input(node.inputs[0])
    
    if not repeat_input_node:
        import logging
        logging.getLogger(__name__).warning(f"Repeat Output {node.name} has no upstream Repeat Input connected.")
        return builder.constant(0.0, DataType.FLOAT)
    
    val_iters = get_socket_value(repeat_input_node.inputs[0])
    val_init = get_socket_value(repeat_input_node.inputs[1])
    
    if val_iters is None: val_iters = builder.constant(1, DataType.INT)
    if val_init is None: val_init = builder.constant(0.0, DataType.FLOAT)
    
    val_iters = builder.cast(val_iters, DataType.INT)
    val_init = builder.cast(val_init, DataType.FLOAT)
    
    op_start = builder.add_op(OpCode.LOOP_START, [val_iters, val_init])
    val_curr = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op_start)
    op_start.add_output(val_curr)
    
    val_idx = builder._new_value(ValueKind.SSA, DataType.INT, origin=op_start)
    op_start.add_output(val_idx)
    
    key_iter = get_socket_key(repeat_input_node.outputs[0])
    key_curr = get_socket_key(repeat_input_node.outputs[1])
    
    socket_value_map[key_iter] = val_idx
    socket_value_map[key_curr] = val_curr
    
    val_next = get_socket_value(node.inputs[0])
    
    if val_next is None:
        val_next = val_curr
        
    val_next = builder.cast(val_next, DataType.FLOAT)
    
    op_end = builder.add_op(OpCode.LOOP_END, [val_next, val_curr])
    val_final = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op_end)
    op_end.add_output(val_final)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_final
    
    return val_final


def handle_repeat_input(node, ctx):
    """Handle ComputeNodeRepeatInput node (Repeat Zone Start)."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    key_curr = get_socket_key(node.outputs[1])
    if key_curr in socket_value_map:
        return socket_value_map[key_curr]
        
    return builder.constant(0.0, DataType.FLOAT)
