# Capture Handler
# Handles: ComputeNodeCapture
# Materializes a Field to a Grid at specified resolution

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_capture(node, ctx):
    """
    Handle ComputeNodeCapture node.
    
    Captures (materializes) a Field to a Grid at the specified resolution.
    This is the fundamental operation that converts lazy procedural data
    into concrete data that can be sampled at arbitrary coordinates.
    
    Grid Architecture:
    - Grid2D: width x height (dimensions == '2D')
    - Grid3D: width x height x depth (dimensions == '3D')
    """
    builder = ctx['builder']
    get_socket_value = ctx['get_socket_value']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    # Get input value (Field)
    val_input = get_socket_value(node.inputs[0])
    
    if val_input is None:
        # Default to black if nothing connected
        val_input = builder.constant((0.0, 0.0, 0.0, 1.0), DataType.VEC4)
    
    # Determine dimensions from node property
    is_3d = getattr(node, 'dimensions', '2D') == '3D'
    dims = 3 if is_3d else 2
    
    # Get target resolution
    target_width = node.width
    target_height = node.height
    target_depth = getattr(node, 'depth', 1) if is_3d else 1
    
    # Create size tuple based on dimensions
    if is_3d:
        size = (target_width, target_height, target_depth)
    else:
        size = (target_width, target_height)
    
    # Create output Grid (ImageDesc)
    output_name = f"grid_{node.name}"
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format="rgba32f",
        size=size,
        dimensions=dims
    )
    val_output = builder.add_resource(desc)
    
    # Ensure input is VEC4 for storage
    if val_input.type == DataType.VEC3:
        val_input = builder.cast(val_input, DataType.VEC4)
    elif val_input.type == DataType.FLOAT:
        val_input = builder.cast(val_input, DataType.VEC4)
    elif val_input.type == DataType.HANDLE:
        # Input is already a Grid - sample it at current position
        # This allows chaining: Grid -> Capture (resize equivalent)
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        if is_3d:
            val_coord_ivec = builder.cast(val_gid, DataType.IVEC3)
        else:
            val_coord = builder.swizzle(val_gid, "xy")
            val_coord_ivec = builder.cast(val_coord, DataType.IVEC2)
        val_input = builder.image_load(val_input, val_coord_ivec)
    
    # Compute output coordinates based on dimensions
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    if is_3d:
        val_coord_ivec = builder.cast(val_gid, DataType.IVEC3)
    else:
        val_coord = builder.swizzle(val_gid, "xy")
        val_coord_ivec = builder.cast(val_coord, DataType.IVEC2)
    
    # Write to Grid
    builder.image_store(val_output, val_coord_ivec, val_input)
    
    # Store output in socket map
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output
    
    return val_output


