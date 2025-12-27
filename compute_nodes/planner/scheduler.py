from typing import List, Set, Union
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
    dirtied_resources = set()
    op_to_pass = {}  # Track which pass each op was originally assigned to
    
    for op in ops:
        # Check for Hazards
        # Does this op read something written in current pass?
        if find_hazards(op, dirtied_resources):
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
        passes = wrap_passes_in_loops(passes, loop_regions, ops)
        
    return passes


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

