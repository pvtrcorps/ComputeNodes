from typing import List
from ..ir.graph import Graph, Op, ValueKind
from .passes import ComputePass
from .analysis import get_topological_sort, find_hazards

def schedule_passes(graph: Graph) -> List[ComputePass]:
    """
    Partitions the graph into a list of executable ComputePasses.
    Handles hazard detection (Read-After-Write) by splitting passes.
    """
    ops = get_topological_sort(graph)
    passes: List[ComputePass] = []
    
    current_pass = ComputePass(pass_id=0)
    dirtied_resources = set()
    
    for op in ops:
        # Check for Hazards
        # 1. Logic Check: Does this op read something written in current pass?
        if find_hazards(op, dirtied_resources):
            # 2. Logic Check: Does this op have different dispatch requirements?
            # (Not implemented in MVP yet, assuming uniform dispatch for now)
            
            # SPLIT PASS
            passes.append(current_pass)
            new_id = len(passes)
            current_pass = ComputePass(pass_id=new_id)
            dirtied_resources.clear()
            
        # Add op to current pass
        current_pass.add_op(op)
        
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
        
    return passes
