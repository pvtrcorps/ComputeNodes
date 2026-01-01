# Output Image Handler - Grid Architecture
# Handles: ComputeNodeOutputImage
#
# IMPORTANT: Output Image expects GRID input only.
# Fields must go through Capture first.

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType
from ...ir.graph import _trace_resource_index


def handle_output_image(node, ctx):
    """
    Handle ComputeNodeOutputImage node.
    
    Grid Architecture:
    - Input MUST be a GRID (HANDLE type)
    - Resolution is INHERITED from the input grid
    
    Save Modes:
    - DATABLOCK: Keep in Blender memory
    - SAVE: Write to file after execution
    - PACK: Pack into .blend file
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
    save_mode = getattr(node, 'save_mode', 'DATABLOCK')
    filepath = getattr(node, 'filepath', '')
    file_format = getattr(node, 'file_format', 'OPEN_EXR')
    
    # Get input data
    data_socket = node.inputs[0]  # "Grid" socket
    val_data = get_socket_value(data_socket)
    
    if val_data is None:
        logger.warning(f"Output Image '{node.name}': No grid connected")
        return None
    
    # VALIDATE: Input must be a GRID (HANDLE)
    if val_data.type != DataType.HANDLE:
        raise TypeError(
            f"Output Image '{node.name}' requires a Grid input.\n"
            f"Got: {val_data.type.name} (Field)\n"
            f"Solution: Insert a Capture node before Output Image."
        )
    
    # Find the source resource to get dimensions
    # Trace through PASS_LOOP_END if needed (when Grid comes from a repeat zone)
    source_resource = None
    res_idx = val_data.resource_index
    
    if res_idx is None and val_data.origin is not None:
        # Trace through origin chain to find actual resource
        res_idx = _trace_resource_index(val_data)
    
    if res_idx is not None and res_idx < len(builder.graph.resources):
        source_resource = builder.graph.resources[res_idx]
    
    # Get dimensions from source texture
    if source_resource and hasattr(source_resource, 'size'):
        output_width = source_resource.size[0]
        output_height = source_resource.size[1]
    else:
        logger.warning(f"Output '{node.name}': Could not determine input size, using 512x512")
        output_width = 512
        output_height = 512
    
    # Create ImageDesc for the output
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.WRITE,
        format=output_format,
        size=(output_width, output_height),
        dimensions=2,
        is_internal=False
    )
    val_target = builder.add_resource(desc)
    
    # Store save settings for executor to use
    if not hasattr(builder.graph, 'output_image_settings'):
        builder.graph.output_image_settings = {}
    
    builder.graph.output_image_settings[output_name] = {
        'save_mode': save_mode,
        'filepath': filepath,
        'file_format': file_format,
    }
    
    # Sample input texture
    val_placeholder_uv = builder.constant((0.5, 0.5), DataType.VEC2)
    val_sampled = builder.sample(val_data, val_placeholder_uv)
    
    # Write to output
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_gid_xy = builder.swizzle(val_gid, "xy")
    val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
    builder.image_store(val_target, val_coord, val_sampled)
    
    return val_target

