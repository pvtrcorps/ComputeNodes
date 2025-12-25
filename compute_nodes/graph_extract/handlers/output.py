# Output Node Handler
# Handles: ComputeNodeOutput

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_output(node, ctx):
    """
    Handle ComputeNodeOutput node.
    
    Creates an ImageDesc for the output and generates IMAGE_STORE operation.
    This handler extracts the output logic from core.py into a modular handler.
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Get properties from node
    output_name = node.output_name
    output_width = node.width
    output_height = node.height
    output_format = node.format
    
    # Create ImageDesc for the output
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.WRITE,
        format=output_format,
        size=(output_width, output_height),
        dimensions=2  # Output is always 2D for now
    )
    val_target = builder.add_resource(desc)
    
    # Data socket is inputs[0] (Color)
    data_socket = node.inputs[0]
    
    # Get data to write
    val_data = get_socket_value(data_socket)
    if val_data is None:
        import logging
        logging.getLogger(__name__).warning(f"Output node {node.name} has no data to write")
        return None
        
    # Ensure VEC4 for RGBA formats
    if val_data.type == DataType.VEC3:
        val_data = builder.cast(val_data, DataType.VEC4)
    if val_data.type == DataType.IVEC2:
        val_data = builder.cast(val_data, DataType.VEC4)
    if val_data.type == DataType.FLOAT:
        val_data = builder.cast(val_data, DataType.VEC4)
    
    # Coord construction
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_coord_uvec = builder.swizzle(val_gid, "xy")
    val_coord_ivec = builder.cast(val_coord_uvec, DataType.IVEC2)
    
    # Image Store
    builder.image_store(val_target, val_coord_ivec, val_data)
    
    # Store in socket map for potential chaining
    out_key = get_socket_key(node.outputs[0]) if node.outputs else None
    if out_key:
        socket_value_map[out_key] = val_target
    
    return val_target
