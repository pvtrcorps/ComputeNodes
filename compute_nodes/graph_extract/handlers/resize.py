# Resize Handler - Field-Based Architecture
# Handles: ComputeNodeResize
# Texture → Texture operation ONLY (uses bilinear sampling)

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_resize(node, ctx):
    """
    Handle ComputeNodeResize node.
    
    Field-Based Architecture:
    - Input MUST be a TEXTURE (HANDLE type)
    - Output is a new texture at target resolution
    - Uses bilinear sampling for proper upscale/downscale
    
    If input is a Field, raise error guiding user to use Rasterize first.
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
        logger.warning(f"Resize node '{node.name}': No texture connected")
        return None
    
    # VALIDATE: Input must be a TEXTURE (HANDLE)
    if val_input.type != DataType.HANDLE:
        raise TypeError(
            f"Resize node '{node.name}' requires a Texture input.\n"
            f"Got: {val_input.type.name} (Field)\n"
            f"Solution: Use Rasterize to convert fields to textures first."
        )
    
    # Get target dimensions
    target_width = node.width
    target_height = node.height
    
    # Create output texture at target resolution
    output_name = f"resize_{node.name}"
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format="rgba32f",
        size=(target_width, target_height),
        dimensions=2
    )
    val_output = builder.add_resource(desc)
    
    # Sample input texture with placeholder UV
    # emit_sample generates inline UVs based on dispatch_size
    val_placeholder_uv = builder.constant((0.5, 0.5), DataType.VEC2)
    val_sampled = builder.sample(val_input, val_placeholder_uv)
    
    # Write to output texture
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_gid_xy = builder.swizzle(val_gid, "xy")
    val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
    builder.image_store(val_output, val_coord, val_sampled)
    
    # Store output in socket map
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output
    
    return val_output
