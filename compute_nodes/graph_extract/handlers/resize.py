# Resize Handler - Grid Architecture
# Handles: ComputeNodeResize
# Texture → Texture operation (uses bilinear/trilinear sampling)

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_resize(node, ctx):
    """
    Handle ComputeNodeResize node.
    
    Grid Architecture:
    - Input MUST be a GRID (HANDLE type)
    - Output is a new grid at target resolution
    - Supports 2D and 3D grids
    
    Dynamic Resolution:
    - If Width/Height sockets are connected to non-constant values,
      the resource is marked as dynamic_size=True
    - The executor will evaluate size_expression at runtime
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
        logger.warning(f"Resize node '{node.name}': No grid connected")
        return None
    
    # VALIDATE: Input must be a GRID (HANDLE)
    if val_input.type != DataType.HANDLE:
        raise TypeError(
            f"Resize node '{node.name}' requires a Grid input.\n"
            f"Got: {val_input.type.name}"
        )
    
    dims = 3 if node.dimensions == '3D' else 2
    
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
        logger.info(f"Resize '{node.name}': {socket_name} is dynamic (non-constant)")
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
    
    # Create output grid
    output_name = f"resize_{node.name}"
    if dims == 3:
        size = (width_val, height_val, depth_val)
    else:
        size = (width_val, height_val)
    
    desc = ImageDesc(
        name=output_name,
        access=ResourceAccess.READ_WRITE,
        format="RGBA32F",
        size=size,
        dimensions=dims,
        is_internal=True,
        dynamic_size=is_dynamic,
        size_expression=size_expression
    )
    val_output = builder.add_resource(desc)
    
    if is_dynamic:
        logger.info(f"Resize '{node.name}': marked as dynamic_size, expressions: {list(size_expression.keys())}")
    
    # Sample input using placeholder UV (will be replaced by proper UV in shader)
    # Calculate explicit UVs based on target size
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    
    if dims == 3:
        # 3D: Use standard sampling (assuming sampler3D works correctly)
        val_coord_i = builder.cast(val_gid, DataType.IVEC3)
        val_coord_f = builder.cast(val_coord_i, DataType.VEC3)
        val_size = builder.constant((float(width_val), float(height_val), float(depth_val)), DataType.VEC3)
        val_half = builder.constant((0.5, 0.5, 0.5), DataType.VEC3)
        
        val_pos = builder.add(val_coord_f, val_half)
        val_uv = builder.div(val_pos, val_size)
        val_sampled = builder.sample(val_input, val_uv)
        
    else:
        # 2D: Manual Bilinear Interpolation using texelFetch
        # This is robust against sampler types (Rect vs 2D) and avoids Zoom artifacts
        
        # 1. Get Texture Size using IMAGE_SIZE OpCode (maps to textureSize for samplers)
        val_ts = builder.emit(OpCode.IMAGE_SIZE, [val_input], DataType.IVEC2)
        val_ts_f = builder.cast(val_ts, DataType.VEC2)
        
        # 2. UV Calculation (Target Normalization)
        val_gid_xy = builder.swizzle(val_gid, "xy")
        val_target_coord_i = builder.cast(val_gid_xy, DataType.IVEC2)
        val_target_coord_f = builder.cast(val_target_coord_i, DataType.VEC2)
        val_target_size = builder.constant((float(width_val), float(height_val)), DataType.VEC2)
        val_half = builder.constant((0.5, 0.5), DataType.VEC2)
        
        # uv = (target_coord + 0.5) / target_size
        val_pos = builder.add(val_target_coord_f, val_half)
        val_uv = builder.div(val_pos, val_target_size)
        
        # 3. Map UV to Input Coords
        # coord = uv * input_size - 0.5
        val_coord_unnorm = builder.mul(val_uv, val_ts_f)
        val_coord_center = builder.binary(OpCode.SUB, val_coord_unnorm, val_half)
        
        # 4. Floor and Fract using builder.emit
        val_coord_floor = builder.emit(OpCode.FLOOR, [val_coord_center], DataType.VEC2)
        val_uv_f = builder.emit(OpCode.FRACT, [val_coord_center], DataType.VEC2)
        
        val_coord_i = builder.cast(val_coord_floor, DataType.IVEC2)
        
        # 5. Clamp and Fetch 4 Neighbors
        val_one_i = builder.constant((1, 1), DataType.IVEC2)
        val_idx_br = builder.add(val_coord_i, builder.constant((1, 0), DataType.IVEC2))
        val_idx_tl = builder.add(val_coord_i, builder.constant((0, 1), DataType.IVEC2))
        val_idx_tr = builder.add(val_coord_i, val_one_i)
        
        # Helper to fetch clamped
        val_sub_one = builder.binary(OpCode.SUB, val_ts, val_one_i)
        val_zero = builder.constant((0, 0), DataType.IVEC2)
        
        def emit_clamped_fetch(coord_val):
            # clamp(coord, 0, size-1)
            val_clamped = builder.emit(OpCode.CLAMP, [coord_val, val_zero, val_sub_one], DataType.IVEC2)
            
            # Fetch using IMAGE_LOAD (maps to texelFetch for valid samplers)
            return builder.image_load(val_input, val_clamped)

        val_tex_bl = emit_clamped_fetch(val_coord_i)
        val_tex_br = emit_clamped_fetch(val_idx_br)
        val_tex_tl = emit_clamped_fetch(val_idx_tl)
        val_tex_tr = emit_clamped_fetch(val_idx_tr)
        
        # 6. Bilinear Mix using MIX OpCode
        # mix(mix(bl, br, f.x), mix(tl, tr, f.x), f.y)
        val_fx = builder.swizzle(val_uv_f, "x")
        val_fy = builder.swizzle(val_uv_f, "y")
        
        val_mix_b = builder.emit(OpCode.MIX, [val_tex_bl, val_tex_br, val_fx], DataType.VEC4)
        val_mix_t = builder.emit(OpCode.MIX, [val_tex_tl, val_tex_tr, val_fx], DataType.VEC4)
        val_sampled = builder.emit(OpCode.MIX, [val_mix_b, val_mix_t, val_fy], DataType.VEC4)
    
    # Write to output (Common)
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    
    # Write to output
    val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    if dims == 3:
        val_coord = builder.cast(val_gid, DataType.IVEC3)
        builder.image_store(val_output, val_coord, val_sampled)
    else:
        val_gid_xy = builder.swizzle(val_gid, "xy")
        val_coord = builder.cast(val_gid_xy, DataType.IVEC2)
        builder.image_store(val_output, val_coord, val_sampled)
    
    # Store output in socket map
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_output
    
    return val_output

