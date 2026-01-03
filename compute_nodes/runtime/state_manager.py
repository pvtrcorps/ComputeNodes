# StateManager - Loop State Buffer Management
#
# Clean abstraction for managing ping-pong buffers in multi-pass loops.
# Supports:
# - Multi-resolution cascades (resolution changes between iterations)
# - Nested loops (stack-based context)
# - Future Field support (architecture-ready)

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import logging
import gpu

logger = logging.getLogger(__name__)


@dataclass
class LoopStateBuffer:
    """
    Represents a single state variable's buffer pair in a loop.
    
    Manages ping-pong double-buffering for GPU compute iterations.
    """
    name: str
    state_index: int
    
    # Buffer pair
    ping: Any = None  # GPUTexture
    pong: Any = None  # GPUTexture
    
    # Current dimensions (may change between iterations for multi-resolution)
    width: int = 0
    height: int = 0
    depth: int = 1
    dimensions: int = 2  # 2D or 3D
    
    # Texture format (e.g., 'RGBA32F')
    format: str = 'RGBA32F'
    
    # Track which buffer is currently "read" vs "write"
    # Even iterations: read=ping, write=pong
    # Odd iterations: read=pong, write=ping
    current_iteration: int = 0
    
    @property
    def read_buffer(self) -> Any:
        """Get the current read buffer (based on iteration parity)."""
        return self.ping if self.current_iteration % 2 == 0 else self.pong
    
    @property
    def write_buffer(self) -> Any:
        """Get the current write buffer (based on iteration parity)."""
        return self.pong if self.current_iteration % 2 == 0 else self.ping
    
    @property
    def read_size(self) -> Tuple[int, int, int]:
        """Get dimensions of read buffer."""
        buf = self.read_buffer
        if buf:
            return (buf.width, buf.height, getattr(buf, 'depth', 1))
        return (self.width, self.height, self.depth)
    
    @property
    def write_size(self) -> Tuple[int, int, int]:
        """Get dimensions of write buffer."""
        buf = self.write_buffer
        if buf:
            return (buf.width, buf.height, getattr(buf, 'depth', 1))
        return (self.width, self.height, self.depth)


@dataclass
class LoopContext:
    """
    Context for a single loop execution.
    
    Tracks state buffers, iteration count, and provides clean access
    to read/write buffers and their dimensions.
    """
    loop_id: str
    iterations: int
    current_iteration: int = 0
    
    # State buffers indexed by state_index
    state_buffers: Dict[int, LoopStateBuffer] = field(default_factory=dict)
    
    # For nested loops: parent context
    parent: Optional['LoopContext'] = None
    
    # Nesting depth (0 = outermost)
    depth: int = 0
    
    def get_state(self, state_index: int) -> Optional[LoopStateBuffer]:
        """Get state buffer by index."""
        return self.state_buffers.get(state_index)
    
    def advance_iteration(self):
        """Advance to next iteration, updating all state buffers."""
        self.current_iteration += 1
        for state in self.state_buffers.values():
            state.current_iteration = self.current_iteration


class StateManager:
    """
    Manages loop state across multi-pass GPU compute iterations.
    
    Key responsibilities:
    - Allocate and manage ping-pong buffer pairs
    - Track read/write buffer assignments per iteration
    - Handle multi-resolution (resizing buffers between iterations)
    - Support nested loops via context stack
    
    Usage:
        mgr = StateManager(texture_manager)
        
        # Start a loop
        ctx = mgr.begin_loop("loop_0", iterations=10, state_vars=[...])
        
        for i in range(10):
            # Get buffers for this iteration
            read_buf = mgr.get_read_buffer(0)  # state index 0
            write_buf = mgr.get_write_buffer(0)
            
            # Get dimensions for shader uniforms
            read_size = mgr.get_read_size(0)
            write_size = mgr.get_write_size(0)
            
            # Execute passes...
            
            # Advance to next iteration (swaps ping-pong)
            mgr.advance_iteration()
        
        # End loop, get final output buffers
        final_buffers = mgr.end_loop()
    """
    
    def __init__(self, texture_manager):
        self.texture_manager = texture_manager
        
        # Stack of active loop contexts (for nested loops)
        self._context_stack: List[LoopContext] = []
        
        # Resource index -> state buffer mapping for active loop
        self._resource_to_state: Dict[int, Tuple[int, int]] = {}  # res_idx -> (loop_depth, state_idx)
    
    @property
    def current_context(self) -> Optional[LoopContext]:
        """Get the current (innermost) loop context."""
        return self._context_stack[-1] if self._context_stack else None
    
    @property
    def depth(self) -> int:
        """Current nesting depth (0 = no active loop)."""
        return len(self._context_stack)
    
    def begin_loop(self, loop_id: str, iterations: int, 
                   state_vars: List[Any], texture_map: Dict[int, Any]) -> LoopContext:
        """
        Begin a new loop, creating state buffers for all state variables.
        
        Args:
            loop_id: Unique identifier for this loop
            iterations: Number of iterations
            state_vars: List of StateVar objects from planner
            texture_map: Current texture map for initializing buffers
            
        Returns:
            New LoopContext for this loop
        """
        parent = self.current_context
        depth = len(self._context_stack)
        
        ctx = LoopContext(
            loop_id=loop_id,
            iterations=iterations,
            parent=parent,
            depth=depth
        )
        
        # Create state buffers
        for state in state_vars:
            if not state.is_grid:
                continue  # Skip non-Grid states (future Field support)
            
            # Get initial buffer info
            ping_idx = state.ping_idx
            pong_idx = state.pong_idx
            
            if ping_idx is None or pong_idx is None:
                logger.warning(f"State '{state.name}' missing ping/pong indices")
                continue
            
            # Get or create textures
            ping_tex = texture_map.get(ping_idx)
            pong_tex = texture_map.get(pong_idx)
            
            # Get dimensions from existing buffers or state
            if ping_tex:
                width, height = ping_tex.width, ping_tex.height
                depth = getattr(ping_tex, 'depth', 1)
            else:
                width = state.size[0] if len(state.size) > 0 else 512
                height = state.size[1] if len(state.size) > 1 else 512
                depth = state.size[2] if len(state.size) > 2 else 1
            
            state_buffer = LoopStateBuffer(
                name=state.name,
                state_index=state.index,
                ping=ping_tex,
                pong=pong_tex,
                width=width,
                height=height,
                depth=depth,
                dimensions=state.dimensions,
                format=getattr(state, 'format', 'RGBA32F'),
                current_iteration=0
            )
            
            ctx.state_buffers[state.index] = state_buffer
            
            # Register resource mappings
            self._resource_to_state[ping_idx] = (depth, state.index)
            self._resource_to_state[pong_idx] = (depth, state.index)
            
            logger.debug(f"Loop '{loop_id}' state '{state.name}': "
                        f"{width}x{height}x{depth} ({state_buffer.format})")
        
        self._context_stack.append(ctx)
        logger.info(f"Begin loop '{loop_id}': {iterations} iterations, "
                   f"{len(ctx.state_buffers)} state vars, depth={depth}")
        
        return ctx
    
    def end_loop(self) -> Dict[int, Any]:
        """
        End the current loop, returning final output buffers.
        
        Returns:
            Dict mapping state_index -> final texture
        """
        if not self._context_stack:
            logger.warning("end_loop called with no active loop")
            return {}
        
        ctx = self._context_stack.pop()
        
        # Determine final buffers (last written = write buffer after last iteration)
        final_buffers = {}
        for state_idx, state_buf in ctx.state_buffers.items():
            # After N iterations, if N is odd, result is in pong (last write target)
            # If N is even and we started at 0, we never wrote (edge case)
            # Actually: after iteration i, we've done i+1 iterations
            # The state's current_iteration is already advanced
            final_buffers[state_idx] = state_buf.write_buffer
        
        # Clean up resource mappings for this loop
        to_remove = [k for k, v in self._resource_to_state.items() if v[0] == ctx.depth]
        for k in to_remove:
            del self._resource_to_state[k]
        
        logger.info(f"End loop '{ctx.loop_id}': completed {ctx.current_iteration} iterations")
        
        return final_buffers
    
    def advance_iteration(self):
        """Advance current loop to next iteration (ping-pong swap)."""
        ctx = self.current_context
        if ctx:
            ctx.advance_iteration()
            logger.debug(f"Loop '{ctx.loop_id}' iteration -> {ctx.current_iteration}")
    
    def get_read_buffer(self, state_index: int) -> Optional[Any]:
        """Get current read buffer for a state variable."""
        ctx = self.current_context
        if not ctx:
            return None
        state = ctx.get_state(state_index)
        return state.read_buffer if state else None
    
    def get_write_buffer(self, state_index: int) -> Optional[Any]:
        """Get current write buffer for a state variable."""
        ctx = self.current_context
        if not ctx:
            return None
        state = ctx.get_state(state_index)
        return state.write_buffer if state else None
    
    def get_read_size(self, state_index: int) -> Tuple[int, int, int]:
        """Get dimensions of current read buffer."""
        ctx = self.current_context
        if not ctx:
            return (0, 0, 1)
        state = ctx.get_state(state_index)
        return state.read_size if state else (0, 0, 1)
    
    def get_write_size(self, state_index: int) -> Tuple[int, int, int]:
        """Get dimensions of current write buffer."""
        ctx = self.current_context
        if not ctx:
            return (0, 0, 1)
        state = ctx.get_state(state_index)
        return state.write_size if state else (0, 0, 1)
    
    def get_current_iteration(self) -> int:
        """Get current iteration index of innermost loop."""
        ctx = self.current_context
        return ctx.current_iteration if ctx else 0
    
    def resize_state(self, state_index: int, new_size: Tuple[int, int, int]):
        """
        Resize a state's write buffer for multi-resolution support.
        
        This is called when a Resize node inside a loop changes the output size.
        The new buffer will be used for writing in the current iteration.
        
        Args:
            state_index: Index of state to resize
            new_size: New (width, height, depth) dimensions
        """
        ctx = self.current_context
        if not ctx:
            logger.warning("resize_state called with no active loop")
            return
        
        state = ctx.get_state(state_index)
        if not state:
            logger.warning(f"resize_state: state {state_index} not found")
            return
        
        current_size = state.write_size
        if current_size == new_size:
            return  # No change needed
        
        logger.info(f"Resizing state '{state.name}': {current_size} -> {new_size}")
        
        # Create new buffer at new size
        new_tex = self.texture_manager.create_storage_texture(
            name=f"loop_resize_{state.name}_{ctx.current_iteration}",
            width=new_size[0],
            height=new_size[1],
            format=state.format
        )
        
        # Replace the current write buffer
        if ctx.current_iteration % 2 == 0:
            state.pong = new_tex
        else:
            state.ping = new_tex
        
        # Update tracked dimensions
        state.width = new_size[0]
        state.height = new_size[1]
        state.depth = new_size[2]
    
    def is_loop_resource(self, resource_index: int) -> bool:
        """Check if a resource index belongs to a loop state buffer."""
        return resource_index in self._resource_to_state
    
    def get_loop_resource_info(self, resource_index: int) -> Optional[Tuple[int, int]]:
        """
        Get loop info for a resource index.
        
        Returns:
            (loop_depth, state_index) if resource is a loop buffer, else None
        """
        return self._resource_to_state.get(resource_index)
    
    def update_texture_map(self, texture_map: Dict[int, Any]):
        """
        Update a texture_map with current read/write buffer assignments.
        
        This should be called before each pass execution to ensure
        the correct buffers are bound.
        """
        ctx = self.current_context
        if not ctx:
            return
        
        for state_idx, state in ctx.state_buffers.items():
            # Find ping/pong resource indices
            # These were stored when we created the state buffer
            for res_idx, (loop_depth, idx) in self._resource_to_state.items():
                if loop_depth == ctx.depth and idx == state_idx:
                    # Determine if this is ping or pong based on context
                    # This is a bit indirect - we should track this better
                    pass
            
            # For now, rely on StateVar having ping_idx/pong_idx attributes
            # This will be improved when we integrate with the full system
