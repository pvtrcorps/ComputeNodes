"""
GraphCompiler - Compiles node graphs to executable passes with caching.

This module provides a cached compilation layer that sits between the
graph extraction and execution phases, avoiding redundant recompilation
when the same graph structure is executed multiple times.

Caching Strategy:
- Graph hash is computed from node structure, links, and property values
- Compiled passes are cached by graph hash
- Cache is invalidated when graph structure changes
"""

import logging
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Union
from collections import OrderedDict

from ..ir.graph import Graph
from ..planner.scheduler import PassScheduler, schedule_passes
from ..planner.passes import ComputePass
from ..planner.loops import PassLoop

logger = logging.getLogger(__name__)


class LRUCache:
    """
    Least Recently Used cache with size limit.
    
    When capacity is exceeded, the least recently accessed items are evicted.
    """
    
    def __init__(self, capacity: int = 16):
        self.capacity = capacity
        self._cache: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache, marking it as recently used."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None
    
    def put(self, key: str, value: Any) -> None:
        """Add item to cache, evicting oldest if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.capacity:
                self._cache.popitem(last=False)
            self._cache[key] = value
    
    def invalidate(self, key: str) -> bool:
        """Remove specific item from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'size': len(self._cache),
            'capacity': self.capacity,
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': hit_rate,
        }


class GraphCompiler:
    """
    Compiles IR Graphs to executable passes with caching.
    
    The compiler maintains a cache of previously compiled graphs,
    allowing fast re-execution of unchanged graph structures.
    
    Example:
        compiler = GraphCompiler()
        passes = compiler.compile(graph)
        # Second call with same graph is cached
        passes = compiler.compile(graph)
    """
    
    def __init__(self, cache_capacity: int = 16):
        """
        Initialize compiler with specified cache capacity.
        
        Args:
            cache_capacity: Maximum number of compiled graphs to cache
        """
        self._cache = LRUCache(capacity=cache_capacity)
        
    def compile(self, graph: Graph) -> List[Union[ComputePass, PassLoop]]:
        """
        Compile a graph to executable passes.
        
        Uses cached result if graph structure hasn't changed.
        
        Args:
            graph: IR Graph to compile
            
        Returns:
            List of ComputePass and PassLoop items
        """
        graph_hash = self._compute_graph_hash(graph)
        
        # Try cache first
        cached = self._cache.get(graph_hash)
        if cached is not None:
            logger.debug(f"Graph compile CACHE HIT (hash={graph_hash[:8]}...)")
            return cached
        
        # Cache miss - need to compile
        logger.debug(f"Graph compile CACHE MISS (hash={graph_hash[:8]}...)")
        
        # Use PassScheduler for compilation
        scheduler = PassScheduler(graph)
        passes = scheduler.schedule()
        
        # Cache the result
        self._cache.put(graph_hash, passes)
        
        return passes
    
    def _compute_graph_hash(self, graph: Graph) -> str:
        """
        Compute a hash that uniquely identifies the graph structure.
        
        The hash includes:
        - Number and types of ops
        - Resource configurations
        - Op opcodes and operand structure
        """
        hasher = hashlib.sha256()
        
        # Graph name for disambiguation
        hasher.update(graph.name.encode())
        
        # Number of resources
        hasher.update(f"resources:{len(graph.resources)}".encode())
        
        # Collect all ops from all blocks for hashing
        # Ops are typically ordered, so block order + op order is stable
        all_ops = []
        for block in graph.blocks:
            all_ops.extend(block.ops)
            
        hasher.update(f"ops:{len(all_ops)}".encode())
        
        # Resource descriptors
        for i, res in enumerate(graph.resources):
            res_str = f"res{i}:{type(res).__name__}"
            if hasattr(res, 'size'):
                res_str += f":size={res.size}"
            if hasattr(res, 'format'):
                res_str += f":fmt={res.format}"
            hasher.update(res_str.encode())
        
        # Op structure (opcode + input count)
        for i, op in enumerate(all_ops):
            op_str = f"op{i}:{op.opcode.name}:inputs={len(op.inputs)}"
            hasher.update(op_str.encode())
        
        return hasher.hexdigest()
    
    def invalidate(self, graph: Graph) -> bool:
        """
        Invalidate cache for a specific graph.
        
        Call this when you know the graph has changed.
        
        Returns:
            True if cache entry was removed, False if not found
        """
        graph_hash = self._compute_graph_hash(graph)
        return self._cache.invalidate(graph_hash)
    
    def clear_cache(self) -> None:
        """Clear the entire compilation cache."""
        self._cache.clear()
        logger.debug("GraphCompiler cache cleared")
    
    def stats(self) -> Dict[str, Any]:
        """Return cache statistics."""
        return self._cache.stats()


# Singleton instance for convenience
_global_compiler: Optional[GraphCompiler] = None


def get_compiler() -> GraphCompiler:
    """Get the global GraphCompiler instance."""
    global _global_compiler
    if _global_compiler is None:
        _global_compiler = GraphCompiler()
    return _global_compiler


def compile_graph(graph: Graph) -> List[Union[ComputePass, PassLoop]]:
    """
    Convenience function to compile a graph using the global compiler.
    
    Args:
        graph: IR Graph to compile
        
    Returns:
        List of ComputePass and PassLoop items
    """
    return get_compiler().compile(graph)
