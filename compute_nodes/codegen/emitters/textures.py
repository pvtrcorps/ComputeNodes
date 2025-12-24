# Texture Operation Emitters
# Handles: NOISE, WHITE_NOISE, VORONOI


def emit_noise(op, ctx):
    """Emit noise texture function call."""
    param = ctx['param']
    
    dims = op.attrs.get('dimensions', '3D')
    normalize = "1.0f" if op.attrs.get('normalize', True) else "0.0f"
    
    co = param(op.inputs[0])
    w = param(op.inputs[1])
    scale = param(op.inputs[2])
    detail = param(op.inputs[3])
    rough = param(op.inputs[4])
    lacu = param(op.inputs[5])
    offset = param(op.inputs[6]) 
    
    out_val_id = op.outputs[0].id
    out_col_id = op.outputs[1].id if len(op.outputs) > 1 else -1
    
    func_map = {
        '1D': 'node_noise_tex_fbm_1d',
        '2D': 'node_noise_tex_fbm_2d',
        '3D': 'node_noise_tex_fbm_3d',
        '4D': 'node_noise_tex_fbm_4d',
    }
    func_name = func_map.get(dims, 'node_noise_tex_fbm_3d')
    
    val_var = f"v{out_val_id}"
    col_var = f"v{out_col_id}" if out_col_id >= 0 else f"unused_col_{out_val_id}" 
    
    decl_val = f"    float {val_var};"
    decl_col = f"    vec4 {col_var};"
    
    call_line = f"    {func_name}({co}, {w}, {scale}, {detail}, {rough}, {lacu}, {offset}, {normalize}, {val_var}, {col_var});"
    
    return f"{decl_val}\n{decl_col}\n{call_line}"


def emit_white_noise(op, ctx):
    """Emit white noise function call."""
    param = ctx['param']
    
    dims = op.attrs.get('dimensions', '3D')
    
    co = param(op.inputs[0])
    w = param(op.inputs[1])
    
    out_val_id = op.outputs[0].id
    out_col_id = op.outputs[1].id if len(op.outputs) > 1 else -1
    
    func_map = {
        '1D': 'node_white_noise_1d',
        '2D': 'node_white_noise_2d',
        '3D': 'node_white_noise_3d',
        '4D': 'node_white_noise_4d',
    }
    func_name = func_map.get(dims, 'node_white_noise_3d')
    
    val_var = f"v{out_val_id}"
    col_var = f"v{out_col_id}" if out_col_id >= 0 else f"unused_col_{out_val_id}"
    
    decl_val = f"    float {val_var};"
    decl_col = f"    vec4 {col_var};"
    
    # Args differ by dimension
    if dims == '1D':
        args = f"{w}, {val_var}, {col_var}"
    elif dims == '4D':
        args = f"{co}, {w}, {val_var}, {col_var}"
    else:
        args = f"{co}, {w}, {val_var}, {col_var}"
        
    call_line = f"    {func_name}({args});"
    
    return f"{decl_val}\n{decl_col}\n{call_line}"


def emit_voronoi(op, ctx):
    """Emit voronoi texture function call."""
    param = ctx['param']
    
    dims = op.attrs.get('dimensions', '3D')
    feature = op.attrs.get('feature', 'F1')
    metric = op.attrs.get('metric', 'EUCLIDEAN')
    normalize = "1.0f" if op.attrs.get('normalize', False) else "0.0f"
    
    # Map Metric String to Int Define
    metric_map = {
        'EUCLIDEAN': 'SHD_VORONOI_EUCLIDEAN',
        'MANHATTAN': 'SHD_VORONOI_MANHATTAN',
        'CHEBYCHEV': 'SHD_VORONOI_CHEBYCHEV',
        'MINKOWSKI': 'SHD_VORONOI_MINKOWSKI',
    }
    metric_str = metric_map.get(metric, 'SHD_VORONOI_EUCLIDEAN')
    metric_val = f"float({metric_str})"
    
    co = param(op.inputs[0])
    w = param(op.inputs[1])
    scale = param(op.inputs[2])
    detail = param(op.inputs[3])
    rough = param(op.inputs[4])
    lacu = param(op.inputs[5])
    smooth = param(op.inputs[6])
    exp = param(op.inputs[7])
    rand = param(op.inputs[8])
    
    # Outputs: [Dist, Col, Pos, W, Rad]
    v_dist = f"v{op.outputs[0].id}"
    v_col  = f"v{op.outputs[1].id}"
    v_pos  = f"v{op.outputs[2].id}"
    v_w    = f"v{op.outputs[3].id}"
    v_rad  = f"v{op.outputs[4].id}"
    
    decl = []
    decl.append(f"    float {v_dist};")
    decl.append(f"    vec4 {v_col};")
    decl.append(f"    vec3 {v_pos};")
    decl.append(f"    float {v_w};")
    decl.append(f"    float {v_rad};")
    
    suffix = dims.lower()
    
    # Helper to swizzle input coord for 1D/2D variants
    co_arg = co
    if dims == '1D':
        co_arg = w
    elif dims == '2D':
        co_arg = f"({co}).xy"
    
    feat_lower = feature.lower()
    
    func_name = f"node_tex_voronoi_{feat_lower}_{suffix}"
    
    call_args = [
        co_arg, w, scale, detail, rough, lacu, smooth, exp, rand, metric_val, normalize,
        v_dist, v_col, v_pos, v_w, v_rad
    ]
    
    call_line = f"    {func_name}({', '.join(call_args)});"
    
    return "\n".join(decl + [call_line])
