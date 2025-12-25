# Resize Handler - Grid Architecture
# Handles: ComputeNodeResize
# Texture → Texture operation (uses bilinear/trilinear sampling)

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_resize(node, ctx):
    """
    Handle ComputeNodeResize node.
    
    Grid Architecture:
    - Input MUST be a GRID (HANDLE type)
    - Output is a new grid at target resolution
    - Supports 2D and 3D grids
    """
    builder = ctx['builder']
    get_socket_value = ctx['get_socket_value']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get input value
    val_input = get_socket_value(node.inputs[0])
    
    if val_input is None:
        logger.warning(f"Resize node '{node.name}': No grid connected")
        return None
    
    # VALIDATE: Input must be a GRID (HANDLE)
    if val_input.type != DataType.HANDLE:
        raise TypeError(
            f"Resize node '{node.name}' requires a Grid input.\n"
            f"Got: {val_input.type.name}"
        )
    
    # Get dimensions and target size
    dims = 3 if node.dimensions == '3D' else 2
    target_width = node.width
    target_height = node.height
    target_depth = node.depth if dims == 3 else 1
    
    # Create output grid at target resolution
    output_name = f"resize_{node.name}"
    if dims == 3:
        size = (target_width, target_height, target_depth)
    else:
        size = (target_width, target_height)
        
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format="RGBA32F",
        size=size,
        dimensions=dims,
        is_internal=True
    )
    val_output = builder.add_resource(desc)
    
    # Sample input using placeholder UV
    if dims == 3:
        val_placeholder_uv = builder.constant((0.5, 0.5, 0.5), DataType.VEC3)
    else:
        val_placeholder_uv = builder.constant((0.5, 0.5), DataType.VEC2)
    val_sampled = builder.sample(val_input, val_placeholder_uv)
    
    # Write to output
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    if dims == 3:
        val_coord = builder.cast(val_gid, DataType.IVEC3)
        builder.image_store(val_output, val_coord, val_sampled)
    else:
        val_gid_xy = builder.swizzle(val_gid, "xy")
        val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
        builder.image_store(val_output, val_coord, val_sampled)
    
    # Store output in socket map
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output
    
    return val_output

