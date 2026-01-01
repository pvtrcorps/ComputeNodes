from typing import Any, Dict, Optional, Set, Callable
from ..ir.graph import Graph, Value, Op
from ..ir.types import DataType

class ShaderContext:
    """
    Context object passed to GLSL emitters.
    Wraps the state required to generate GLSL for a specific operation.
    """
    def __init__(self, 
                 generator: Any,  # ShaderGenerator instance
                 op: Op,
                 lhs: str,
                 dispatch_info: Dict[str, Any]):
        self._generator = generator
        self.op = op
        self.lhs = lhs
        self._dispatch_info = dispatch_info
        
    def param(self, val: Value) -> str:
        """Resolve a Value to its GLSL string representation (e.g., 'v1', 'img_0')."""
        return self._generator._param(val)
        
    def type_str(self, dtype: DataType) -> str:
        """Resolve a DataType to its GLSL type string (e.g., 'vec3', 'float')."""
        return self._generator._type_str(dtype)
        
    @property
    def graph(self) -> Graph:
        return self._generator.graph
        
    @property
    def dispatch_size(self):
        return self._dispatch_info.get('dispatch_size', (512, 512, 1))

    @property
    def op_ids(self) -> Set[int]:
        return self._dispatch_info.get('op_ids', set())

    @property
    def reads_idx(self) -> Set[int]:
        return self._dispatch_info.get('reads_idx', set())

    @property
    def writes_idx(self) -> Set[int]:
        return self._dispatch_info.get('writes_idx', set())

    @property
    def binding_map(self) -> Dict[int, int]:
        return self._dispatch_info.get('binding_map', {})

    # Backward compatibility removed - Use strict API

