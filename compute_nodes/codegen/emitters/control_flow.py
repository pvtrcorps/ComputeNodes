# Control Flow Emitters
# Handles: LOOP_START, LOOP_END, PASS_LOOP_*


def emit_loop_start(op, ctx):
    """Emit loop start: declares accumulator and begins for loop."""
    param = ctx['param']
    type_str = ctx['type_str']
    
    iters = param(op.inputs[0])
    init_val = param(op.inputs[1])
    
    acc_id = op.outputs[0].id
    idx_id = op.outputs[1].id
    
    acc_type = type_str(op.outputs[0].type)
    
    lines = []
    lines.append(f"    {acc_type} v{acc_id} = {init_val};")
    lines.append(f"    for (int i=0; i<{iters}; ++i) {{")
    lines.append(f"        int v{idx_id} = i;")
    return "\n".join(lines)


def emit_loop_end(op, ctx):
    """Emit loop end: updates accumulator and closes loop."""
    param = ctx['param']
    type_str = ctx['type_str']
    
    next_val = param(op.inputs[0])
    acc_val = param(op.inputs[1])
    
    res_id = op.outputs[0].id
    res_type = type_str(op.outputs[0].type)
    
    lines = []
    lines.append(f"        {acc_val} = {next_val};")
    lines.append(f"    }}")
    lines.append(f"    {res_type} v{res_id} = {acc_val};")
    return "\n".join(lines)


# ============= Multi-Pass Loop Emitters =============
# These are no-ops in GLSL - the loop is handled by ComputeExecutor
# which runs the body pass multiple times with ping-pong buffers.

def emit_pass_loop_begin(op, ctx):
    """
    PASS_LOOP_BEGIN: No-op in GLSL.
    Loop iteration is handled by executor.
    Output iteration index as constant 0 (will be overwritten per-pass).
    """
    type_str = ctx['type_str']
    lines = []
    
    # Declare iteration counter output
    if op.outputs:
        iter_id = op.outputs[0].id
        lines.append(f"    // Pass loop iteration (managed by executor)")
        lines.append(f"    int v{iter_id} = 0;")
    
    return "\n".join(lines)


def emit_pass_loop_end(op, ctx):
    """
    PASS_LOOP_END: No-op in GLSL.
    Values are passed through ping-pong buffers by executor.
    Skip HANDLE outputs - grids are resources, not GLSL variables.
    """
    from ...ir.types import DataType
    
    type_str = ctx['type_str']
    param = ctx['param']
    lines = []
    
    # Declare outputs that reference the "next" values
    # Skip HANDLE types - they're image resources, not GLSL variables
    for i, out in enumerate(op.outputs):
        if out.type == DataType.HANDLE:
            # Grid outputs - no GLSL declaration needed
            lines.append(f"    // Grid state passed via ping-pong buffer")
            continue
            
        out_type = type_str(out.type)
        if i < len(op.inputs):
            val = param(op.inputs[i])
            lines.append(f"    {out_type} v{out.id} = {val};")
        else:
            lines.append(f"    {out_type} v{out.id};  // loop final")
    
    return "\n".join(lines)


def emit_pass_loop_read(op, ctx):
    """
    PASS_LOOP_READ: No-op, value comes from ping buffer.
    The resource binding handles the correct buffer at runtime.
    """
    # Output already has resource_index set, just declare variable
    lines = []
    if op.outputs:
        out = op.outputs[0]
        lines.append(f"    // Loop state read from ping buffer")
    return "\n".join(lines)


def emit_pass_loop_write(op, ctx):
    """
    PASS_LOOP_WRITE: No-op, value goes to pong buffer.
    The resource binding handles the correct buffer at runtime.
    """
    return "    // Loop state write to pong buffer"

