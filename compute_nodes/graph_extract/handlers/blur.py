# Blur Handler - Gaussian blur for 2D/3D Grids
# Handles: ComputeNodeBlur
#
# Features:
# - Per-axis control (blur_x, blur_y, blur_z)
# - Variable blur via Field input
# - 2D and 3D grids

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType
from ...ir.ops import OpCode
from ...ir.graph import ValueKind


def handle_blur(node, ctx):
    """
    Handle ComputeNodeBlur node.
    
    Creates output grid(s) for separable blur passes.
    Stores metadata for shader generation.
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get properties
    dims = 3 if node.dimensions == '3D' else 2
    radius = node.radius
    iterations = node.iterations
    blur_x = node.blur_x
    blur_y = node.blur_y
    blur_z = node.blur_z if dims == 3 else False
    
    # Which axes to blur
    axes = []
    if blur_x: axes.append('x')
    if blur_y: axes.append('y')
    if blur_z and dims == 3: axes.append('z')
    
    if not axes:
        logger.warning(f"Blur '{node.name}': No axes enabled, passing through")
        # Pass through input unchanged
        val_input = get_socket_value(node.inputs[0])
        out_key = get_socket_key(node.outputs[0])
        socket_value_map[out_key] = val_input
        return val_input
    
    # Get input grid
    val_input = get_socket_value(node.inputs[0])
    
    if val_input is None:
        logger.warning(f"Blur '{node.name}': No input grid")
        return None
    
    if val_input.type != DataType.HANDLE:
        raise TypeError(
            f"Blur '{node.name}' requires a Grid input.\n"
            f"Got: {val_input.type.name}"
        )
    
    # Check for variable radius Field input
    radius_socket = node.inputs[1]  # Radius socket
    val_radius = None
    if radius_socket.is_linked:
        val_radius = get_socket_value(radius_socket)
    
    # Get source resource for dimensions
    source_resource = None
    if val_input.resource_index is not None:
        source_resource = builder.graph.resources[val_input.resource_index]
    
    if source_resource is None:
        raise ValueError(f"Blur '{node.name}': Could not find input resource")
    
    # Get size
    size = source_resource.size
    width = size[0]
    height = size[1]
    depth = size[2] if dims == 3 else 1
    
    # Create output grid
    output_name = f"blur_{node.name}"
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.WRITE,  # WRITE for pass separation
        format='RGBA32F',
        size=(width, height, depth) if dims == 3 else (width, height),
        dimensions=dims,
        is_internal=True
    )
    val_output = builder.add_resource(desc)
    
    # Store blur metadata
    if not hasattr(builder.graph, 'blur_ops'):
        builder.graph.blur_ops = []
    
    blur_info = {
        'input_idx': val_input.resource_index,
        'output_idx': val_output.resource_index,
        'radius': radius,
        'axes': axes,
        'iterations': iterations,
        'dimensions': dims,
        'size': (width, height, depth),
        'has_variable_radius': val_radius is not None,
    }
    builder.graph.blur_ops.append(blur_info)
    
    # Emit BLUR op
    inputs = [val_input]
    if val_radius is not None:
        inputs.append(val_radius)
        
    op = builder.add_op(OpCode.BLUR, inputs)
    op.metadata = blur_info
    
    val_output_value = builder._new_value(ValueKind.SSA, DataType.HANDLE, origin=op)
    val_output_value.resource_index = val_output.resource_index
    op.add_output(val_output_value)
    
    # Store in socket map
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output_value
    
    return val_output_value
