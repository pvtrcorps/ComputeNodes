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
    builder = ctx.builder
    
    img = node.image
    if not img:
        val = builder.constant(0.0, DataType.FLOAT)
    else:
        fmt = "rgba32f" if img.is_float else "rgba8"
        desc = ImageDesc(name=img.name, access=ResourceAccess.READ, format=fmt)
        val = builder.add_resource(desc)
    
    ctx.set_output(0, val)
    return val



def handle_image_info(node, ctx):
    """Handle ComputeNodeImageInfo node - returns separate width, height, depth, and dimensionality."""
    builder = ctx.builder
    
    # Get input data using validation
    val_img = ctx.require_input(0, expected_type=DataType.HANDLE)
    
    # Calculate size and dims from val_img...
    # (Existing logic continues below, we just replaced the fetching/validation part)
    
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
    ctx.set_output(0, val_width)
    ctx.set_output(1, val_height)
    ctx.set_output(2, val_depth)
    ctx.set_output(3, val_dims)
    
    return val_width


def handle_sample(node, ctx):
    """
    Handle ComputeNodeSample node - texture sampling with bilinear filtering.
    """
    builder = ctx.builder
    
    val_img = ctx.get_input(0)  # Texture
    val_coord = ctx.get_input(1)  # Coordinate
    
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
    
    ctx.set_output(0, val_out)
    return val_out
