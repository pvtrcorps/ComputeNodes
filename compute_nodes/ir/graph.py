from typing import List, Optional, Dict, Any, Set
from enum import Enum, auto
from dataclasses import dataclass, field

from .types import DataType
from .ops import OpCode, infer_binary_type
from .resources import ResourceDesc, ResourceType


def _trace_resource_index(val: 'Value') -> Optional[int]:
    """
    Trace back through SSA origin chain to find the underlying resource index.
    
    Handles values from PASS_LOOP_END (pong buffers) and PASS_LOOP_READ (ping buffers).
    """
    if val is None:
        return None
    
    # Direct resource reference
    if hasattr(val, 'resource_index') and val.resource_index is not None:
        return val.resource_index
    
    # Trace through origin
    if val.origin is not None:
        op = val.origin
        
        # PASS_LOOP_END: Output corresponds to state variables with pong buffer
        if op.opcode == OpCode.PASS_LOOP_END:
            metadata = getattr(op, 'metadata', {})
            state_vars = metadata.get('state_vars', [])
            
            # Find which output index this value is
            for i, out_val in enumerate(op.outputs):
                if out_val is val and i < len(state_vars):
                    state = state_vars[i]
                    state = state_vars[i]
                    # Return pong_idx (output buffer for loop)
                    # Handle both dict (legacy) and StateVar object
                    pong_idx = state.get('pong_idx') if isinstance(state, dict) else getattr(state, 'pong_idx', None)
                    if pong_idx is not None:
                        return pong_idx
                    
                    ping_idx = state.get('ping_idx') if isinstance(state, dict) else getattr(state, 'ping_idx', None)
                    if ping_idx is not None:
                        return ping_idx
                    break
            
            # Fallback: trace through inputs
            for inp in op.inputs:
                res_idx = _trace_resource_index(inp)
                if res_idx is not None:
                    return res_idx
        
        # PASS_LOOP_READ: Get from output's resource_index or metadata
        elif op.opcode == OpCode.PASS_LOOP_READ:
            if op.outputs and op.outputs[0].resource_index is not None:
                return op.outputs[0].resource_index
        
        # Other ops: trace through HANDLE inputs
        elif op.inputs:
            for inp in op.inputs:
                if hasattr(inp, 'type') and inp.type == DataType.HANDLE:
                    res_idx = _trace_resource_index(inp)
                    if res_idx is not None:
                        return res_idx
    
    return None

class ValueKind(Enum):
    SSA = auto()      # Produced by an Op
    CONSTANT = auto() # Literal constant
    ARGUMENT = auto() # Function argument (Uniform, Resource)
    BUILTIN = auto()  # Intrinsic (e.g. GlobalInvocationID)

class Value:
    """
    Representation of a typed value in the SSA graph.
    Has a unique ID and a stable identity.
    """
    def __init__(self, id: int, kind: ValueKind, type: DataType, origin: Optional['Op'] = None, name_hint: str = "", resource_index: Optional[int] = None):
        self.id = id
        self.kind = kind
        self.type = type
        # For SSA values, origin is the Op that produced this value.
        self.origin = origin 
        self.users: List['Op'] = []
        self.name_hint = name_hint
        # For ARGUMENT, stores index in Graph.resources
        self.resource_index = resource_index
        
    def __repr__(self):
        return f"%{self.id}"

class Op:
    """
    Data-driven Operation.
    """
    def __init__(self, opcode: OpCode, inputs: List[Value], attrs: Optional[Dict[str, Any]] = None):
        self.opcode = opcode
        self.inputs = inputs
        self.attrs = attrs or {}
        
        # Output is determined during construction (usually single output for SSA)
        self.outputs: List[Value] = []
        
        # Side effects?
        self.side_effects = False
        if opcode in {OpCode.IMAGE_STORE, OpCode.BUFFER_WRITE}:
            self.side_effects = True

        # Register usage
        for val in inputs:
            val.users.append(self)

    def add_output(self, val: Value):
        self.outputs.append(val)

    def writes_resources(self) -> List[int]:
        """Returns list of resource indices written by this op."""
        if self.opcode == OpCode.IMAGE_STORE:
            # imageStore(img, coord, val) -> input[0] is access target
            img_val = self.inputs[0]
            if img_val.kind == ValueKind.ARGUMENT and img_val.resource_index is not None:
                return [img_val.resource_index]
        elif self.opcode == OpCode.BUFFER_WRITE:
             buf_val = self.inputs[0]
             if buf_val.kind == ValueKind.ARGUMENT and buf_val.resource_index is not None:
                return [buf_val.resource_index]
        elif self.opcode == OpCode.BLUR:
            # BLUR writes to output resource stored in op.metadata or outputs
            if self.outputs and self.outputs[0].resource_index is not None:
                return [self.outputs[0].resource_index]
        return []

    def reads_resources(self) -> List[int]:
        """Returns list of resource indices read by this op."""
        indices = []
        if self.opcode in {OpCode.IMAGE_LOAD, OpCode.SAMPLE, OpCode.IMAGE_SIZE}:
            img_val = self.inputs[0]
            # Check both ARGUMENT and SSA values with resource_index
            res_idx = img_val.resource_index
            
            # If resource_index is None, trace through origin chain
            # This handles PASS_LOOP_END outputs that reference ping-pong buffers
            if res_idx is None and img_val.origin is not None:
                res_idx = _trace_resource_index(img_val)
            
            if res_idx is not None:
                indices.append(res_idx)
        elif self.opcode == OpCode.BUFFER_READ:
             buf_val = self.inputs[0]
             if buf_val.resource_index is not None:
                indices.append(buf_val.resource_index)
        elif self.opcode == OpCode.IMAGE_STORE:
            # Check if we are storing FROM a resource (copy)
            if len(self.inputs) > 2:
                data_val = self.inputs[2]
                if data_val.resource_index is not None:
                     indices.append(data_val.resource_index)
        elif self.opcode == OpCode.BLUR:
            # BLUR reads from input resource
            if self.inputs and self.inputs[0].resource_index is not None:
                indices.append(self.inputs[0].resource_index)
        return indices


    def __repr__(self):
        return f"Op({self.opcode.name})"

class Block:
    def __init__(self, name: str = "block"):
        self.name = name
        self.ops: List[Op] = []
    
    def append(self, op: Op):
        self.ops.append(op)

class Graph:
    def __init__(self, name: str = "main"):
        self.name = name
        self.blocks: List[Block] = [Block("entry")]
        self.resources: List[ResourceDesc] = []
        # optimization: map desc -> index for O(1) lookup
        self._resource_map: Dict[ResourceDesc, int] = {} 
        # Arguments to the kernel (uniforms, resources mapped to args)
        self.arguments: List[Value] = []

class IRBuilder:
    """
    Helper to construct the IR Graph while maintaining invariants.
    """
    def __init__(self, graph: Graph):
        self.graph = graph
        self.active_block = graph.blocks[0]
        self._next_value_id = 0

    def _new_value(self, kind: ValueKind, type: DataType, origin: Op = None, name_hint: str = "", resource_index: Optional[int] = None) -> Value:
        val = Value(self._next_value_id, kind, type, origin, name_hint, resource_index)
        self._next_value_id += 1
        return val

    def add_resource(self, desc: ResourceDesc) -> Value:
        """Adds a resource to the graph and returns an Argument Value referencing it."""
        if desc in self.graph._resource_map:
            idx = self.graph._resource_map[desc]
            # Refinement: Reuse existing argument value if possible to avoid duplication.
            # We iterate graph.arguments to find one pointing to this index.
            # optimization: we could maintain a map idx->Value but iteration is okay for MVP size.
            for arg in self.graph.arguments:
                if arg.resource_index == idx:
                    return arg
        else:
            idx = len(self.graph.resources)
            self.graph.resources.append(desc)
            # Ensure unique internal map
            self.graph._resource_map[desc] = idx
            
        val = self._new_value(ValueKind.ARGUMENT, type=DataType.HANDLE, name_hint=desc.name)
        val.resource_index = idx
        # We need to link this value to the resource desc.
        # In a real compiler, this is an Argument linked to index i.
        self.graph.arguments.append(val)
        return val

    def add_op(self, opcode: OpCode, inputs: List[Value], attrs: Dict[str, Any] = None) -> Op:
        op = Op(opcode, inputs, attrs)
        self.active_block.append(op)
        return op

    def binary(self, opcode: OpCode, a: Value, b: Value) -> Value:
        out_type = infer_binary_type(opcode, a.type, b.type)
        op = self.add_op(opcode, [a, b])
        out = self._new_value(ValueKind.SSA, out_type, origin=op)
        op.add_output(out)
        return out

    # Helpers for specific ops
    def add(self, a: Value, b: Value): return self.binary(OpCode.ADD, a, b)
    def mul(self, a: Value, b: Value): return self.binary(OpCode.MUL, a, b)
    
    def constant(self, val: Any, type: DataType) -> Value:
        # Unified Constant handling: Always an Op
        op = self.add_op(OpCode.CONSTANT, [], attrs={'value': val})
        v = self._new_value(ValueKind.SSA, type, origin=op)
        # Optional: tag as CONSTANT kind too, or just rely on Op?
        # User convention: "Const como Op". ValueKind.CONSTANT can be a label.
        v.kind = ValueKind.CONSTANT 
        op.add_output(v)
        return v

    def builtin(self, name: str, type: DataType) -> Value:
        """Creates a BUILTIN value (e.g. gl_GlobalInvocationID)."""
        op = self.add_op(OpCode.BUILTIN, [], attrs={'name': name})
        v = self._new_value(ValueKind.BUILTIN, type, origin=op, name_hint=name)
        op.add_output(v)
        return v

    def swizzle(self, val: Value, mask: str) -> Value:
        """Creates a SWIZZLE op."""
        # TODO: infer type size from mask length
        # For now MVP: assume UVEC2 if mask length 2, float if 1, etc.
        # This inference logic should be centralized but kept simple here.
        new_len = len(mask)
        base_type = val.type # e.g. UVEC3
        # Infer result type (very basic)
        if hasattr(base_type, 'name') and 'UVEC' in base_type.name:
            res_type = getattr(DataType, f"UVEC{new_len}") if new_len > 1 else DataType.UINT
        elif hasattr(base_type, 'name') and 'IVEC' in base_type.name:
            res_type = getattr(DataType, f"IVEC{new_len}") if new_len > 1 else DataType.INT
        else:
            # Fallback for floats
            res_type = getattr(DataType, f"VEC{new_len}") if new_len > 1 else DataType.FLOAT
            
        op = self.add_op(OpCode.SWIZZLE, [val], attrs={'mask': mask})
        v = self._new_value(ValueKind.SSA, res_type, origin=op)
        op.add_output(v)
        return v

    def cast(self, val: Value, target_type: DataType) -> Value:
        """Creates a CAST op."""
        # If type matches, return as is? Or explicit no-op?
        if val.type == target_type:
            return val
        
        # We need an explicit OpCode for CAST or use Unary? 
        # Using separate CAST OpCode would be cleaner.
        # Check if OpCode.CAST exists, if not assume we need to add it or use equivalent.
        # For now assuming OpCode.GK_CAST or similar doesn't exist, we added it?
        # Let's check ops.py... wait, we didn't add CAST yet.
        # We should use a placeholder or define it. 
        # Assuming we add OpCode.CAST to types/ops.
        op = self.add_op(OpCode.CAST, [val], attrs={'type': target_type.name})
        v = self._new_value(ValueKind.SSA, target_type, origin=op)
        op.add_output(v)
        return v

    def image_store(self, image: Value, coord: Value, data: Value):
        # Validation: coord should be IVEC2 for 2D images
        # We can auto-cast here or assume caller did it.
        # The user requested strict casting so we might enforcing it here is good.
        self.add_op(OpCode.IMAGE_STORE, [image, coord, data])

    def image_size(self, image: Value) -> Value:
        op = self.add_op(OpCode.IMAGE_SIZE, [image])
        # imageSize returns ivec3 for consistent handling of 2D and 3D images
        # For 2D: returns (width, height, 1)
        # For 3D: returns (width, height, depth)
        v = self._new_value(ValueKind.SSA, DataType.IVEC3, origin=op)
        op.add_output(v)
        return v
    
    def image_load(self, image: Value, coord: Value) -> Value:
        # imageLoad(img, ivec2) -> vec4
        op = self.add_op(OpCode.IMAGE_LOAD, [image, coord])
        v = self._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
        op.add_output(v)
        return v
    
    def div(self, a: Value, b: Value) -> Value:
        """Division helper."""
        return self.binary(OpCode.DIV, a, b)
    
    def sample(self, sampler: Value, coord: Value) -> Value:
        """Texture sampling (texture(sampler, uv))."""
        op = self.add_op(OpCode.SAMPLE, [sampler, coord])
        v = self._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
        op.add_output(v)
        return v
    
    def emit(self, opcode: OpCode, inputs: List[Value], result_type: DataType) -> Value:
        """
        Generic emit for any operation with a single output.
        
        Args:
            opcode: The operation code
            inputs: List of input values
            result_type: The type of the result value
            
        Returns:
            The output Value
        """
        op = self.add_op(opcode, inputs)
        v = self._new_value(ValueKind.SSA, result_type, origin=op)
        op.add_output(v)
        return v

