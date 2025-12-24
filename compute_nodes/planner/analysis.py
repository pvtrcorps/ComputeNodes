from typing import List, Dict, Set, Tuple
from ..ir.graph import Graph, Op, ValueKind
from ..ir.resources import ResourceDesc

def get_topological_sort(graph: Graph) -> List[Op]:
    """
    Returns a list of Ops in topological order.
    """
    visited = set()
    order = []
    
    # Simple recursive DFS
    def visit(op: Op):
        if id(op) in visited:
            return
        
        # Visit dependencies (inputs that are SSA)
        for val in op.inputs:
            if val.kind == ValueKind.SSA and val.origin:
                visit(val.origin)
                
        visited.add(id(op))
        order.append(op)

    # Visit all ops in all blocks (assuming basic block structure for now)
    # Ideally start from "Terminal" ops (Side effects / Outputs)
    # But finding all reachable ops is safer for complete coverage.
    
    # Strategy 1: Iterate all ops in blocks (usually strictly ordered by builder)
    # Strategy 2: Traverse from Output Ops backwards (lazy)
    
    # Using builder order is usually roughly topological if built correctly,
    # but reordering ensures safety.
    all_ops = []
    for block in graph.blocks:
        all_ops.extend(block.ops)
    
    # We re-sort to guarantee dependencies are met
    # Reset visited and order for the actual sort
    visited.clear()
    order.clear()
    
    for op in all_ops:
        visit(op)
        
    return order

def find_hazards(op: Op, dirtied_resources: Set[int]) -> bool:
    """
    Checks if 'op' reads a resource that has been dirtied in the current context.
    Returns True if a hazard (Read-After-Write) exists.
    """
    reads = op.reads_resources()
    for res_idx in reads:
        if res_idx in dirtied_resources:
            return True
    return False
