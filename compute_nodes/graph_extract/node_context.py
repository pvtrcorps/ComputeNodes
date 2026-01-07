from typing import Any, Optional, Tuple, Dict, Callable
from ..ir.graph import Value, ValueKind
from ..ir.types import DataType
from ..ir.ops import OpCode

class NodeContext:
    """
    Context object passed to node handlers during graph extraction.
    Provides standardized access to inputs, outputs, and the IR builder.
    """
    def __init__(self, 
                 builder: Any, 
                 node: Any,
                 socket_value_map: Dict[int, Value],
                 get_socket_key: Callable[[Any], int],
                 get_socket_value: Callable[[Any], Optional[Value]],
                 extra_ctx: Dict[str, Any] = None):
        self.builder = builder
        self.node = node
        self._socket_value_map = socket_value_map
        self._get_socket_key = get_socket_key
        self._get_socket_value = get_socket_value
        self.extra = extra_ctx or {}

    def get_input(self, key_or_index: Any) -> Optional[Value]:
        """Get raw input Value from socket name or index."""
        if isinstance(key_or_index, int):
            if key_or_index >= len(self.node.inputs):
                return None
            socket = self.node.inputs[key_or_index]
        else:
            if key_or_index not in self.node.inputs:
                return None
            socket = self.node.inputs[key_or_index]
            
        return self._get_socket_value(socket)
        
    def input_float(self, key: Any, default: float = 0.0) -> Value:
        val = self.get_input(key)
        if val is None:
            return self.builder.constant(float(default), DataType.FLOAT)
        if val.type != DataType.FLOAT:
            return self.builder.cast(val, DataType.FLOAT)
        return val

    def input_int(self, key: Any, default: int = 0) -> Value:
        val = self.get_input(key)
        if val is None:
            return self.builder.constant(int(default), DataType.INT)
        if val.type != DataType.INT:
            return self.builder.cast(val, DataType.INT)
        return val

    def input_vec3(self, key: Any, default: Tuple[float, float, float] = (0.0, 0.0, 0.0)) -> Value:
        val = self.get_input(key)
        if val is None:
            return self.builder.constant(default, DataType.VEC3)
        if val.type != DataType.VEC3:
            return self.builder.cast(val, DataType.VEC3)
        return val
        
    def input_vec4(self, key: Any, default: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)) -> Value:
        val = self.get_input(key)
        if val is None:
            return self.builder.constant(default, DataType.VEC4)
        if val.type != DataType.VEC4:
            return self.builder.cast(val, DataType.VEC4)
        return val

    def set_output(self, key_or_index: Any, value: Value):
        """Set output Value for socket name or index."""
        if isinstance(key_or_index, int):
            if key_or_index >= len(self.node.outputs):
                return
            socket = self.node.outputs[key_or_index]
        else:
            if key_or_index not in self.node.outputs:
                return
            socket = self.node.outputs[key_or_index]
            
        key = self._get_socket_key(socket)
        self._socket_value_map[key] = value

    @property
    def graph(self):
        return self.builder.graph

    @property
    def loop_depth(self) -> int:
        """Get current loop nesting depth (0 = not in loop, 1+ = inside loop)."""
        extraction_state = self.extra.get('extraction_state', {})
        return extraction_state.get('loop_depth', 0)
    
    @property
    def in_loop_body(self) -> bool:
        """Check if currently processing nodes inside a loop body."""
        return self.loop_depth > 0
    
    def enter_loop(self):
        """Increment loop depth when entering a repeat zone body."""
        extraction_state = self.extra.get('extraction_state', {})
        extraction_state['loop_depth'] = extraction_state.get('loop_depth', 0) + 1
    
    def exit_loop(self):
        """Decrement loop depth when exiting a repeat zone body."""
        extraction_state = self.extra.get('extraction_state', {})
        extraction_state['loop_depth'] = max(0, extraction_state.get('loop_depth', 1) - 1)

    def error(self, message: str):
        """Raise a descriptive error associated with this node."""
        raise RuntimeError(f"Node Error [{self.node.name}]: {message}")

    def require_input(self, key_or_index: Any, expected_type: Optional[DataType] = None) -> Value:
        """
        Get input value, raising an error if it is not connected.
        Optionally validates the data type.
        """
        val = self.get_input(key_or_index)
        if val is None:
            # Try to get socket name for better error
            socket_name = str(key_or_index)
            if isinstance(key_or_index, int) and key_or_index < len(self.node.inputs):
                socket_name = self.node.inputs[key_or_index].name
            
            self.error(f"Input '{socket_name}' is required but not connected.")
            
        if expected_type and val.type != expected_type:
            # Allow auto-casting if compatible (captured in get_input usually, but let's be strict here if requested)
            # Actually, types might not match exactly due to casting, but lets check fundamental incompatibility
            # For now, simplistic check
             if expected_type == DataType.HANDLE and val.type != DataType.HANDLE:
                 self.error(f"Input '{key_or_index}' must be a Grid (Handle), got {val.type.name} (Field). Insert a Capture node?")
        
        return val

    def validate_type(self, value: Value, allowed_types: list[DataType], socket_name: str = "Input"):
        """Validate that a value is one of the allowed types."""
        if value.type not in allowed_types:
            type_names = [t.name for t in allowed_types]
            self.error(f"{socket_name} has invalid type {value.type.name}. Expected: {', '.join(type_names)}")
