# Image Operation Emitters
# Handles: IMAGE_STORE, IMAGE_LOAD, IMAGE_SIZE

from ...ir.graph import ValueKind


def emit_image_store(op, ctx):
    """Emit imageStore operation."""
    param = ctx['param']
    
    img = param(op.inputs[0])
    coord = param(op.inputs[1])
    data = param(op.inputs[2])

    # Check if 'data' is a Resource (e.g. Image Input connected to Write)
    data_val = op.inputs[2]
    if data_val.kind == ValueKind.ARGUMENT and data_val.resource_index is not None:
        # It's a resource (img_X). We need to sample it.
        data = f"texelFetch({data}, {coord}, 0)"

    return f"    imageStore({img}, {coord}, {data});"


def emit_image_load(op, ctx):
    """Emit imageLoad operation."""
    lhs = ctx['lhs']
    param = ctx['param']
    graph = ctx['graph']
    
    img = param(op.inputs[0])
    coord = param(op.inputs[1])
    
    # Check if sampler
    res_idx = op.inputs[0].resource_index
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
