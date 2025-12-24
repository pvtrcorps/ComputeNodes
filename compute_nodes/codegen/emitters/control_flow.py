# Control Flow Emitters
# Handles: LOOP_START, LOOP_END


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
