# Output Image Handler - Grid Architecture
# Handles: ComputeNodeOutputImage
#
# IMPORTANT: Output Image expects GRID input only.
# Fields must go through Capture first.

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType
from ...ir.graph import _trace_resource_index

import logging
logger = logging.getLogger(__name__)


def _is_loop_resource(res):
    """Check if resource comes from a loop output (size changes at runtime)."""
    if res is None:
        return False
    name = getattr(res, 'name', '')
    # Loop ping-pong buffers have these patterns
    if 'loop_' in name or '_ping' in name or '_pong' in name:
        return True
    # Resources marked as dynamic
    if getattr(res, 'dynamic_size', False):
        return True
    return False


def handle_output_image(node, ctx):
    """
    Handle ComputeNodeOutputImage node.
    Grid Architecture:
    - Input MUST be a GRID (HANDLE type)
    - Resolution is INHERITED from the input grid
    - If input is a loop output, size is evaluated at runtime
    """
    builder = ctx.builder
    
    # Get properties from node
    output_name = node.output_name
    output_format = node.format
    save_mode = getattr(node, 'save_mode', 'DATABLOCK')
    filepath = getattr(node, 'filepath', '')
    file_format = getattr(node, 'file_format', 'OPEN_EXR')
    
    # Get input data using validation
    val_data = ctx.require_input(0, expected_type=DataType.HANDLE)
    
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
    is_dynamic = False
    output_width = 512
    output_height = 512
    
    if source_resource and hasattr(source_resource, 'size'):
        # Check if source is a loop resource (size will change at runtime)
        if _is_loop_resource(source_resource):
            # Mark as dynamic - size will be inherited from loop output at runtime
            is_dynamic = True
            logger.info(f"Output '{node.name}': Input from loop resource - marking dynamic")
            # Use initial size for placeholder, runtime will update
            output_width = source_resource.size[0] if source_resource.size[0] > 0 else 512
            output_height = source_resource.size[1] if len(source_resource.size) > 1 and source_resource.size[1] > 0 else 512
        else:
            output_width = source_resource.size[0]
            output_height = source_resource.size[1]
    else:
        logger.warning(f"Output '{node.name}': Could not determine input size, using 512x512")
    
    # Create ImageDesc for the output
    # If dynamic, runtime will resize based on actual loop output size
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.WRITE,
        format=output_format,
        size=(output_width, output_height),
        dimensions=2,
        is_internal=False,
        dynamic_size=is_dynamic,
        size_expression={'source_resource': res_idx} if is_dynamic else {}
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
