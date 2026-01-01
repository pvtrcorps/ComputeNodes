# Loop scheduling structures for multi-pass GPU loops
#
# PassLoop represents a region that executes multiple times with
# ping-pong buffering between iterations.

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple


from ..ir.state import StateVar


@dataclass 
class PassLoop:
    """
    Represents a multi-pass loop structure.
    
    The loop executes its body_passes N times, with automatic
    ping-pong buffer swapping for Grid state variables.
    """
    iterations: int | Any  # Can be constant int or a Value reference
    body_passes: List[Any] = field(default_factory=list)  # List[ComputePass | PassLoop]
    state_vars: List[StateVar] = field(default_factory=list)
    
    # Metadata from the loop
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For resolution cascade support
    resolution_per_iteration: Optional[Dict[int, Tuple[int, int, int]]] = None
    
    def __post_init__(self):
        """Convert state_vars dicts to StateVar objects if needed."""
        converted = []
        for sv in self.state_vars:
            if isinstance(sv, dict):
                converted.append(StateVar(**sv))
            else:
                converted.append(sv)
        self.state_vars = converted


def is_loop_boundary_op(op) -> bool:
    """Check if an op marks a loop boundary."""
    from ..ir.ops import OpCode
    return op.opcode in {OpCode.PASS_LOOP_BEGIN, OpCode.PASS_LOOP_END}


def find_loop_regions(ops: List) -> List[Dict]:
    """
    Find PASS_LOOP_BEGIN/END pairs in opcodes.
    
    Returns list of regions: {begin_idx, end_idx, begin_op, end_op, metadata}
    """
    from ..ir.ops import OpCode
    
    regions = []
    begin_stack = []  # Stack for nested loops
    
    for i, op in enumerate(ops):
        if op.opcode == OpCode.PASS_LOOP_BEGIN:
            begin_stack.append((i, op))
        elif op.opcode == OpCode.PASS_LOOP_END:
            if begin_stack:
                begin_idx, begin_op = begin_stack.pop()
                regions.append({
                    'begin_idx': begin_idx,
                    'end_idx': i,
                    'begin_op': begin_op,
                    'end_op': op,
                    'metadata': begin_op.metadata or {},
                    'depth': len(begin_stack),  # Nesting level
                })
    
    return regions


def wrap_passes_in_loops(passes: List, regions: List[Dict], ops: List, graph=None) -> List:
    """
    Wraps sequences of ComputePass into PassLoop structures based on regions.
    
    Supports nested loops by using stack-based parsing to match BEGIN/END pairs.
    Each PassLoop can contain other PassLoops in its body_passes.
    
    Args:
        passes: List of ComputePass
        regions: List of loop regions
        ops: List of ops
        graph: Optional Graph object for resource lookup (needed to populate pass.writes/reads)
    """
    from ..planner.passes import ComputePass
    from ..ir.ops import OpCode
    
    if not regions:
        return passes
    
    result = []
    pass_counter = [100]
    
    def new_pass_id():
        pass_counter[0] += 1
        return pass_counter[0]
    
    def resolve_iterations(raw_iterations):
        """Extract integer iteration count from Value or int."""
        if hasattr(raw_iterations, 'origin') and raw_iterations.origin:
            origin = raw_iterations.origin
            if hasattr(origin, 'attrs') and 'value' in origin.attrs:
                return int(origin.attrs['value'])
            return 10
        elif isinstance(raw_iterations, (int, float)):
            return int(raw_iterations)
        return 10
    
    def parse_ops_recursive(ops_list, start_idx=0):
        """
        Recursively parse ops, building PassLoops for nested structures.
        Returns (items, end_idx) where items is list of ops/PassLoops.
        """
        items = []
        i = start_idx
        
        while i < len(ops_list):
            op = ops_list[i]
            
            if op.opcode == OpCode.PASS_LOOP_BEGIN:
                # Start of a loop - find matching END
                loop_metadata = op.metadata or {}
                
                # Collect body by recursing (handles nested loops)
                body_items, end_i = parse_ops_recursive(ops_list, i + 1)
                
                # IMPORTANT: Include the BEGIN op in body so iteration variable is declared
                body_items.insert(0, op)
                
                # Create loop
                iterations = resolve_iterations(loop_metadata.get('iterations', 10))
                loop = PassLoop(
                    iterations=iterations,
                    body_passes=[],  # Will be populated with ComputePass(es)
                    state_vars=loop_metadata.get('state_vars', []),
                    metadata=loop_metadata,
                )
                loop._raw_body_items = body_items  # Store for later conversion
                items.append(loop)
                i = end_i + 1  # Skip past END
                
            elif op.opcode == OpCode.PASS_LOOP_END:
                # End of current level - return to parent
                return items, i
                
            else:
                # Regular op
                items.append(op)
                i += 1
        
        return items, i
    
    def items_to_passes(items):
        """Convert list of ops/PassLoops to list of ComputePass/PassLoop."""
        result_list = []
        current_ops = []
        
        def flush_ops():
            nonlocal current_ops
            if current_ops:
                cp = ComputePass(pass_id=new_pass_id())
                cp.ops.extend(current_ops)
                
                # Default dispatch
                cp.dispatch_size = (0, 0, 0)
                
                max_w, max_h, max_d = 0, 0, 1
                
                for op in current_ops:
                    for idx in op.reads_resources():
                        cp.reads_idx.add(idx)
                        if graph and idx < len(graph.resources):
                            cp.reads.add(graph.resources[idx])
                            
                    for idx in op.writes_resources():
                        cp.writes_idx.add(idx)
                        if graph and idx < len(graph.resources):
                            res = graph.resources[idx]
                            cp.writes.add(res)
                            
                            # Track max dimensions for dispatch
                            if hasattr(res, 'width'):
                                w = getattr(res, 'width', 0)
                                h = getattr(res, 'height', 0)
                                d = getattr(res, 'depth', 1)
                                if w * h * d > max_w * max_h * max_d:
                                    max_w, max_h, max_d = w, h, d
                
                if max_w > 0:
                    cp.dispatch_size = (max_w, max_h, max_d)
                else:
                    # Fallback/Inherit?
                    # For loops, maybe we want to use the 'main' loop size if available?
                    # But (0,0,0) allows runtime defaults.
                    pass
                            
                result_list.append(cp)
                current_ops = []
        
        for item in items:
            if isinstance(item, PassLoop):
                flush_ops()
                # Recursively convert body items
                if hasattr(item, '_raw_body_items'):
                    item.body_passes = items_to_passes(item._raw_body_items)
                    delattr(item, '_raw_body_items')
                result_list.append(item)
            else:
                current_ops.append(item)
        
        flush_ops()
        return result_list
    
    # CRITICAL FIX: When hazard detection splits a loop region into multiple passes,
    # we need to merge ALL ops and parse once, not process passes individually.
    # Otherwise, LOOP_BEGIN may be in Pass 0, LOOP_END in Pass 3, and ops between
    # them get incorrectly structured.
    
    # First, merge all ops from all passes that contain any loop markers
    all_ops = []
    
    # Check if ANY pass has loop markers - if so, we need unified processing
    any_loop_markers = any(
        any(op.opcode in (OpCode.PASS_LOOP_BEGIN, OpCode.PASS_LOOP_END) for op in p.ops)
        for p in passes
    )
    
    if any_loop_markers:
        # Merge all ops from all passes
        for p in passes:
            all_ops.extend(p.ops)
        
        # Parse the merged ops
        parsed_items, _ = parse_ops_recursive(all_ops, 0)
        result = items_to_passes(parsed_items)
    else:
        # No loops - just return passes as-is
        result = list(passes)
    
    return result

