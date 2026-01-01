# Capture Handler
# Handles: ComputeNodeCapture
# Materializes a Field to a Grid at specified resolution

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_capture(node, ctx):
    """
    Handle ComputeNodeCapture node.
    Captures (materializes) a Field to a Grid at the specified resolution.
    """
    builder = ctx.builder
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get input value (Field)
    # Using 'Field' key from inputs
    val_input = ctx.get_input('Field')
    
    if val_input is None:
        # Default to black if nothing connected
        val_input = builder.constant((0.0, 0.0, 0.0, 1.0), DataType.VEC4)
    
    # Determine dimensions from node property
    is_3d = getattr(node, 'dim_mode', '2D') == '3D'
    dims = 3 if is_3d else 2
    
    def get_size_info(socket_name, default):
        """
        Get size information from socket.
        Returns (value, is_dynamic, expression)
        """
        if socket_name not in node.inputs:
            return default, False, None
        
        socket = node.inputs[socket_name]
        
        # Using ctx to get linked value
        val = ctx.get_input(socket_name)
        
        if val is None:
            # Not linked or no value, use default
            return int(socket.default_value), False, None
        
        # Check if it's a constant
        if val.origin and hasattr(val.origin, 'attrs') and 'value' in val.origin.attrs:
            # It's a CONSTANT op - extract static value
            return int(val.origin.attrs['value']), False, None
        
        # Check if it comes from IMAGE_SIZE
        if val.origin and val.origin.opcode == OpCode.IMAGE_SIZE:
            img_input = val.origin.inputs[0] if val.origin.inputs else None
            if img_input and img_input.resource_index is not None:
                graph = builder.graph
                if img_input.resource_index < len(graph.resources):
                    res = graph.resources[img_input.resource_index]
                    if hasattr(res, 'size') and res.size:
                        if socket_name == 'Width' and len(res.size) > 0:
                            return res.size[0], False, None
                        elif socket_name == 'Height' and len(res.size) > 1:
                            return res.size[1], False, None
        
        # Check if val is from SWIZZLE of IMAGE_SIZE (Grid Info connected)
        if val.origin and val.origin.opcode == OpCode.SWIZZLE:
            swizzle_input = val.origin.inputs[0] if val.origin.inputs else None
            if swizzle_input and swizzle_input.origin and swizzle_input.origin.opcode == OpCode.IMAGE_SIZE:
                img_size_op = swizzle_input.origin
                img_input = img_size_op.inputs[0] if img_size_op.inputs else None
                if img_input and img_input.resource_index is not None:
                    graph = builder.graph
                    if img_input.resource_index < len(graph.resources):
                        res = graph.resources[img_input.resource_index]
                        if hasattr(res, 'size') and res.size:
                            mask = val.origin.attrs.get('mask', 'x')
                            idx = {'x': 0, 'y': 1, 'z': 2}.get(mask, 0)
                            if idx < len(res.size):
                                logger.info(f"Capture '{node.name}': Extracted {socket_name}={res.size[idx]} from Grid Info")
                                return res.size[idx], False, None
        
        # It's a dynamic value
        logger.info(f"Capture '{node.name}': {socket_name} is dynamic (non-constant)")
        return int(socket.default_value), True, val
    
    # Get size info for each dimension
    width_val, width_dynamic, width_expr = get_size_info('Width', 512)
    height_val, height_dynamic, height_expr = get_size_info('Height', 512)
    depth_val, depth_dynamic, depth_expr = get_size_info('Depth', 64) if dims == 3 else (1, False, None)
    
    # Determine if any dimension is dynamic
    is_dynamic = width_dynamic or height_dynamic or (dims == 3 and depth_dynamic)
    
    # Build size expression dict for runtime evaluation
    size_expression = {}
    if width_dynamic:
        size_expression['width'] = width_expr
    if height_dynamic:
        size_expression['height'] = height_expr
    if dims == 3 and depth_dynamic:
        size_expression['depth'] = depth_expr
    
    # Create size tuple based on dimensions
    if is_3d:
        size = (width_val, height_val, depth_val)
    else:
        size = (width_val, height_val)
    
    # Create output Grid (ImageDesc)
    output_name = f"grid_{node.name}"
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format="RGBA32F",
        size=size,
        dimensions=dims,
        dynamic_size=is_dynamic,
        size_expression=size_expression if is_dynamic else {}
    )
    val_output = builder.add_resource(desc)
    
    if is_dynamic:
        logger.info(f"Capture '{node.name}': marked as dynamic_size, expressions: {list(size_expression.keys())}")
    
    # Ensure input is VEC4 for storage
    if val_input.type == DataType.VEC3:
        val_input = builder.cast(val_input, DataType.VEC4)
    elif val_input.type == DataType.FLOAT:
        val_input = builder.cast(val_input, DataType.VEC4)
    elif val_input.type == DataType.HANDLE:
        # Input is already a Grid - sample it at current position
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        if is_3d:
            val_coord_ivec = builder.cast(val_gid, DataType.IVEC3)
        else:
            val_coord = builder.swizzle(val_gid, "xy")
            val_coord_ivec = builder.cast(val_coord, DataType.IVEC2)
        val_input = builder.image_load(val_input, val_coord_ivec)
    
    # Compute output coordinates based on dimensions
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    if is_3d:
        val_coord_ivec = builder.cast(val_gid, DataType.IVEC3)
    else:
        val_coord = builder.swizzle(val_gid, "xy")
        val_coord_ivec = builder.cast(val_coord, DataType.IVEC2)
    
    # Write to Grid
    builder.image_store(val_output, val_coord_ivec, val_input)
    
    # Store output in socket map
    ctx.set_output(0, val_output)
    
    return val_output


