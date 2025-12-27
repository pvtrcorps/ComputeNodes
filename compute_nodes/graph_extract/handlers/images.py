# Image Node Handlers
# Handles: ComputeNodeImageInput, ComputeNodeImageWrite, ComputeNodeImageInfo, ComputeNodeSample

import logging

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType

logger = logging.getLogger(__name__)


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
    """Handle ComputeNodeImageInfo node - returns separate width, height, depth, and dimensionality."""
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_img = get_socket_value(node.inputs[0])
    
    if not val_img:
        # No input: return zeros
        val_width = builder.constant(0, DataType.INT)
        val_height = builder.constant(0, DataType.INT)
        val_depth = builder.constant(1, DataType.INT)  # Default to 1 for depth
        val_dims = builder.constant(2, DataType.INT)   # Default to 2D
    else:
        if val_img.type != DataType.HANDLE:
            raise TypeError(f"Node '{node.name}': Input must be a Grid (got {val_img.type.name})")
        
        # Get image size as IVEC3 (handles both 2D and 3D)
        val_size = builder.image_size(val_img)
        
        # Extract individual components
        val_width = builder.swizzle(val_size, "x")
        val_height = builder.swizzle(val_size, "y")
        val_depth = builder.swizzle(val_size, "z")
        
        # Determine dimensionality from resource descriptor
        graph = builder.graph
        if val_img.resource_index is not None and val_img.resource_index < len(graph.resources):
            res = graph.resources[val_img.resource_index]
            dimensions = getattr(res, 'dimensions', 2)
            val_dims = builder.constant(dimensions, DataType.INT)
        else:
            # Default to 2D if resource not found
            val_dims = builder.constant(2, DataType.INT)
    
    # Map outputs: Width, Height, Depth, Dimensionality
    socket_value_map[get_socket_key(node.outputs[0])] = val_width
    socket_value_map[get_socket_key(node.outputs[1])] = val_height
    socket_value_map[get_socket_key(node.outputs[2])] = val_depth
    socket_value_map[get_socket_key(node.outputs[3])] = val_dims
    
    return val_width


def handle_sample(node, ctx):
    """
    Handle ComputeNodeSample node - texture sampling with bilinear filtering.
    
    Generates IR for sampling from 2D or 3D textures using normalized UV coords (0-1).
    
    Dimension Handling:
        - Detects target texture dimensionality from the resource descriptor
        - VEC3 coords preserved when sampling from 3D textures
        - VEC3 coords flattened to XY when sampling from 2D textures
        - VEC2 coords extended with Z=0.5 when sampling from 3D textures
    
    Args:
        node: The ComputeNodeSample Blender node
        ctx: Handler context with builder, socket_value_map, etc.
    
    Returns:
        Value representing the sampled RGBA result (VEC4)
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    val_img = get_socket_value(node.inputs[0])  # Texture
    val_coord = get_socket_value(node.inputs[1])  # Coordinate
    
    if val_img is None:
        val_out = builder.constant((0.0, 0.0, 0.0, 0.0), DataType.VEC4)
    else:
        # Detect if target texture is 3D from resource descriptor
        target_is_3d = False
        if val_img.resource_index is not None:
            graph = builder.graph
            if val_img.resource_index < len(graph.resources):
                res = graph.resources[val_img.resource_index]
                target_is_3d = getattr(res, 'dimensions', 2) == 3
        
        if val_coord is None:
            # Default coords: center of texture
            if target_is_3d:
                val_coord = builder.constant((0.5, 0.5, 0.5), DataType.VEC3)
            else:
                val_coord = builder.constant((0.5, 0.5), DataType.VEC2)
        
        # Validate coordinate type
        if val_coord.type == DataType.HANDLE:
            logger.error(
                f"Sample node '{node.name}': Coordinate input received a Texture (HANDLE), "
                "expected a vector. Check your connections."
            )
            val_coord = builder.constant((0.5, 0.5), DataType.VEC2)
        
        # Adjust coordinate dimensionality based on target texture
        if target_is_3d:
            # For 3D textures, ensure VEC3
            if val_coord.type == DataType.VEC2:
                # Extend 2D coords to 3D with Z=0.5 (middle slice)
                z_val = builder.constant(0.5, DataType.FLOAT)
                val_coord = builder.combine_xyz(
                    builder.swizzle(val_coord, "x"),
                    builder.swizzle(val_coord, "y"),
                    z_val
                )
            elif val_coord.type == DataType.IVEC3:
                val_coord = builder.cast(val_coord, DataType.VEC3)
            elif val_coord.type not in (DataType.VEC3, DataType.VEC4):
                # Cast other types to VEC3
                val_coord = builder.cast(val_coord, DataType.VEC3)
            # VEC3 is preserved as-is
        else:
            # For 2D textures, ensure VEC2
            if val_coord.type == DataType.VEC3:
                # Flatten to 2D by taking XY
                val_coord = builder.swizzle(val_coord, "xy")
            elif val_coord.type == DataType.IVEC2:
                val_coord = builder.cast(val_coord, DataType.VEC2)
            elif val_coord.type != DataType.VEC2:
                val_coord = builder.cast(val_coord, DataType.VEC2)
        
        # Use sample() for texture() - enables bilinear filtering
        val_out = builder.sample(val_img, val_coord)
    
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_out
    return val_out

