from typing import List, Set, Union, Dict
from ..ir.graph import Graph, Op, ValueKind
from ..ir.resources import ImageDesc
from ..ir.ops import OpCode
from .passes import ComputePass
from .analysis import get_topological_sort, find_hazards
from .loops import PassLoop, find_loop_regions, wrap_passes_in_loops


# Ops that are "pure" field operations - no side effects, safe to duplicate
# These ops can be safely copied into multiple passes when their output is used across pass boundaries
PURE_FIELD_OPS = {
    # Arithmetic
    OpCode.ADD, OpCode.SUB, OpCode.MUL, OpCode.DIV, OpCode.MOD,
    OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.SNAP, OpCode.PINGPONG,
    
    # Math / Common
    OpCode.ABS, OpCode.SIGN, OpCode.FLOOR, OpCode.CEIL, OpCode.FRACT,
    OpCode.TRUNC, OpCode.ROUND, OpCode.MIN, OpCode.MAX,
    OpCode.SMOOTH_MIN, OpCode.SMOOTH_MAX, OpCode.CLAMP, OpCode.MIX,
    
    # Exponential
    OpCode.POW, OpCode.SQRT, OpCode.INVERSE_SQRT, OpCode.EXP, OpCode.LOG,
    
    # Trigonometry
    OpCode.SIN, OpCode.COS, OpCode.TAN, OpCode.ASIN, OpCode.ACOS,
    OpCode.ATAN, OpCode.ATAN2, OpCode.SINH, OpCode.COSH, OpCode.TANH,
    OpCode.RADIANS, OpCode.DEGREES,
    
    # Vector
    OpCode.DOT, OpCode.CROSS, OpCode.LENGTH, OpCode.DISTANCE, OpCode.NORMALIZE,
    OpCode.REFLECT, OpCode.REFRACT, OpCode.FACEFORWARD, OpCode.PROJECT,
    
    # Relational / Comparison
    OpCode.EQ, OpCode.NEQ, OpCode.LT, OpCode.GT, OpCode.LE, OpCode.GE, OpCode.COMPARE,
    
    # Logic
    OpCode.AND, OpCode.OR, OpCode.NOT, OpCode.SELECT,
    
    # Constructors / Conversion
    OpCode.CAST, OpCode.SWIZZLE, OpCode.SEPARATE_XYZ, OpCode.COMBINE_XY, OpCode.COMBINE_XYZ,
    OpCode.SEPARATE_COLOR, OpCode.COMBINE_COLOR, OpCode.MAP_RANGE, OpCode.CLAMP_RANGE,
    
    # Texture / Procedural (read-only, safe to duplicate)
    OpCode.SAMPLE, OpCode.NOISE, OpCode.WHITE_NOISE, OpCode.VORONOI, OpCode.IMAGE_SIZE,
    
    # Inputs (constants and builtins are always safe)
    OpCode.CONSTANT, OpCode.BUILTIN,
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


class PassScheduler:
    """
    Schedules IR ops into executable ComputePasses.
    
    The scheduling process has 6 phases:
    1. Initial partitioning (hazard detection, resource limits)
    2. Field dependency propagation
    3. Resource access recalculation
    4. Dispatch size calculation
    5. Loop wrapping (PassLoop structures)
    6. Size-based splitting
    
    Example:
        scheduler = PassScheduler(graph)
        passes = scheduler.schedule()
    """
    
    # Maximum unique resources per pass (GPU binding limit is typically 8)
    MAX_RESOURCES_PER_PASS = 7
    
    def __init__(self, graph: Graph):
        """
        Initialize scheduler with graph to process.
        
        Args:
            graph: IR Graph containing ops and resources
        """
        self.graph = graph
        self.ops = get_topological_sort(graph)
        self._pass_counter = 0
    
    def schedule(self) -> List[Union[ComputePass, 'PassLoop']]:
        """
        Execute all scheduling phases and return passes.
        
        Returns:
            List of ComputePass and PassLoop items ready for execution
        """
        # Phase 1: Initial partitioning
        passes = self._phase1_initial_partition()
        
        # Phase 2: Field dependency propagation
        self._phase2_propagate_field_deps(passes)
        
        # Phase 3: Recalculate reads/writes
        self._phase3_recalculate_resources(passes)
        
        # Phase 4: Calculate dispatch sizes
        self._phase4_calculate_dispatch(passes)
        
        # Phase 5: Wrap in PassLoop structures
        passes = self._phase5_wrap_loops(passes)
        
        # Phase 6: Split by output size
        passes = self._phase6_split_by_size(passes)
        
        # Phase 7: Fuse compatible passes (optional optimization)
        passes = self._phase7_fuse_passes(passes)
        
        return passes
    
    def _new_pass_id(self) -> int:
        """Generate unique pass ID."""
        pid = self._pass_counter
        self._pass_counter += 1
        return pid
    
    def _phase1_initial_partition(self) -> List[ComputePass]:
        """
        Phase 1: Partition ops into passes based on hazards and resource limits.
        
        - Read-After-Write hazards force pass splits
        - Resource count exceeding GPU limits forces splits
        """
        passes: List[ComputePass] = []
        current_pass = ComputePass(pass_id=self._new_pass_id())
        dirtied_resources: Set[int] = set()
        
        for op in self.ops:
            # Check for hazards
            should_split = find_hazards(op, dirtied_resources)
            
            # Check resource limit
            if not should_split:
                op_reads = set(op.reads_resources())
                op_writes = set(op.writes_resources())
                future_resources = (current_pass.reads_idx | current_pass.writes_idx | 
                                   op_reads | op_writes)
                if len(future_resources) > self.MAX_RESOURCES_PER_PASS:
                    should_split = True
            
            if should_split:
                passes.append(current_pass)
                current_pass = ComputePass(pass_id=self._new_pass_id())
                dirtied_resources.clear()
            
            # Add op to current pass
            current_pass.add_op(op)
            
            # Track writes
            for res_idx in op.writes_resources():
                dirtied_resources.add(res_idx)
                res = self.graph.resources[res_idx]
                current_pass.writes.add(res)
                current_pass.writes_idx.add(res_idx)
            
            # Track reads
            for res_idx in op.reads_resources():
                res = self.graph.resources[res_idx]
                current_pass.reads.add(res)
                current_pass.reads_idx.add(res_idx)
        
        # Append final pass
        if current_pass.ops:
            passes.append(current_pass)
        
        return passes
    
    def _phase2_propagate_field_deps(self, passes: List[ComputePass]) -> None:
        """
        Phase 2: Ensure each pass has all field ops it depends on.
        
        Pure field ops (Position, Math, Noise) are duplicated across passes
        that need them.
        """
        for p in passes:
            ops_in_pass = {id(op) for op in p.ops}
            deps_to_add = []
            collected = set()
            
            for op in p.ops:
                collect_field_dependencies(op, collected, deps_to_add)
            
            new_deps = [dep for dep in deps_to_add if id(dep) not in ops_in_pass]
            
            if new_deps:
                p.ops = new_deps + p.ops
    
    def _phase3_recalculate_resources(self, passes: List[ComputePass]) -> None:
        """
        Phase 3: Recalculate reads/writes for all ops in each pass.
        
        Needed because Phase 2 adds ops that weren't tracked initially.
        """
        for p in passes:
            for op in p.ops:
                for res_idx in op.reads_resources():
                    res = self.graph.resources[res_idx]
                    p.reads.add(res)
                    p.reads_idx.add(res_idx)
                for res_idx in op.writes_resources():
                    res = self.graph.resources[res_idx]
                    p.writes.add(res)
                    p.writes_idx.add(res_idx)
    
    def _phase4_calculate_dispatch(self, passes: List[ComputePass]) -> None:
        """Phase 4: Calculate dispatch_size for each pass."""
        for p in passes:
            _calculate_dispatch_size(p, self.graph)
    
    def _phase5_wrap_loops(self, passes: List[ComputePass]) -> List[Union[ComputePass, 'PassLoop']]:
        """
        Phase 5: Detect PASS_LOOP regions and wrap in PassLoop structures.
        
        Also re-applies field dependency propagation to loop bodies.
        """
        loop_regions = find_loop_regions(self.ops)
        if not loop_regions:
            return passes
        
        wrapped = wrap_passes_in_loops(passes, loop_regions, self.ops, self.graph)
        _propagate_field_deps_recursive(wrapped, self.graph)
        return wrapped
    
    def _phase6_split_by_size(self, passes: list) -> list:
        """
        Phase 6: Split passes that write to resources with different sizes.
        
        Ensures each pass has a single dispatch size for correct UV calculations.
        """
        return _split_passes_by_output_size(passes, self.graph)
    
    def _phase7_fuse_passes(self, passes: list) -> list:
        """
        Phase 7: Fuse compatible consecutive passes to reduce GPU dispatches.
        
        Two passes can be fused if:
        1. Both are ComputePass (not PassLoop)
        2. Same dispatch size
        3. No RAW hazard between them
        4. Combined resources <= MAX_RESOURCES_PER_PASS
        
        This is a conservative optimization that maintains correctness.
        """
        if len(passes) < 2:
            return passes
        
        result = []
        i = 0
        fusions = 0
        
        while i < len(passes):
            current = passes[i]
            
            # Only fuse ComputePass, not PassLoop
            if hasattr(current, 'body_passes'):
                # PassLoop - process body recursively
                current.body_passes = self._phase7_fuse_passes(current.body_passes)
                result.append(current)
                i += 1
                continue
            
            # Try to fuse with next passes
            while i + 1 < len(passes):
                next_pass = passes[i + 1]
                
                # Don't fuse across loops
                if hasattr(next_pass, 'body_passes'):
                    break
                
                # Check if fusible
                if _can_fuse_passes(current, next_pass, self.MAX_RESOURCES_PER_PASS):
                    current = _fuse_two_passes(current, next_pass)
                    fusions += 1
                    i += 1
                else:
                    break
            
            result.append(current)
            i += 1
        
        if fusions > 0:
            from ..logger import log_debug
            log_debug(f"Pass fusion: {fusions} passes fused, {len(result)} passes remain")
        
        return result


def schedule_passes(graph: Graph) -> List[Union[ComputePass, PassLoop]]:
    """
    Partitions the graph into a list of executable ComputePasses.
    
    This is the main entry point for scheduling. Uses PassScheduler internally.
    
    Args:
        graph: IR Graph to schedule
        
    Returns:
        List of ComputePass and PassLoop items
    """
    scheduler = PassScheduler(graph)
    return scheduler.schedule()



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


def _can_fuse_passes(pass_a: ComputePass, pass_b: ComputePass, max_resources: int) -> bool:
    """
    Check if two passes can be safely fused.
    
    Criteria:
    1. Same dispatch size
    2. No RAW hazard (pass_b doesn't read what pass_a writes)
    3. Combined resources don't exceed limit
    """
    # Must have same dispatch size
    if pass_a.dispatch_size != pass_b.dispatch_size:
        return False
    
    # Check for RAW hazard: pass_b reads what pass_a writes
    if pass_a.writes_idx & pass_b.reads_idx:
        return False
    
    # Check resource limit
    combined_resources = (pass_a.reads_idx | pass_a.writes_idx | 
                          pass_b.reads_idx | pass_b.writes_idx)
    if len(combined_resources) > max_resources:
        return False
    
    return True


def _fuse_two_passes(pass_a: ComputePass, pass_b: ComputePass) -> ComputePass:
    """Merge two ComputePasses into one."""
    fused = ComputePass(pass_id=pass_a.id)  # Keep first pass's ID
    
    # Combine ops in order
    for op in pass_a.ops:
        fused.add_op(op)
    for op in pass_b.ops:
        fused.add_op(op)
    
    # Combine resources
    fused.reads = pass_a.reads | pass_b.reads
    fused.writes = pass_a.writes | pass_b.writes
    fused.reads_idx = pass_a.reads_idx | pass_b.reads_idx
    fused.writes_idx = pass_a.writes_idx | pass_b.writes_idx
    
    # Use first pass's dispatch size (should be same)
    fused.dispatch_size = pass_a.dispatch_size
    
    return fused
