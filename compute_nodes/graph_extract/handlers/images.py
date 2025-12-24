# Image Node Handlers
# Handles: ComputeNodeImageInput, ComputeNodeImageWrite, ComputeNodeImageInfo, ComputeNodeSample

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_image_input(node, ctx):
    """Handle ComputeNodeImageInput node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    img = node.image
    if not img:
        val = builder.constant(0.0, DataType.FLOAT)
    else:
        fmt = "rgba32f" if img.is_float else "rgba8"
        desc = ImageDesc(name=img.name, access=ResourceAccess.READ, format=fmt)
        val = builder.add_resource(desc)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val
    return val


def handle_image_write(node, ctx):
    """Handle ComputeNodeImageWrite node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    img = node.image
    if not img:
        val = builder.constant(0.0, DataType.FLOAT)
    else:
        fmt = "rgba32f" if img.is_float else "rgba8"
        desc = ImageDesc(name=img.name, access=ResourceAccess.WRITE, format=fmt)
        val = builder.add_resource(desc)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val
    return val


def handle_image_info(node, ctx):
    """Handle ComputeNodeImageInfo node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_img = get_socket_value(node.inputs[0])
    if not val_img:
        val_size = builder.constant((0, 0), DataType.IVEC2)
    else:
        if val_img.type != DataType.HANDLE:
            raise TypeError(f"Node '{node.name}': Input must be an Image (got {val_img.type.name})")
        val_size = builder.image_size(val_img)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_size
    return val_size


def handle_sample(node, ctx):
    """Handle ComputeNodeSample node."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_img = get_socket_value(node.inputs[0])
    val_coord = get_socket_value(node.inputs[1])
    
    if val_img is None:
        val_out = builder.constant((0.0, 0.0, 0.0, 0.0), DataType.VEC4)
    else:
        if val_coord is None:
            val_coord = builder.constant((0, 0), DataType.IVEC2)
        
        if val_coord.type != DataType.IVEC2:
            val_coord = builder.cast(val_coord, DataType.IVEC2)
        
        val_out = builder.image_load(val_img, val_coord)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_out
    return val_out
