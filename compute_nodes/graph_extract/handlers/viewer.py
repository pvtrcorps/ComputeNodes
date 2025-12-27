# Viewer Handler - GPU-only visualization
# Handles: ComputeNodeViewer

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType
from ...ir.ops import OpCode


def handle_viewer(node, ctx):
    """
    Handle ComputeNodeViewer node.
    
    GPU-Only Viewer:
    - Creates internal GPU texture (no CPU readback)
    - Stores texture reference for draw handler display
    """
    builder = ctx['builder']
    get_socket_value = ctx['get_socket_value']
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get Grid input
    val_data = None
    if node.inputs[0].is_linked:
        val_data = get_socket_value(node.inputs[0])
    
    if val_data is None:
        logger.warning(f"Viewer '{node.name}': No input connected")
        return None
    
    # Create internal texture (GPU-only, no readback)
    output_name = node.get_preview_name()
    
    # Get source dimensions
    source_resource = None
    if val_data.resource_index is not None:
        source_resource = builder.graph.resources[val_data.resource_index]
    
    if source_resource:
        size = source_resource.size
        dims = getattr(source_resource, 'dimensions', 2)
    else:
        size = (256, 256)
        dims = 2
    
    # For 3D, take 2D slice
    output_size = (size[0], size[1]) if dims >= 2 else (256, 256)
    
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format='RGBA32F',
        size=output_size,
        dimensions=2,
        is_internal=True  # GPU-only, no readback!
    )
    val_output = builder.add_resource(desc)
    
    # Sample input and write
    if val_data.type == DataType.HANDLE:
        # Grid: sample it
        uv_placeholder = builder.constant((0.5, 0.5), DataType.VEC2)
        val_sampled = builder.sample(val_data, uv_placeholder)
    else:
        # Field: use directly
        val_sampled = val_data
        # Convert to vec4 if needed
        if val_data.type == DataType.FLOAT:
            val_sampled = builder.emit(OpCode.SWIZZLE, [val_data], DataType.VEC4)
        elif val_data.type == DataType.VEC3:
            val_one = builder.constant(1.0, DataType.FLOAT)
            val_sampled = builder.emit(OpCode.COMBINE_XYZ, [val_data, val_one], DataType.VEC4)
    
    # Store to grid
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_gid_xy = builder.swizzle(val_gid, "xy")
    val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
    builder.image_store(val_output, val_coord, val_sampled)
    
    # Mark for viewer system
    if not hasattr(builder.graph, 'viewer_outputs'):
        builder.graph.viewer_outputs = {}
    
    builder.graph.viewer_outputs[output_name] = {
        'node': node,
        'resource_index': val_output.resource_index,
        'channel': node.channel,
        'exposure': node.exposure,
    }
    
    # Update node's internal reference
    node.preview_image_name = output_name
    
    return None
