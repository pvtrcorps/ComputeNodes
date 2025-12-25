# Output Image Handler - Grid Architecture
# Handles: ComputeNodeOutputImage
#
# IMPORTANT: Output Image expects GRID input only.
# Fields must go through Capture first.

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_output_image(node, ctx):
    """
    Handle ComputeNodeOutputImage node.
    
    Grid Architecture:
    - Input MUST be a GRID (HANDLE type)
    - Resolution is INHERITED from the input grid
    - If input is a Field (Color/Float/Vector), raise an error
    
    The handler copies the input grid to the output Image datablock.
    The actual GPU→CPU readback happens in the executor.
    
    Future output nodes:
    - handle_output_volume: Grid3D → OpenVDB
    - handle_output_sequence: Grid2D[] → Image sequence
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get properties from node
    output_name = node.output_name
    output_format = node.format
    
    # Get input data
    data_socket = node.inputs[0]  # "Grid" socket
    val_data = get_socket_value(data_socket)
    
    if val_data is None:
        logger.warning(f"Output Image '{node.name}': No grid connected")
        return None
    
    # VALIDATE: Input must be a GRID (HANDLE)
    if val_data.type != DataType.HANDLE:
        # This is a Field (Color/Float/Vector) - not a Grid!
        raise TypeError(
            f"Output Image '{node.name}' requires a Grid input.\n"
            f"Got: {val_data.type.name} (Field)\n"
            f"Solution: Insert a Capture node before Output Image to materialize the field."
        )
    
    # Find the source resource to get its dimensions
    source_resource = None
    if val_data.resource_index is not None:
        source_resource = builder.graph.resources[val_data.resource_index]
    
    # Get dimensions from source texture
    if source_resource and hasattr(source_resource, 'size'):
        output_width = source_resource.size[0]
        output_height = source_resource.size[1]
    else:
        logger.warning(f"Output '{node.name}': Could not determine input size, using 512x512")
        output_width = 512
        output_height = 512
    
    # Create ImageDesc for the output (writes to Blender Image)
    # is_internal=False means this needs a Blender Image datablock
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.WRITE,
        format=output_format,
        size=(output_width, output_height),
        dimensions=2,
        is_internal=False  # This is an OUTPUT - needs Blender Image
    )
    val_target = builder.add_resource(desc)
    
    # Sample input texture at normalized UVs
    # Use placeholder UV - emit_sample will generate inline UVs
    val_placeholder_uv = builder.constant((0.5, 0.5), DataType.VEC2)
    val_sampled = builder.sample(val_data, val_placeholder_uv)
    
    # Write to output using gl_GlobalInvocationID
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_gid_xy = builder.swizzle(val_gid, "xy")
    val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
    builder.image_store(val_target, val_coord, val_sampled)
    
    return val_target
