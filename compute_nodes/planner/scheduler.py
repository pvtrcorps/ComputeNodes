from typing import List, Set, Union, Dict
from ..ir.graph import Graph, Op, ValueKind
from ..ir.resources import ImageDesc
from ..ir.ops import OpCode
from .passes import ComputePass
from .analysis import get_topological_sort, find_hazards
from .loops import PassLoop, find_loop_regions, wrap_passes_in_loops


# Ops that are "pure" field operations - no side effects, safe to duplicate
PURE_FIELD_OPS = {
    OpCode.BUILTIN, OpCode.CONSTANT, OpCode.ADD, OpCode.SUB, OpCode.MUL, 
    OpCode.DIV, OpCode.CAST, OpCode.SWIZZLE, OpCode.COMBINE_XYZ, OpCode.COMBINE_XY,
    OpCode.SEPARATE_XYZ, OpCode.SEPARATE_COLOR, OpCode.DOT, OpCode.CROSS,
    OpCode.NORMALIZE, OpCode.LENGTH, OpCode.DISTANCE, OpCode.MIN, OpCode.MAX, OpCode.ABS,
    OpCode.FLOOR, OpCode.CEIL, OpCode.FRACT, OpCode.MOD, OpCode.POW,
    OpCode.SQRT, OpCode.SIN, OpCode.COS, OpCode.TAN,
    OpCode.NOISE, OpCode.VORONOI, OpCode.COMPARE, OpCode.SELECT,
    OpCode.SNAP, OpCode.WRAP, OpCode.CLAMP, OpCode.MAP_RANGE,
    OpCode.MIX, OpCode.MULTIPLY_ADD,
    OpCode.SAMPLE,  # Read-only operation, safe to duplicate across passes
    OpCode.IMAGE_SIZE,  # Read-only metadata query, safe to duplicate
}


def is_pure_field_op(op: Op) -> bool:
    """Check if an op is a pure field operation (no side effects)."""
    return op.opcode in PURE_FIELD_OPS


def collect_field_dependencies(op: Op, collected: Set[int], all_deps: List[Op]):
    """Recursively collect pure field op dependencies."""
    for val in op.inputs:
        if val.kind == ValueKind.SSA and val.origin:
            dep_op = val.origin
            if id(dep_op) not in collected and is_pure_field_op(dep_op):
                collected.add(id(dep_op))
                # First collect deps of this dep (deeper first)
                collect_field_dependencies(dep_op, collected, all_deps)
                all_deps.append(dep_op)


def schedule_passes(graph: Graph) -> List[Union[ComputePass, PassLoop]]:
    """
    Partitions the graph into a list of executable ComputePasses.
    Handles hazard detection (Read-After-Write) by splitting passes.
    Also calculates dispatch_size for each pass based on output dimensions.
    
    Field Dependency Handling:
    - After initial pass split, ensures each pass has all field ops it needs
    - Pure field ops (Position, Noise, Math) are duplicated across passes
    """
    ops = get_topological_sort(graph)
    passes: List[ComputePass] = []
    
    current_pass = ComputePass(pass_id=0)
    dirtied_resources: Set[int] = set()
    op_to_pass: Dict[int, int] = {}  # Track which pass each op was originally assigned to
    
    # Maximum unique resources per pass (GPU binding limit is typically 8)
    MAX_RESOURCES_PER_PASS = 7
    
    for op in ops:
        # Check for Hazards
        # Does this op read something written in current pass?
        should_split = find_hazards(op, dirtied_resources)
        
        # Also check resource limit - prevent exceeding GPU binding slots
        if not should_split:
            op_reads = set(op.reads_resources())
            op_writes = set(op.writes_resources())
            future_resources = (current_pass.reads_idx | current_pass.writes_idx | 
                               op_reads | op_writes)
            if len(future_resources) > MAX_RESOURCES_PER_PASS:
                should_split = True
        
        if should_split:
            # SPLIT PASS
            passes.append(current_pass)
            new_id = len(passes)
            current_pass = ComputePass(pass_id=new_id)
            dirtied_resources.clear()
            
        # Add op to current pass
        current_pass.add_op(op)
        op_to_pass[id(op)] = current_pass.id
        
        # Track Writes
        writes = op.writes_resources()
        for res_idx in writes:
            dirtied_resources.add(res_idx)
            # Add to pass metadata
            res = graph.resources[res_idx]
            current_pass.writes.add(res)
            current_pass.writes_idx.add(res_idx)
            
        # Track Reads
        reads = op.reads_resources()
        for res_idx in reads:
             res = graph.resources[res_idx]
             current_pass.reads.add(res)
             current_pass.reads_idx.add(res_idx)
             
    # Append final pass
    if current_pass.ops:
        passes.append(current_pass)
    
    # ===== PHASE 2: Ensure field dependencies are in each pass =====
    # For each pass, check if ops use SSA values from other passes
    # If so, and the source is a pure field op, include it in this pass
    for p in passes:
        ops_in_pass = {id(op) for op in p.ops}
        deps_to_add = []
        collected = set()
        
        for op in p.ops:
            # Collect all field dependencies
            collect_field_dependencies(op, collected, deps_to_add)
        
        # Filter to deps NOT already in this pass
        new_deps = [dep for dep in deps_to_add if id(dep) not in ops_in_pass]
        
        # Prepend all new deps at once (preserves order)
        if new_deps:
            p.ops = new_deps + p.ops
            for dep in new_deps:
                ops_in_pass.add(id(dep))
    
    # ===== PHASE 2.5: Recalculate reads/writes for all ops in each pass =====
    # This ensures that ops added during field dependency propagation 
    # (like SAMPLE from auto-sample) have their resource accesses tracked
    for p in passes:
        for op in p.ops:
            # Track Reads
            reads = op.reads_resources()
            for res_idx in reads:
                res = graph.resources[res_idx]
                p.reads.add(res)
                p.reads_idx.add(res_idx)
            # Track Writes
            writes = op.writes_resources()
            for res_idx in writes:
                res = graph.resources[res_idx]
                p.writes.add(res)
                p.writes_idx.add(res_idx)
    
    # Calculate dispatch_size for each pass based on write resources
    for p in passes:
        _calculate_dispatch_size(p, graph)
    
    # ===== PHASE 4: Detect PASS_LOOP regions and wrap in PassLoop =====
    # Find PASS_LOOP_BEGIN/END pairs and wrap intervening passes
    loop_regions = find_loop_regions(ops)
    if loop_regions:
        passes = wrap_passes_in_loops(passes, loop_regions, ops, graph)
        
        # PHASE 4.5: Re-apply field dependency propagation to loop body passes
        # wrap_passes_in_loops recreates passes from raw ops, losing Phase 2 deps
        _propagate_field_deps_recursive(passes, graph)
    
    # ===== PHASE 5: Split passes by output size =====
    # When a pass writes to resources with different sizes, split into separate passes
    # This ensures correct UV/dispatch calculations for each output
    passes = _split_passes_by_output_size(passes, graph)
        
    return passes


def _propagate_field_deps_to_pass(p: ComputePass, graph: Graph):
    """Apply field dependency propagation to a single pass."""
    ops_in_pass = {id(op) for op in p.ops}
    deps_to_add = []
    collected = set()
    
    for op in p.ops:
        collect_field_dependencies(op, collected, deps_to_add)
    
    # Filter to deps NOT already in this pass
    new_deps = [dep for dep in deps_to_add if id(dep) not in ops_in_pass]
    
    # Prepend all new deps at once (preserves order)
    if new_deps:
        p.ops = new_deps + p.ops
        # Update reads/writes for new deps
        for dep in new_deps:
            for res_idx in dep.reads_resources():
                res = graph.resources[res_idx]
                p.reads.add(res)
                p.reads_idx.add(res_idx)
            for res_idx in dep.writes_resources():
                res = graph.resources[res_idx]
                p.writes.add(res)
                p.writes_idx.add(res_idx)


def _propagate_field_deps_recursive(passes, graph: Graph):
    """Recursively apply field dependency propagation to all passes including loop bodies."""
    for item in passes:
        if hasattr(item, 'body_passes'):  # PassLoop
            _propagate_field_deps_recursive(item.body_passes, graph)
        else:  # ComputePass
            _propagate_field_deps_to_pass(item, graph)


def _calculate_dispatch_size(compute_pass: ComputePass, graph: Graph):
    """
    Calculate the dispatch size for a pass based on its output resources.
    
    Priority:
    1. If any write resource has explicit size, use the largest
    2. Otherwise, use (0, 0) to indicate "use context default"
    """
    max_width = 0
    max_height = 0
    max_depth = 1
    
    for res in compute_pass.writes:
        if isinstance(res, ImageDesc) and res.size != (0, 0):
            w = res.width
            h = res.height
            d = res.depth
            
            if w * h * d > max_width * max_height * max_depth:
                max_width = w
                max_height = h
                max_depth = d
    
    if max_width > 0:
        compute_pass.dispatch_size = (max_width, max_height, max_depth)
    else:
        # Leave as default (0, 0, 0) to signal "use context"
        compute_pass.dispatch_size = (0, 0, 0)


def _get_write_size(op: Op, graph: Graph) -> tuple:
    """Get the size of the resource this op writes to."""
    writes = op.writes_resources()
    if not writes:
        return (0, 0)
    
    # Get the first write's size
    for res_idx in writes:
        if res_idx < len(graph.resources):
            res = graph.resources[res_idx]
            if hasattr(res, 'size') and res.size != (0, 0):
                return res.size
    return (0, 0)


def _split_passes_by_output_size(passes: list, graph: Graph) -> list:
    """
    Split passes that write to resources with different sizes.
    
    When a pass contains IMAGE_STORE ops that write to resources of different
    sizes, we split them into separate passes. This ensures each pass has a
    single dispatch size, fixing UV calculation issues.
    
    This function processes both regular ComputePasses and PassLoops recursively.
    """
    result = []
    
    for item in passes:
        if hasattr(item, 'body_passes'):  # PassLoop
            # Recursively process loop body passes
            item.body_passes = _split_passes_by_output_size(item.body_passes, graph)
            result.append(item)
        else:  # ComputePass
            split_passes = _split_single_pass_by_size(item, graph)
            result.extend(split_passes)
    
    return result


def _split_single_pass_by_size(compute_pass: ComputePass, graph: Graph) -> list:
    """
    Split a single pass if it writes to resources with different sizes.
    
    Returns a list of passes (may be just the original if no split needed).
    """
    # Group ops by the size of their write target
    size_to_ops: Dict[tuple, list] = {}
    non_writing_ops = []
    
    for op in compute_pass.ops:
        writes = op.writes_resources()
        if writes:
            size = _get_write_size(op, graph)
            if size not in size_to_ops:
                size_to_ops[size] = []
            size_to_ops[size].append(op)
        else:
            # Non-writing ops (field computations) need to be duplicated
            non_writing_ops.append(op)
    
    # If all writes are same size (or no splits needed), return original
    if len(size_to_ops) <= 1:
        return [compute_pass]
    
    # Split into multiple passes
    result = []
    base_id = compute_pass.id
    
    for idx, (size, ops) in enumerate(sorted(size_to_ops.items(), key=lambda x: x[0])):
        new_pass = ComputePass(pass_id=f"{base_id}_{idx}")
        
        # Add non-writing ops first (field dependencies)
        for op in non_writing_ops:
            new_pass.add_op(op)
        
        # Add the writing ops for this size
        for op in ops:
            new_pass.add_op(op)
        
        # Recalculate reads/writes
        new_pass.reads = set()
        new_pass.writes = set()
        new_pass.reads_idx = set()
        new_pass.writes_idx = set()
        
        for op in new_pass.ops:
            for res_idx in op.reads_resources():
                res = graph.resources[res_idx]
                new_pass.reads.add(res)
                new_pass.reads_idx.add(res_idx)
            for res_idx in op.writes_resources():
                res = graph.resources[res_idx]
                new_pass.writes.add(res)
                new_pass.writes_idx.add(res_idx)
        
        # Calculate dispatch size for this pass
        _calculate_dispatch_size(new_pass, graph)
        
        result.append(new_pass)
    
    return result
