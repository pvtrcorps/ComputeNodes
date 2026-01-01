# Grid Field Context Utility
# Provides context propagation for nodes that operate on grids with field inputs
#
# When a node operates on a grid (e.g., Sample, Blur, Distort) and has field inputs
# (e.g., Coordinate, Radius, Offset), those field inputs need to know the dimensions
# of the grid they're operating on, not the downstream dispatch context.

from contextlib import contextmanager
from typing import Any, Dict, Optional


@contextmanager
def grid_field_context(ctx: Any, grid_value: Any):
    """
    Context manager that pushes grid context for field input processing.
    
    Usage:
        val_grid = get_socket_value(node.inputs[0])  # Grid input
        
        with grid_field_context(ctx, val_grid):
            val_field = get_socket_value(node.inputs[1])  # Field input
        # Position nodes in val_field's upstream will use grid's dimensions
    
    Args:
        ctx: The handler context dict
        grid_value: The Value representing the grid resource
    
    Yields:
        The context dict with sample_grid_context set (or unchanged if no grid)
    """
    if grid_value is None:
        yield ctx
        return
    
    resource_index = getattr(grid_value, 'resource_index', None)
    if resource_index is None:
        yield ctx
        return
    
    # Handle NodeContext object vs dict
    if hasattr(ctx, 'graph'):
        graph = ctx.graph
        storage = ctx.extra
    else:
        graph = ctx.get('graph')
        storage = ctx
    
    if graph is None or resource_index >= len(graph.resources):
        yield ctx
        return
    
    resource = graph.resources[resource_index]
    dimensions = getattr(resource, 'dimensions', 2)
    size = getattr(resource, 'size', None)
    
    # Save old context
    old_context = storage.get('sample_grid_context')
    
    # Push new context
    storage['sample_grid_context'] = {
        'dimensions': dimensions,  # 1, 2, or 3
        'size': size,              # (w,) or (w,h) or (w,h,d)
    }
    
    try:
        yield ctx
    finally:
        # Restore old context
        storage['sample_grid_context'] = old_context


def get_grid_dimensions(ctx: Any, grid_value: Any) -> tuple:
    """
    Get dimensions and size from a grid value.
    
    Returns:
        Tuple of (dimensions: int, size: tuple or None)
    """
    if grid_value is None:
        return (2, None)
    
    resource_index = getattr(grid_value, 'resource_index', None)
    if resource_index is None:
        return (2, None)
    
    # Handle NodeContext object vs dict
    if hasattr(ctx, 'graph'):
        graph = ctx.graph
    else:
        graph = ctx.get('graph')
    
    if graph is None or resource_index >= len(graph.resources):
        return (2, None)
    
    resource = graph.resources[resource_index]
    dimensions = getattr(resource, 'dimensions', 2)
    size = getattr(resource, 'size', None)
    
    return (dimensions, size)
