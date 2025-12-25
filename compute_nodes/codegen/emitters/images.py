# Image Operation Emitters
# Handles: IMAGE_STORE, IMAGE_LOAD, IMAGE_SIZE, SAMPLE

from ...ir.graph import ValueKind


def emit_image_store(op, ctx):
    """
    Emit imageStore operation.
    
    IMPORTANT: To avoid cross-pass SSA reference issues, we always use
    gl_GlobalInvocationID inline for coordinates rather than referencing
    a potentially undefined SSA variable from another pass.
    
    Grid Architecture:
    - Grid2D: imageStore(img, ivec2, data)
    - Grid3D: imageStore(img, ivec3, data)
    """
    param = ctx['param']
    graph = ctx['graph']
    
    img = param(op.inputs[0])
    
    # Detect if target image is 3D
    res_idx = op.inputs[0].resource_index
    is_3d = False
    if res_idx is not None and res_idx < len(graph.resources):
        res = graph.resources[res_idx]
        is_3d = getattr(res, 'dimensions', 2) == 3
    
    # Use appropriate coordinate type
    if is_3d:
        coord = "ivec3(gl_GlobalInvocationID)"
    else:
        coord = "ivec2(gl_GlobalInvocationID.xy)"
    
    data = param(op.inputs[2])

    # Check if 'data' is a Resource (e.g. Image Input connected to Write)
    data_val = op.inputs[2]
    if data_val.kind == ValueKind.ARGUMENT and data_val.resource_index is not None:
        # It's a resource (img_X). We need to load it.
        res = graph.resources[data_val.resource_index]
        
        # Use texelFetch only for READ-only samplers, imageLoad for images
        if res.access.name == 'READ':
            data = f"texelFetch({data}, {coord}, 0)"
        else:
            # READ_WRITE or WRITE - it's an image, use imageLoad
            data = f"imageLoad({data}, {coord})"

    return f"    imageStore({img}, {coord}, {data});"


def emit_image_load(op, ctx):
    """
    Emit imageLoad operation.
    
    To avoid cross-pass SSA reference issues, if the coord is an SSA value
    we use inline gl_GlobalInvocationID instead.
    
    Grid Architecture:
    - Grid2D: imageLoad(img, ivec2)
    - Grid3D: imageLoad(img, ivec3)
    """
    lhs = ctx['lhs']
    param = ctx['param']
    graph = ctx['graph']
    
    img = param(op.inputs[0])
    
    # Detect if source image is 3D
    res_idx = op.inputs[0].resource_index
    is_3d = False
    if res_idx is not None and res_idx < len(graph.resources):
        res = graph.resources[res_idx]
        is_3d = getattr(res, 'dimensions', 2) == 3
    
    # Check if coord input is SSA (potentially from another pass)
    coord_val = op.inputs[1]
    from ...ir.graph import ValueKind
    if coord_val.kind == ValueKind.SSA:
        # Use inline coords to avoid cross-pass issues
        if is_3d:
            coord = "ivec3(gl_GlobalInvocationID)"
        else:
            coord = "ivec2(gl_GlobalInvocationID.xy)"
    else:
        coord = param(coord_val)
    
    # Check if sampler
    if res_idx is not None:
        res = graph.resources[res_idx]
        if res.access.name == 'READ':
            return f"{lhs}texelFetch({img}, {coord}, 0);"
    
    return f"{lhs}imageLoad({img}, {coord});"


def emit_image_size(op, ctx):
    """Emit imageSize operation."""
    lhs = ctx['lhs']
    param = ctx['param']
    graph = ctx['graph']
    
    img = param(op.inputs[0])
    
    # Check if sampler
    res_idx = op.inputs[0].resource_index
    if res_idx is not None:
        res = graph.resources[res_idx]
        if res.access.name == 'READ':
            return f"{lhs}textureSize({img}, 0);"
    
    return f"{lhs}imageSize({img});"


def emit_sample(op, ctx):
    """
    Emit texture sampling operation.
    
    GLSL: texture(sampler, uv) for filtered sampling
    Inputs: [sampler_resource, uv_coord]
    
    Grid Architecture:
    - For Grid2D: texture(sampler2D, vec2)
    - For Grid3D: texture(sampler3D, vec3)
    - Auto-projection: If Grid is 3D but coords are 2D, project to vec3(uv, 0.0)
    
    UV Handling:
    - Check if UV is valid in current pass (its defining op is in current pass)
    - If UV would be undefined (cross-pass reference), use inline normalized UVs
    - Otherwise use actual UV value
    """
    lhs = ctx['lhs']
    dispatch_size = ctx.get('dispatch_size', (512, 512, 1))
    param = ctx['param']
    current_op_ids = ctx.get('op_ids', set())  # Set of op IDs in current pass
    graph = ctx.get('graph')
    
    sampler = param(op.inputs[0])
    uv_input = op.inputs[1]
    
    # Determine if texture is 3D from resource
    is_3d = False
    res_idx = op.inputs[0].resource_index
    if res_idx is not None and graph:
        res = graph.resources[res_idx]
        is_3d = getattr(res, 'dimensions', 2) == 3
    
    # Determine if UV is usable in current pass
    from ...ir.graph import ValueKind
    from ...ir.types import DataType
    
    # SSA values: check if their origin op is in current pass
    if uv_input.kind == ValueKind.SSA and uv_input.origin is not None:
        uv_op_id = id(uv_input.origin)
        uv_available = uv_op_id in current_op_ids
    elif uv_input.kind == ValueKind.CONSTANT:
        # Constants might be placeholder (0.5, 0.5) or could be emitted in any pass
        if hasattr(uv_input, 'origin') and uv_input.origin is not None:
            val = getattr(uv_input.origin, 'attrs', {}).get('value')
            uv_available = val != (0.5, 0.5)  # Not a placeholder
        else:
            uv_available = False  # Assume placeholder
    elif uv_input.kind == ValueKind.BUILTIN:
        # Builtins are always available
        uv_available = True
    else:
        uv_available = False
    
    if uv_available:
        # Use actual UV coords
        uv = param(uv_input)
        uv_type = uv_input.type
    else:
        # Use inline normalized UVs (for cross-pass or placeholder cases)
        w, h, d = dispatch_size[0], dispatch_size[1], dispatch_size[2]
        if is_3d:
            # 3D: use all three dimensions
            uv = f"((vec3(gl_GlobalInvocationID.xyz) + vec3(0.5)) / vec3({float(w)}, {float(h)}, {float(d)}))"
            uv_type = DataType.VEC3
        else:
            uv = f"((vec2(gl_GlobalInvocationID.xy) + vec2(0.5)) / vec2({float(w)}, {float(h)}))"
            uv_type = DataType.VEC2
    
    # Auto-projection: If texture is 3D but UV is 2D, project to vec3(uv, 0.0)
    if is_3d:
        if uv_available and uv_type == DataType.VEC2:
            # Project 2D coords to 3D at Z=0
            uv = f"vec3({uv}, 0.0)"
        elif not uv_available and uv_type != DataType.VEC3:
            # Inline UV already generated as vec3 above
            pass
    
    return f"{lhs}texture({sampler}, {uv});"
