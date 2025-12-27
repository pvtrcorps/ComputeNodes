# Image Operation Emitters
# Handles: IMAGE_STORE, IMAGE_LOAD, IMAGE_SIZE, SAMPLE

from ...ir.graph import ValueKind
from ...ir.types import DataType


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
    # Check if coord input is SSA (potentially from another pass)
    coord_val = op.inputs[1]
    
    # Determine if we should force inline global coords
    force_inline = False
    if coord_val.kind == ValueKind.SSA:
        # Check if origin is in current pass (Local SSA)
        current_op_ids = ctx.get('op_ids', set())
        if coord_val.origin and id(coord_val.origin) in current_op_ids:
            # Local variable, safe to use directly
            force_inline = False
        else:
            # Cross-pass reference, force inline to avoid undefined references
            force_inline = True

    if force_inline:
        # Use inline coords to avoid cross-pass issues
        if is_3d:
            coord = "ivec3(gl_GlobalInvocationID)"
        else:
            coord = "ivec2(gl_GlobalInvocationID.xy)"
    else:
        coord = param(coord_val)
    
    # Check if sampler or image
    # If the resource is NOT written in this pass, it is bound as a sampler (READ_ONLY).
    # If it IS written, it is bound as an image (READ_WRITE/WRITE_ONLY).
    writes_idx = ctx.get('writes_idx', set())
    
    if res_idx is not None:
        # Determine if it's bound as image (writable) or sampler (read-only)
        is_image_binding = res_idx in writes_idx
        
        if not is_image_binding:
            # It's a sampler, use texelFetch
            return f"{lhs}texelFetch({img}, {coord}, 0);"
    
    # It's an image, use imageLoad
    return f"{lhs}imageLoad({img}, {coord});"


def emit_image_size(op, ctx):
    """Emit imageSize operation - returns ivec3 for both 2D and 3D grids."""
    lhs = ctx['lhs']
    param = ctx['param']
    graph = ctx['graph']
    
    img = param(op.inputs[0])
    
    # Detect resource dimensionality
    res_idx = op.inputs[0].resource_index
    is_3d = False
    if res_idx is not None and res_idx < len(graph.resources):
        res = graph.resources[res_idx]
        is_3d = getattr(res, 'dimensions', 2) == 3
    
    # Check if sampler or image binding
    writes_idx = ctx.get('writes_idx', set())
    
    if res_idx is not None:
        # If not written, it's a sampler
        if res_idx not in writes_idx:
            if is_3d:
                return f"{lhs}ivec3(textureSize({img}, 0));"
            else:
                # 2D sampler: extend to ivec3 with depth=1
                return f"{lhs}ivec3(textureSize({img}, 0), 1);"
    
    # Image binding
    if is_3d:
        return f"{lhs}ivec3(imageSize({img}));"
    else:
        # 2D image: extend to ivec3 with depth=1
        return f"{lhs}ivec3(imageSize({img}), 1);"


def emit_sample(op, ctx):
    """
    Emit texture sampling operation for 2D and 3D textures.
    
    GLSL Output depends on resource binding:
        - If resource is READ-ONLY (sampler): texture(sampler2D, vec2)
        - If resource is also WRITTEN (image): imageLoad(image2D, ivec2)
    
    Coordinate Handling:
        - If UV origin is in current pass: use actual UV value
        - If UV is cross-pass reference or placeholder: use inline normalized coords
        - Safety check: VEC2 coords extended to VEC3 with Z=0.5 for 3D textures
    
    Args:
        op: The SAMPLE operation from IR
        ctx: Emitter context with param, lhs, dispatch_size, graph, op_ids, reads_idx, writes_idx
    
    Returns:
        GLSL code string for the texture() or imageLoad() call
    """
    lhs = ctx['lhs']
    dispatch_size = ctx.get('dispatch_size', (512, 512, 1))
    param = ctx['param']
    current_op_ids = ctx.get('op_ids', set())
    graph = ctx.get('graph')
    reads_idx = ctx.get('reads_idx', set())
    writes_idx = ctx.get('writes_idx', set())
    
    sampler = param(op.inputs[0])
    uv_input = op.inputs[1]
    
    # Detect if texture is 3D from resource descriptor
    is_3d = False
    res_idx = op.inputs[0].resource_index
    if res_idx is not None and graph:
        res = graph.resources[res_idx]
        is_3d = getattr(res, 'dimensions', 2) == 3
    
    # Check if resource is declared as image (also written) vs sampler (read-only)
    is_image_binding = res_idx is not None and res_idx in writes_idx
    
    # Check if UV is usable in current pass (origin op is in this pass)
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
    
    w, h, d = dispatch_size[0], dispatch_size[1], dispatch_size[2]
    
    if is_image_binding:
        # Resource is bound as image2D (also written in this pass)
        # Must use imageLoad with integer pixel coordinates
        if is_3d:
            coord = "ivec3(gl_GlobalInvocationID)"
        else:
            coord = "ivec2(gl_GlobalInvocationID.xy)"
        return f"{lhs}imageLoad({sampler}, {coord});"
    else:
        # Resource is bound as sampler2D (read-only in this pass)
        # Use texture() with normalized UV coordinates
        if uv_available:
            # Use actual UV coords
            uv = param(uv_input)
            uv_type = uv_input.type
        else:
            # Use inline normalized UVs (for cross-pass or placeholder cases)
            if is_3d:
                # 3D: use all three dimensions from uniform
                uv = "((vec3(gl_GlobalInvocationID.xyz) + vec3(0.5)) / vec3(u_dispatch_size))"
                uv_type = DataType.VEC3
            else:
                # 2D: use xy from uniform
                uv = "((vec2(gl_GlobalInvocationID.xy) + vec2(0.5)) / vec2(u_dispatch_size.xy))"
                uv_type = DataType.VEC2
        
        # Type check: ensure coordinate matches texture dimensionality
        # Handler should have already adjusted this, but safety check
        if is_3d and uv_available and uv_type == DataType.VEC2:
            # Edge case: still got VEC2 for 3D texture, project to middle slice
            uv = f"vec3({uv}, 0.5)"
        
        return f"{lhs}texture({sampler}, {uv});"
