# Converter Operation Emitters
# Handles: SEPARATE_XYZ, COMBINE_XYZ, SEPARATE_COLOR, COMBINE_COLOR


def emit_separate_xyz(op, ctx):
    """Emit separate XYZ operation - extracts x, y, z from vec3.
    
    This operation has 3 outputs (x, y, z), so we emit multiple assignments.
    """
    param = ctx.param
    type_str = ctx.type_str
    
    vec = param(op.inputs[0])
    
    # Get the 3 output values
    out_x = op.outputs[0]
    out_y = op.outputs[1]
    out_z = op.outputs[2]
    
    lines = []
    lines.append(f"    {type_str(out_x.type)} v{out_x.id} = {vec}.x;")
    lines.append(f"    {type_str(out_y.type)} v{out_y.id} = {vec}.y;")
    lines.append(f"    {type_str(out_z.type)} v{out_z.id} = {vec}.z;")
    
    return "\n".join(lines)


def emit_combine_xyz(op, ctx):
    """Emit combine XYZ operation - constructs vec3 from x, y, z."""
    lhs = ctx.lhs
    param = ctx.param
    
    x = param(op.inputs[0])
    y = param(op.inputs[1])
    z = param(op.inputs[2])
    
    return f"{lhs}vec3({x}, {y}, {z});"


def emit_combine_xy(op, ctx):
    """Emit combine XY operation - constructs vec2 from x, y."""
    lhs = ctx.lhs
    param = ctx.param
    
    x = param(op.inputs[0])
    y = param(op.inputs[1])
    
    return f"{lhs}vec2({x}, {y});"


def emit_separate_color(op, ctx):
    """Emit separate color operation - extracts components based on mode.
    
    Modes:
    - RGB: Direct extraction (r, g, b, a)
    - HSV: Convert to HSV then extract (h, s, v, a)
    - HSL: Convert to HSL then extract (h, s, l, a)
    """
    param = ctx.param
    type_str = ctx.type_str
    
    color = param(op.inputs[0])
    mode = op.attrs.get('mode', 'RGB')
    
    # Get the 4 output values
    out_0 = op.outputs[0]
    out_1 = op.outputs[1]
    out_2 = op.outputs[2]
    out_a = op.outputs[3]
    
    lines = []
    
    if mode == 'RGB':
        # Direct extraction
        lines.append(f"    {type_str(out_0.type)} v{out_0.id} = {color}.r;")
        lines.append(f"    {type_str(out_1.type)} v{out_1.id} = {color}.g;")
        lines.append(f"    {type_str(out_2.type)} v{out_2.id} = {color}.b;")
    elif mode == 'HSV':
        # Convert to HSV first
        lines.append(f"    vec3 _hsv_{out_0.id} = rgb_to_hsv({color}.rgb);")
        lines.append(f"    {type_str(out_0.type)} v{out_0.id} = _hsv_{out_0.id}.x;")
        lines.append(f"    {type_str(out_1.type)} v{out_1.id} = _hsv_{out_0.id}.y;")
        lines.append(f"    {type_str(out_2.type)} v{out_2.id} = _hsv_{out_0.id}.z;")
    elif mode == 'HSL':
        # Convert to HSL first
        lines.append(f"    vec3 _hsl_{out_0.id} = rgb_to_hsl({color}.rgb);")
        lines.append(f"    {type_str(out_0.type)} v{out_0.id} = _hsl_{out_0.id}.x;")
        lines.append(f"    {type_str(out_1.type)} v{out_1.id} = _hsl_{out_0.id}.y;")
        lines.append(f"    {type_str(out_2.type)} v{out_2.id} = _hsl_{out_0.id}.z;")
    else:
        # Fallback to RGB
        lines.append(f"    {type_str(out_0.type)} v{out_0.id} = {color}.r;")
        lines.append(f"    {type_str(out_1.type)} v{out_1.id} = {color}.g;")
        lines.append(f"    {type_str(out_2.type)} v{out_2.id} = {color}.b;")
    
    # Alpha is always direct
    lines.append(f"    {type_str(out_a.type)} v{out_a.id} = {color}.a;")
    
    return "\n".join(lines)


def emit_combine_color(op, ctx):
    """Emit combine color operation - constructs vec4 from components based on mode.
    
    Modes:
    - RGB: Direct construction
    - HSV: Construct HSV then convert to RGB
    - HSL: Construct HSL then convert to RGB
    """
    lhs = ctx.lhs
    param = ctx.param
    
    c0 = param(op.inputs[0])  # R/H
    c1 = param(op.inputs[1])  # G/S
    c2 = param(op.inputs[2])  # B/V/L
    alpha = param(op.inputs[3])  # Alpha
    
    mode = op.attrs.get('mode', 'RGB')
    
    if mode == 'RGB':
        return f"{lhs}vec4({c0}, {c1}, {c2}, {alpha});"
    elif mode == 'HSV':
        return f"{lhs}vec4(hsv_to_rgb(vec3({c0}, {c1}, {c2})), {alpha});"
    elif mode == 'HSL':
        return f"{lhs}vec4(hsl_to_rgb(vec3({c0}, {c1}, {c2})), {alpha});"
    else:
        # Fallback to RGB
        return f"{lhs}vec4({c0}, {c1}, {c2}, {alpha});"


def emit_map_range(op, ctx):
    """Emit map range operation with various interpolation modes."""
    lhs = ctx.lhs
    param = ctx.param
    
    value = param(op.inputs[0])
    from_min = param(op.inputs[1])
    from_max = param(op.inputs[2])
    to_min = param(op.inputs[3])
    to_max = param(op.inputs[4])
    steps = param(op.inputs[5])
    
    interpolation_type = op.attrs.get('interpolation_type', 'LINEAR')
    do_clamp = op.attrs.get('clamp', False)
    data_type = op.attrs.get('data_type', 'FLOAT')
    
    is_vector = data_type == 'FLOAT_VECTOR'
    
    if is_vector:
        # Vector mode - use vec3 version for LINEAR, component-wise for others
        if interpolation_type == 'LINEAR':
            result = f"map_range_linear_vec3({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        elif interpolation_type == 'STEPPED':
            # Component-wise stepped
            result = f"vec3(map_range_stepped({value}.x, {from_min}.x, {from_max}.x, {to_min}.x, {to_max}.x, {steps}), map_range_stepped({value}.y, {from_min}.y, {from_max}.y, {to_min}.y, {to_max}.y, {steps}), map_range_stepped({value}.z, {from_min}.z, {from_max}.z, {to_min}.z, {to_max}.z, {steps}))"
        elif interpolation_type == 'SMOOTHSTEP':
            result = f"vec3(map_range_smoothstep({value}.x, {from_min}.x, {from_max}.x, {to_min}.x, {to_max}.x), map_range_smoothstep({value}.y, {from_min}.y, {from_max}.y, {to_min}.y, {to_max}.y), map_range_smoothstep({value}.z, {from_min}.z, {from_max}.z, {to_min}.z, {to_max}.z))"
        elif interpolation_type == 'SMOOTHERSTEP':
            result = f"vec3(map_range_smootherstep({value}.x, {from_min}.x, {from_max}.x, {to_min}.x, {to_max}.x), map_range_smootherstep({value}.y, {from_min}.y, {from_max}.y, {to_min}.y, {to_max}.y), map_range_smootherstep({value}.z, {from_min}.z, {from_max}.z, {to_min}.z, {to_max}.z))"
        else:
            result = f"map_range_linear_vec3({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        
        if do_clamp:
            result = f"clamp({result}, min({to_min}, {to_max}), max({to_min}, {to_max}))"
    else:
        # Float mode
        if interpolation_type == 'LINEAR':
            result = f"map_range_linear({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        elif interpolation_type == 'STEPPED':
            result = f"map_range_stepped({value}, {from_min}, {from_max}, {to_min}, {to_max}, {steps})"
        elif interpolation_type == 'SMOOTHSTEP':
            result = f"map_range_smoothstep({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        elif interpolation_type == 'SMOOTHERSTEP':
            result = f"map_range_smootherstep({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        else:
            result = f"map_range_linear({value}, {from_min}, {from_max}, {to_min}, {to_max})"
        
        if do_clamp:
            result = f"clamp({result}, min({to_min}, {to_max}), max({to_min}, {to_max}))"
    
    return f"{lhs}{result};"


def emit_clamp_range(op, ctx):
    """Emit clamp operation with MINMAX or RANGE mode."""
    lhs = ctx.lhs
    param = ctx.param
    
    value = param(op.inputs[0])
    min_val = param(op.inputs[1])
    max_val = param(op.inputs[2])
    
    clamp_type = op.attrs.get('clamp_type', 'MINMAX')
    
    if clamp_type == 'MINMAX':
        return f"{lhs}clamp_minmax({value}, {min_val}, {max_val});"
    elif clamp_type == 'RANGE':
        return f"{lhs}clamp_range({value}, {min_val}, {max_val});"
    else:
        return f"{lhs}clamp({value}, {min_val}, {max_val});"
