"""
Loops module - Unified handling of Repeat Zones.

This module consolidates all loop-related functionality:
- PassLoop, StateVar structures (planning)
- LoopExecutor (runtime)
- Buffer management (ping-pong)

The module provides clean imports for external use:
    from compute_nodes.loops import PassLoop, LoopExecutor, StateVar
"""

# Re-export main classes for convenient imports
from ..planner.loops import PassLoop, find_loop_regions, wrap_passes_in_loops
from ..ir.state import StateVar
from ..runtime.loop_executor import LoopExecutor

__all__ = [
    'PassLoop',
    'StateVar',
    'LoopExecutor',
    'find_loop_regions',
    'wrap_passes_in_loops',
]
