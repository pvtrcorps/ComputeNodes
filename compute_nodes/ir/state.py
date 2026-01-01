from dataclasses import dataclass
from typing import Optional, Any, Tuple

@dataclass
class StateVar:
    """
    A state variable in a loop with ping-pong buffering.
    
    Shared between Graph Extraction (repeat.py) and Planner (loops.py).
    """
    name: str
    index: int
    is_grid: bool
    data_type: Any  # DataType enum
    
    # Unified socket name (used by new repeat system)
    socket_name: Optional[str] = None
    
    # For Grid types: ping-pong buffer indices
    ping_idx: Optional[int] = None
    pong_idx: Optional[int] = None
    
    # Initial value reference
    initial_value: Any = None
    
    # Current size for Grid types
    size: Tuple[int, int, int] = (0, 0, 0)
    dimensions: int = 2
    
    # Texture format (inherited from source, defaults to RGBA32F)
    format: str = 'RGBA32F'
    
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
