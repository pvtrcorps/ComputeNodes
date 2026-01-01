# Control Flow Emitters
# Handles: LOOP_START, LOOP_END, PASS_LOOP_*


def emit_loop_start(op, ctx):
    """Emit loop start: declares accumulator and begins for loop."""
    param = ctx.param
    type_str = ctx.type_str
    
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
    param = ctx.param
    type_str = ctx.type_str
    
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
    PASS_LOOP_BEGIN: Emit iteration counter from uniform.
    
    The executor passes u_loop_iteration for each iteration of the multi-pass loop.
    """
    type_str = ctx.type_str
    lines = []
    
    # Declare iteration counter output from uniform (set by executor each iteration)
    if op.outputs:
        iter_id = op.outputs[0].id
        lines.append(f"    // Pass loop iteration (from executor uniform)")
        lines.append(f"    int v{iter_id} = u_loop_iteration;")
    
    return "\n".join(lines)


def emit_pass_loop_end(op, ctx):
    """
    PASS_LOOP_END: Minimal emission for multi-pass loops.
    
    Multi-pass loops are executed N times by the executor, NOT by GLSL for-loops.
    Scalars cannot be passed between iterations (no ping-pong buffer).
    
    Grid states use ping-pong buffers managed by executor - no GLSL code needed.
    Scalar states CANNOT reference inputs from previous iterations - they don't exist!
    
    Solution: Don't emit ANY code for loop outputs. The executor handles state.
    """
    from ...ir.types import DataType
    
    # For multi-pass loops, the state is managed entirely by the executor
    # via ping-pong buffers (Grids) or is unsupported (scalars).
    # We shouldn't generate any GLSL code that tries to reference "next" values
    # from previous shader invocations - they don't exist in the same shader!
    
    return "    // Multi-pass loop end (state managed by executor)"


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

