# Converter Node Handlers
# Handles: SeparateXYZ, CombineXYZ, SeparateColor, CombineColor

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType


def handle_separate_xyz(node, ctx):
    """Handle ComputeNodeSeparateXYZ - separates vec3 into x, y, z components."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Get input vector
    val_vec = get_socket_value(node.inputs[0])
    if val_vec is None:
        val_vec = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
    
    # Ensure VEC3
    if val_vec.type != DataType.VEC3:
        val_vec = builder.cast(val_vec, DataType.VEC3)
    
    # Create SEPARATE_XYZ op - single op with 3 outputs
    op = builder.add_op(OpCode.SEPARATE_XYZ, [val_vec])
    
    val_x = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="x")
    val_y = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="y")
    val_z = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op, name_hint="z")
    
    op.add_output(val_x)
    op.add_output(val_y)
    op.add_output(val_z)
    
    # Register all outputs
    socket_value_map[get_socket_key(node.outputs[0])] = val_x  # X
    socket_value_map[get_socket_key(node.outputs[1])] = val_y  # Y
    socket_value_map[get_socket_key(node.outputs[2])] = val_z  # Z
    
    # Return requested output
    if output_socket_needed:
        return socket_value_map.get(get_socket_key(output_socket_needed), val_x)
    return val_x


def handle_combine_xyz(node, ctx):
    """Handle ComputeNodeCombineXYZ - combines x, y, z into vec3."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Get input components
    val_x = get_socket_value(node.inputs[0])
    val_y = get_socket_value(node.inputs[1])
    val_z = get_socket_value(node.inputs[2])
    
    if val_x is None: val_x = builder.constant(0.0, DataType.FLOAT)
    if val_y is None: val_y = builder.constant(0.0, DataType.FLOAT)
    if val_z is None: val_z = builder.constant(0.0, DataType.FLOAT)
    
    # Ensure FLOAT
    if val_x.type != DataType.FLOAT: val_x = builder.cast(val_x, DataType.FLOAT)
    if val_y.type != DataType.FLOAT: val_y = builder.cast(val_y, DataType.FLOAT)
    if val_z.type != DataType.FLOAT: val_z = builder.cast(val_z, DataType.FLOAT)
    
    # Create COMBINE_XYZ op
    op = builder.add_op(OpCode.COMBINE_XYZ, [val_x, val_y, val_z])
    val_out = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op)
    op.add_output(val_out)
    
    # Register output
    socket_value_map[get_socket_key(node.outputs[0])] = val_out
    return val_out


def handle_separate_color(node, ctx):
    """Handle ComputeNodeSeparateColor - separates vec4 into components based on mode."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Get color mode
    mode = getattr(node, 'mode', 'RGB')
    
    # Get input color
    val_color = get_socket_value(node.inputs[0])
    if val_color is None:
        val_color = builder.constant((0.8, 0.8, 0.8, 1.0), DataType.VEC4)
    
    # Ensure VEC4
    if val_color.type == DataType.VEC3:
        val_color = builder.cast(val_color, DataType.VEC4)
    elif val_color.type != DataType.VEC4:
        val_color = builder.cast(val_color, DataType.VEC4)
    
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
    socket_value_map[get_socket_key(node.outputs[0])] = val_0  # R/H
    socket_value_map[get_socket_key(node.outputs[1])] = val_1  # G/S
    socket_value_map[get_socket_key(node.outputs[2])] = val_2  # B/V/L
    socket_value_map[get_socket_key(node.outputs[3])] = val_a  # Alpha
    
    # Return requested output
    if output_socket_needed:
        return socket_value_map.get(get_socket_key(output_socket_needed), val_0)
    return val_0


def handle_combine_color(node, ctx):
    """Handle ComputeNodeCombineColor - combines components into vec4 based on mode."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Get color mode
    mode = getattr(node, 'mode', 'RGB')
    
    # Get input components
    val_0 = get_socket_value(node.inputs[0])  # R/H
    val_1 = get_socket_value(node.inputs[1])  # G/S
    val_2 = get_socket_value(node.inputs[2])  # B/V/L
    val_a = get_socket_value(node.inputs[3])  # Alpha
    
    if val_0 is None: val_0 = builder.constant(0.0, DataType.FLOAT)
    if val_1 is None: val_1 = builder.constant(0.0, DataType.FLOAT)
    if val_2 is None: val_2 = builder.constant(0.0, DataType.FLOAT)
    if val_a is None: val_a = builder.constant(1.0, DataType.FLOAT)
    
    # Ensure FLOAT
    if val_0.type != DataType.FLOAT: val_0 = builder.cast(val_0, DataType.FLOAT)
    if val_1.type != DataType.FLOAT: val_1 = builder.cast(val_1, DataType.FLOAT)
    if val_2.type != DataType.FLOAT: val_2 = builder.cast(val_2, DataType.FLOAT)
    if val_a.type != DataType.FLOAT: val_a = builder.cast(val_a, DataType.FLOAT)
    
    # Create COMBINE_COLOR op with mode attribute
    op = builder.add_op(OpCode.COMBINE_COLOR, [val_0, val_1, val_2, val_a], attrs={'mode': mode})
    val_out = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
    op.add_output(val_out)
    
    # Register output
    socket_value_map[get_socket_key(node.outputs[0])] = val_out
    return val_out


def handle_map_range(node, ctx):
    """Handle ComputeNodeMapRange - remaps value from one range to another."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Get node properties
    data_type = getattr(node, 'data_type', 'FLOAT')
    interpolation_type = getattr(node, 'interpolation_type', 'LINEAR')
    clamp = getattr(node, 'clamp', False)
    
    is_vector = data_type == 'FLOAT_VECTOR'
    target_type = DataType.VEC3 if is_vector else DataType.FLOAT
    
    if is_vector:
        # Vector mode: use vector sockets
        # Socket indices: 0-4 float, 5-9 vector, 10 steps
        val_value = get_socket_value(node.inputs['Vector'])
        val_from_min = get_socket_value(node.inputs['From Min (Vec)'])
        val_from_max = get_socket_value(node.inputs['From Max (Vec)'])
        val_to_min = get_socket_value(node.inputs['To Min (Vec)'])
        val_to_max = get_socket_value(node.inputs['To Max (Vec)'])
        
        if val_value is None: val_value = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
        if val_from_min is None: val_from_min = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
        if val_from_max is None: val_from_max = builder.constant((1.0, 1.0, 1.0), DataType.VEC3)
        if val_to_min is None: val_to_min = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
        if val_to_max is None: val_to_max = builder.constant((1.0, 1.0, 1.0), DataType.VEC3)
        
        # Ensure VEC3 type
        if val_value.type != DataType.VEC3: val_value = builder.cast(val_value, DataType.VEC3)
        if val_from_min.type != DataType.VEC3: val_from_min = builder.cast(val_from_min, DataType.VEC3)
        if val_from_max.type != DataType.VEC3: val_from_max = builder.cast(val_from_max, DataType.VEC3)
        if val_to_min.type != DataType.VEC3: val_to_min = builder.cast(val_to_min, DataType.VEC3)
        if val_to_max.type != DataType.VEC3: val_to_max = builder.cast(val_to_max, DataType.VEC3)
    else:
        # Float mode: use float sockets
        val_value = get_socket_value(node.inputs['Value'])
        val_from_min = get_socket_value(node.inputs['From Min'])
        val_from_max = get_socket_value(node.inputs['From Max'])
        val_to_min = get_socket_value(node.inputs['To Min'])
        val_to_max = get_socket_value(node.inputs['To Max'])
        
        if val_value is None: val_value = builder.constant(0.0, DataType.FLOAT)
        if val_from_min is None: val_from_min = builder.constant(0.0, DataType.FLOAT)
        if val_from_max is None: val_from_max = builder.constant(1.0, DataType.FLOAT)
        if val_to_min is None: val_to_min = builder.constant(0.0, DataType.FLOAT)
        if val_to_max is None: val_to_max = builder.constant(1.0, DataType.FLOAT)
        
        # Ensure FLOAT type
        if val_value.type != DataType.FLOAT: val_value = builder.cast(val_value, DataType.FLOAT)
        if val_from_min.type != DataType.FLOAT: val_from_min = builder.cast(val_from_min, DataType.FLOAT)
        if val_from_max.type != DataType.FLOAT: val_from_max = builder.cast(val_from_max, DataType.FLOAT)
        if val_to_min.type != DataType.FLOAT: val_to_min = builder.cast(val_to_min, DataType.FLOAT)
        if val_to_max.type != DataType.FLOAT: val_to_max = builder.cast(val_to_max, DataType.FLOAT)
    
    # Steps is always float
    val_steps = get_socket_value(node.inputs['Steps'])
    if val_steps is None: val_steps = builder.constant(4.0, DataType.FLOAT)
    if val_steps.type != DataType.FLOAT: val_steps = builder.cast(val_steps, DataType.FLOAT)
    
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
        socket_value_map[get_socket_key(node.outputs['Vector Result'])] = val_out
    else:
        socket_value_map[get_socket_key(node.outputs['Result'])] = val_out
    return val_out


def handle_clamp(node, ctx):
    """Handle ComputeNodeClamp - clamps value between min and max."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Get node properties
    clamp_type = getattr(node, 'clamp_type', 'MINMAX')
    
    # Get input values
    val_value = get_socket_value(node.inputs[0])
    val_min = get_socket_value(node.inputs[1])
    val_max = get_socket_value(node.inputs[2])
    
    if val_value is None: val_value = builder.constant(0.0, DataType.FLOAT)
    if val_min is None: val_min = builder.constant(0.0, DataType.FLOAT)
    if val_max is None: val_max = builder.constant(1.0, DataType.FLOAT)
    
    # Ensure FLOAT
    if val_value.type != DataType.FLOAT: val_value = builder.cast(val_value, DataType.FLOAT)
    if val_min.type != DataType.FLOAT: val_min = builder.cast(val_min, DataType.FLOAT)
    if val_max.type != DataType.FLOAT: val_max = builder.cast(val_max, DataType.FLOAT)
    
    # Create CLAMP_RANGE op with mode attribute
    attrs = {'clamp_type': clamp_type}
    op = builder.add_op(OpCode.CLAMP_RANGE, [val_value, val_min, val_max], attrs=attrs)
    val_out = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
    op.add_output(val_out)
    
    socket_value_map[get_socket_key(node.outputs[0])] = val_out
    return val_out
