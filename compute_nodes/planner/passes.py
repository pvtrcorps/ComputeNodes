from typing import List, Set, Dict, Optional
from ..ir.graph import Op
from ..ir.resources import ResourceDesc

class ComputePass:
    """
    Represents a single dispatch / draw call in the execution pipeline.
    It contains a sequence of Operations that can be executed together
    without internal barriers (or with minimal local synchronization).
    """
    def __init__(self, pass_id: int):
        self.id = pass_id
        self.ops: List[Op] = []       # Topological order of ops in this pass
        self.root_ops: List[Op] = []  # Ops that are the 'roots' (e.g. Stores)
        
        # Resources used in this pass
        self.reads: Set[ResourceDesc] = set()
        self.writes: Set[ResourceDesc] = set()
        
        # Resource Indices (Source of Truth)
        self.reads_idx: Set[int] = set()
        self.writes_idx: Set[int] = set()
        
        # Dispatch configuration (to be improved)
        self.dispatch_size = (1, 1, 1)

        # Shader Source
        self.source: str = ""
        self.display_source: Optional[str] = None

    def add_op(self, op: Op):
        self.ops.append(op)
        # Assuming resource tracking happens during scheduling/analysis
        # but we could helper update here.

    def __repr__(self):
        return f"<ComputePass {self.id} | {len(self.ops)} Ops | R:{len(self.reads)} W:{len(self.writes)}>"
