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
    This is the fundamental operation that converts lazy procedural data
    into concrete data that can be sampled at arbitrary coordinates.
    
    Grid Architecture:
    - Grid2D: width x height (dim_mode == '2D')
    - Grid3D: width x height x depth (dim_mode == '3D')
    
    Resolution can be:
    - Static: Socket default values or constant connections
    - Dynamic: Non-constant connected values (e.g., from GridInfo, loop iteration)
    """
    builder = ctx['builder']
    get_socket_value = ctx['get_socket_value']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get input value (Field)
    val_input = get_socket_value(node.inputs['Field'])
    
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
        - value: integer to use for static allocation
        - is_dynamic: True if value is computed at runtime
        - expression: Value object for runtime evaluation (or None)
        """
        if socket_name not in node.inputs:
            return default, False, None
        
        socket = node.inputs[socket_name]
        if not socket.is_linked:
            return int(socket.default_value), False, None
        
        # Socket is connected - get the Value
        val = get_socket_value(socket)
        if val is None:
            return int(socket.default_value), False, None
        
        # Check if it's a constant
        if val.origin and hasattr(val.origin, 'attrs') and 'value' in val.origin.attrs:
            # It's a CONSTANT op - extract static value
            return int(val.origin.attrs['value']), False, None
        
        # It's a dynamic value (not constant) - mark as dynamic
        # Use socket default as fallback size, but store expression for runtime
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
        format="rgba32f",
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
        # This allows chaining: Grid -> Capture (resize equivalent)
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
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output
    
    return val_output


