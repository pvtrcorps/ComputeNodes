"""
ExecutionState - Runtime state container for compute graph execution.

This module provides the central state management for phased execution,
tracking resource sizes, loop context, and future simulation state.

Key Concepts:
- ExecutionState: Mutable runtime state updated as execution proceeds
- ResourceLifetime: Enum classifying when resources can be allocated
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Tuple, Optional, Any

logger = logging.getLogger(__name__)


class ResourceLifetime(Enum):
    """
    Classifies when a resource can be allocated.
    
    Used by PhasedResourceResolver to determine allocation timing.
    """
    
    STATIC = "static"
    """Resource size is known at compile time. Allocated in Phase 0."""
    
    AFTER_LOOP = "after_loop"
    """Resource depends on loop output. Allocated after loops execute."""
    
    ON_DEMAND = "on_demand"
    """Resource allocated lazily when first referenced."""


@dataclass
class ExecutionState:
    """
    Runtime state for current execution context.
    
    This is the central state container that tracks:
    - Current sizes of all resources (updated as execution proceeds)
    - Loop iteration context
    - Future: Simulation frame context
    
    The state is passed to ScalarEvaluator for runtime size calculations
    and updated by LoopExecutor after loops complete.
    
    Example:
        state = ExecutionState(context_width=1024, context_height=1024)
        
        # Resolve static resources
        resolver.resolve_static(graph, state)
        
        # Execute loop - updates state.resource_sizes
        loop_executor.execute(graph, loop, state)
        
        # Now state.get_size(loop_output_idx) returns correct post-loop size
        resolver.resolve_pending(graph, state)
    """
    
    # Current sizes of all resources (updated as execution proceeds)
    # Maps resource_index -> (width, height, depth)
    resource_sizes: Dict[int, Tuple[int, int, int]] = field(default_factory=dict)
    
    # Loop context (updated per iteration)
    current_iteration: int = 0
    total_iterations: int = 1
    
    # Context dimensions (default for unspecified resources)
    context_width: int = 512
    context_height: int = 512
    context_depth: int = 1
    
    # Simulation context (future)
    current_frame: int = 0
    delta_time: float = 0.0
    elapsed_time: float = 0.0
    
    # Resource allocation tracking
    # Maps resource_index -> ResourceLifetime
    _lifetimes: Dict[int, ResourceLifetime] = field(default_factory=dict)
    
    # Pending resources (not yet allocated)
    # Maps resource_index -> True if pending
    _pending: Dict[int, bool] = field(default_factory=dict)
    
    def get_size(self, resource_idx: int) -> Tuple[int, int, int]:
        """
        Get current size of a resource.
        
        If resource hasn't been allocated yet, returns context dimensions.
        
        Args:
            resource_idx: Index of resource in graph.resources
            
        Returns:
            Tuple of (width, height, depth)
        """
        if resource_idx in self.resource_sizes:
            return self.resource_sizes[resource_idx]
        return (self.context_width, self.context_height, self.context_depth)
    
    def update_size(self, resource_idx: int, width: int, height: int, depth: int = 1):
        """
        Update resource size after allocation or resize.
        
        Called by ResourceResolver after allocating a texture,
        and by LoopExecutor after dynamic resizes.
        
        Args:
            resource_idx: Index of resource in graph.resources
            width: New width
            height: New height
            depth: New depth (default 1 for 2D)
        """
        self.resource_sizes[resource_idx] = (width, height, depth)
        logger.debug(f"ExecutionState: resource[{resource_idx}] size updated to {width}x{height}x{depth}")
    
    def set_lifetime(self, resource_idx: int, lifetime: ResourceLifetime):
        """
        Set the lifetime classification for a resource.
        
        Args:
            resource_idx: Index of resource
            lifetime: When the resource can be allocated
        """
        self._lifetimes[resource_idx] = lifetime
        if lifetime != ResourceLifetime.STATIC:
            self._pending[resource_idx] = True
    
    def get_lifetime(self, resource_idx: int) -> ResourceLifetime:
        """Get lifetime classification for a resource."""
        return self._lifetimes.get(resource_idx, ResourceLifetime.STATIC)
    
    def is_pending(self, resource_idx: int) -> bool:
        """Check if resource is pending allocation."""
        return self._pending.get(resource_idx, False)
    
    def mark_allocated(self, resource_idx: int):
        """Mark resource as allocated (no longer pending)."""
        self._pending.pop(resource_idx, None)
    
    def get_pending_resources(self) -> list:
        """Get list of resource indices that are pending allocation."""
        return [idx for idx, pending in self._pending.items() if pending]
    
    def set_loop_context(self, iteration: int, total: int):
        """
        Update loop iteration context.
        
        Called by LoopExecutor at the start of each iteration.
        """
        self.current_iteration = iteration
        self.total_iterations = total
    
    def set_simulation_context(self, frame: int, delta_time: float, elapsed_time: float):
        """
        Update simulation frame context.
        
        Called by (future) SimulationExecutor at each frame.
        """
        self.current_frame = frame
        self.delta_time = delta_time
        self.elapsed_time = elapsed_time
    
    def reset(self):
        """Reset state for new execution (preserves context dimensions)."""
        self.resource_sizes.clear()
        self.current_iteration = 0
        self.total_iterations = 1
        self._lifetimes.clear()
        self._pending.clear()
    
    def copy(self) -> 'ExecutionState':
        """Create a shallow copy of state (for nested loops)."""
        return ExecutionState(
            resource_sizes=self.resource_sizes.copy(),
            current_iteration=self.current_iteration,
            total_iterations=self.total_iterations,
            context_width=self.context_width,
            context_height=self.context_height,
            context_depth=self.context_depth,
            current_frame=self.current_frame,
            delta_time=self.delta_time,
            elapsed_time=self.elapsed_time,
            _lifetimes=self._lifetimes.copy(),
            _pending=self._pending.copy(),
        )
    
    def to_eval_context(self) -> dict:
        """
        Convert to dict format expected by ScalarEvaluator.EvalContext.
        
        This bridges the new ExecutionState to the existing ScalarEvaluator.
        """
        return {
            'iteration': self.current_iteration,
            'context_width': self.context_width,
            'context_height': self.context_height,
            'context_depth': self.context_depth,
            'grid_sizes': self.resource_sizes.copy(),
        }
