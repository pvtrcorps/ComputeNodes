# Converter Node Handlers
# Handles: SeparateXYZ, CombineXYZ, SeparateColor, CombineColor

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_separate_xyz(node, ctx):
    """Handle ComputeNodeSeparateXYZ - separates vec3 into x, y, z components."""
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Get input vector
    val_vec = ctx.input_vec3(0, default=(0.0, 0.0, 0.0))
    
    # Create SEPARATE_XYZ op - single op with 3 outputs
    op = builder.add_op(OpCode.SEPARATE_XYZ, [val_vec])
    
    val_x = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="x")
    val_y = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="y")
    val_z = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="z")
    
    op.add_output(val_x)
    op.add_output(val_y)
    op.add_output(val_z)
    
    # Register all outputs
    ctx.set_output(0, val_x)  # X
    ctx.set_output(1, val_y)  # Y
    ctx.set_output(2, val_z)  # Z
    
    # Return requested output
    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_x


def handle_combine_xyz(node, ctx):
    """Handle ComputeNodeCombineXYZ - combines x, y, z into vec3."""
    builder = ctx.builder
    
    # Get input components
    val_x = ctx.input_float(0, default=0.0)
    val_y = ctx.input_float(1, default=0.0)
    val_z = ctx.input_float(2, default=0.0)
    
    # Create COMBINE_XYZ op
    op = builder.add_op(OpCode.COMBINE_XYZ, [val_x, val_y, val_z])
    val_out = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op)
    op.add_output(val_out)
    
    # Register output
    ctx.set_output(0, val_out)
    return val_out


def handle_separate_color(node, ctx):
    """Handle ComputeNodeSeparateColor - separates vec4 into components based on mode."""
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Get color mode
    mode = getattr(node, 'mode', 'RGB')
    
    # Get input color
    val_color = ctx.input_vec4(0, default=(0.8, 0.8, 0.8, 1.0))
    
    # Create SEPARATE_COLOR op with mode attribute
    op = builder.add_op(OpCode.SEPARATE_COLOR, [val_color], attrs={'mode': mode})
    
    val_0 = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="c0")
    val_1 = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="c1")
    val_2 = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="c2")
    val_a = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="alpha")
    
    op.add_output(val_0)
    op.add_output(val_1)
    op.add_output(val_2)
    op.add_output(val_a)
    
    # Register all outputs
    ctx.set_output(0, val_0)
    ctx.set_output(1, val_1)
    ctx.set_output(2, val_2)
    ctx.set_output(3, val_a)
    
    # Return requested output
    if output_socket_needed:
        req_key = ctx._get_socket_key(output_socket_needed)
        if req_key in ctx._socket_value_map:
            return ctx._socket_value_map[req_key]
    return val_0


def handle_combine_color(node, ctx):
    """Handle ComputeNodeCombineColor - combines components into vec4 based on mode."""
    builder = ctx.builder
    
    # Get color mode
    mode = getattr(node, 'mode', 'RGB')
    
    # Get input components
    val_0 = ctx.input_float(0, default=0.0)
    val_1 = ctx.input_float(1, default=0.0)
    val_2 = ctx.input_float(2, default=0.0)
    val_a = ctx.input_float(3, default=1.0)
    
    # Create COMBINE_COLOR op with mode attribute
    op = builder.add_op(OpCode.COMBINE_COLOR, [val_0, val_1, val_2, val_a], attrs={'mode': mode})
    val_out = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    op.add_output(val_out)
    
    # Register output
    ctx.set_output(0, val_out)
    return val_out


def handle_map_range(node, ctx):
    """Handle ComputeNodeMapRange - remaps value from one range to another."""
    builder = ctx.builder
    
    # Get node properties
    data_type = getattr(node, 'data_type', 'FLOAT')
    interpolation_type = getattr(node, 'interpolation_type', 'LINEAR')
    clamp = getattr(node, 'clamp', False)
    
    is_vector = data_type == 'FLOAT_VECTOR'
    target_type = DataType.VEC3 if is_vector else DataType.FLOAT
    
    if is_vector:
        # Vector mode: use vector sockets via NAME because indices might change or be ambiguous
        # Actually, let's look at the node definition if possible.
        # But safest is name lookup for this node as it has dynamic sockets.
        val_value = ctx.input_vec3('Vector', default=(0.0, 0.0, 0.0))
        val_from_min = ctx.input_vec3('From Min', default=(0.0, 0.0, 0.0)) # Note: Names might need verification
        # Wait, usually for Vector mode it reveals different sockets.
        # Let's check typical Blender node socket names.
        # Assuming standard names: 'Vector', 'From Min Vector', etc.
        # Update: In my previous view of converter.py, it used:
        # inputs['Vector'], inputs['From Min (Vec)'], inputs['From Max (Vec)']...
        val_from_min = ctx.input_vec3('From Min', default=(0.0, 0.0, 0.0)) # Fallback if names differ?
        # Let's double check implementation I read.
        # It had: val_from_min = get_socket_value(node.inputs['From Min (Vec)'])
        val_from_min = ctx.input_vec3('From Min (Vec)', default=(0.0, 0.0, 0.0))
        val_from_max = ctx.input_vec3('From Max (Vec)', default=(1.0, 1.0, 1.0))
        val_to_min = ctx.input_vec3('To Min (Vec)', default=(0.0, 0.0, 0.0))
        val_to_max = ctx.input_vec3('To Max (Vec)', default=(1.0, 1.0, 1.0))
        
    else:
        # Float mode
        val_value = ctx.input_float('Value', default=0.0)
        val_from_min = ctx.input_float('From Min', default=0.0)
        val_from_max = ctx.input_float('From Max', default=1.0)
        val_to_min = ctx.input_float('To Min', default=0.0)
        val_to_max = ctx.input_float('To Max', default=1.0)
    
    # Steps is always float
    val_steps = ctx.input_float('Steps', default=4.0)
    
    # Build inputs list
    inputs = [val_value, val_from_min, val_from_max, val_to_min, val_to_max, val_steps]
    
    # Create MAP_RANGE op with attributes
    attrs = {
        'interpolation_type': interpolation_type,
        'clamp': clamp,
        'data_type': data_type,
    }
    op = builder.add_op(OpCode.MAP_RANGE, inputs, attrs=attrs)
    val_out = builder._new_value(ValueKind.SSA, target_type, origin=op)
    op.add_output(val_out)
    
    # Register correct output socket based on mode
    if is_vector:
        ctx.set_output('Vector Result', val_out)
    else:
        ctx.set_output('Result', val_out)
    return val_out


def handle_clamp(node, ctx):
    """Handle ComputeNodeClamp - clamps value between min and max."""
    builder = ctx.builder
    
    # Get node properties
    clamp_type = getattr(node, 'clamp_type', 'MINMAX')
    
    # Get input values
    val_value = ctx.input_float(0, default=0.0)
    val_min = ctx.input_float(1, default=0.0)
    val_max = ctx.input_float(2, default=1.0)
    
    # Create CLAMP_RANGE op with mode attribute
    attrs = {'clamp_type': clamp_type}
    op = builder.add_op(OpCode.CLAMP_RANGE, [val_value, val_min, val_max], attrs=attrs)
    val_out = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    op.add_output(val_out)
    
    ctx.set_output(0, val_out)
    return val_out
