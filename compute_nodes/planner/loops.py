# Loop scheduling structures for multi-pass GPU loops
#
# PassLoop represents a region that executes multiple times with
# ping-pong buffering between iterations.

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Union, Tuple


@dataclass
class StateVar:
    """A state variable in a loop with ping-pong buffering."""
    name: str
    index: int
    is_grid: bool
    data_type: Any  # DataType
    
    # For Grid types: ping-pong buffer indices
    ping_idx: Optional[int] = None
    pong_idx: Optional[int] = None
    
    # Initial value reference
    initial_value: Any = None
    
    # Current size for Grid types
    size: Tuple[int, int, int] = (0, 0, 0)
    dimensions: int = 2
    
    # Socket name mappings (used by handler)
    initial_socket: Optional[str] = None
    current_socket: Optional[str] = None
    next_socket: Optional[str] = None
    final_socket: Optional[str] = None
    
    # Runtime values (used during processing)
    current_value: Any = None
    next_value: Any = None
    
    # For blur/filter outputs that need copying to pong buffer
    copy_from_resource: Optional[int] = None


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


def wrap_passes_in_loops(passes: List, regions: List[Dict], ops: List) -> List:
    """
    Wraps sequences of ComputePass into PassLoop structures based on regions.
    
    Supports nested loops by using stack-based parsing to match BEGIN/END pairs.
    Each PassLoop can contain other PassLoops in its body_passes.
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
    
    def items_to_passes(items, dispatch_size):
        """Convert list of ops/PassLoops to list of ComputePass/PassLoop."""
        result_list = []
        current_ops = []
        
        def flush_ops():
            nonlocal current_ops
            if current_ops:
                cp = ComputePass(pass_id=new_pass_id())
                cp.ops.extend(current_ops)
                cp.dispatch_size = dispatch_size
                for op in current_ops:
                    for idx in op.reads_resources():
                        cp.reads_idx.add(idx)
                    for idx in op.writes_resources():
                        cp.writes_idx.add(idx)
                result_list.append(cp)
                current_ops = []
        
        for item in items:
            if isinstance(item, PassLoop):
                flush_ops()
                # Recursively convert body items
                if hasattr(item, '_raw_body_items'):
                    item.body_passes = items_to_passes(item._raw_body_items, dispatch_size)
                    delattr(item, '_raw_body_items')
                result_list.append(item)
            else:
                current_ops.append(item)
        
        flush_ops()
        return result_list
    
    # Process each input pass
    for p in passes:
        # Check if this pass has any loop markers
        has_loop = any(op.opcode in (OpCode.PASS_LOOP_BEGIN, OpCode.PASS_LOOP_END) 
                       for op in p.ops)
        
        if has_loop:
            # Parse and restructure
            parsed_items, _ = parse_ops_recursive(p.ops, 0)
            new_passes = items_to_passes(parsed_items, p.dispatch_size)
            result.extend(new_passes)
        else:
            result.append(p)
    
    return result

