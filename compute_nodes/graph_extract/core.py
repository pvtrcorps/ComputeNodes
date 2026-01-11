# Core Graph Extraction Logic
# Converts a ComputeNodeTree into an IR Graph using modular handlers

import logging
from typing import Dict, Set

from ..ir.graph import Graph, IRBuilder, Value, ValueKind
from ..ir.resources import ImageDesc, ResourceAccess
from ..ir.types import DataType

from .registry import get_handler

logger = logging.getLogger(__name__)

# Mock BPY for separate testing if needed, or assume running in Blender
try:
    import bpy
except ImportError:
    bpy = None


def extract_graph(nodetree) -> Graph:
    """
    Converts a ComputeNodeTree into an IR Graph.
    Uses modular handlers for each node type.
    """
    graph = Graph(name=nodetree.name)
    
    from ..logger import log_debug
    log_debug(f"Graph extraction started for '{nodetree.name}' ({len(nodetree.nodes)} nodes)")
    
    builder = IRBuilder(graph)
    
    # Map: Socket Pointer (int) -> Value (SSA)
    socket_value_map: Dict[int, Value] = {}
    
    # Recursion stack for cycle detection
    recursion_stack: Set[int] = set()
    
    # Shared extraction state (propagated through all NodeContext instances)
    # loop_depth: 0 = outside any loop, 1+ = inside loop(s)
    extraction_state: Dict[str, any] = {
        'loop_depth': 0,
    }
    
    # Find Output Nodes (Output Image, Output Sequence, Viewer)
    output_nodes = []
    output_bl_idnames = {'ComputeNodeOutputImage', 'ComputeNodeOutputSequence', 'ComputeNodeViewer'}
    for node in nodetree.nodes:
        if node.bl_idname in output_bl_idnames:
            output_nodes.append(node)
            
    if not output_nodes:
        logger.warning("No Output Node found (Output Image or Output Sequence)")
        return graph

    def get_socket_key(socket, scope=()):
        """Get unique key for a socket, including scope for NodeGroup differentiation."""
        if hasattr(socket, "as_pointer"):
            ptr = socket.as_pointer()
        else:
            ptr = id(socket)
        # Include scope tuple for unique keys across NodeGroup instances
        return (ptr, tuple(scope))

    def get_node_key(node):
        """Get unique key for a node."""
        if hasattr(node, "as_pointer"):
            return node.as_pointer()
        return id(node)

    def get_socket_value(socket, scope=()) -> Value:
        """Recursively get or compute the value for a socket.
        
        Auto-Sample Feature:
        When a Grid (HANDLE) is connected to a socket expecting a Field value
        (FLOAT, VEC3, VEC4, RGBA), automatically inject a sample operation
        using normalized UV coordinates.
        """
        key = get_socket_key(socket, scope)
        if hasattr(socket, 'name'):
             pass # print(f"DEBUG_CORE: get_socket_value {socket.name} (Node: {socket.node.name if hasattr(socket, 'node') and socket.node else 'None'}). Linked: {socket.is_linked}")

        if key in socket_value_map:
            return socket_value_map[key]
            
        # print(f"DEBUG: get_socket_value {socket.name} (Node: {socket.node.name}). Linked: {socket.is_linked}")
            
        # If linked, traverse
        if socket.is_linked:
            if len(socket.links) > 1:
                raise ValueError(f"Socket {socket.name} has multiple links, which is not supported for Inputs.")
            
            link = socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Optimization/Cycle Breaking: Check if source socket is already computed
            # This allows reading outputs from a node that is currently on the recursion stack
            # (e.g. Repeat Input providing values for the loop body)
            from_key = get_socket_key(from_socket, scope)
            if from_key in socket_value_map:
                val = socket_value_map[from_key]
                socket_value_map[key] = val
                return val
            
            # Recursive call to process dependency (pass scope)
            val = process_node(from_node, from_socket, scope)
            
            # === AUTO-SAMPLE: Grid → Field conversion ===
            # If we got a HANDLE (Grid) but the socket expects a field type,
            # automatically inject sampling with normalized UVs.
            if val is not None and val.type == DataType.HANDLE:
                socket_type = getattr(socket, 'type', None)
                # Field-expecting sockets: VALUE, VECTOR, RGBA
                # EXCEPTION: NodeReroute sockets appear as RGBA but should pass-through Handles/Grids without sampling.
                if socket_type in ('VALUE', 'VECTOR', 'RGBA', 'FLOAT') and socket.node.bl_idname != 'NodeReroute':
                    # Create normalized UV from gl_GlobalInvocationID
                    # Uses placeholder that emit_sample will expand inline
                    uv_placeholder = builder.constant((0.5, 0.5), DataType.VEC2)
                    val = builder.sample(val, uv_placeholder)
                    logger.debug(f"Auto-sample injected for {socket.name}")
            
            socket_value_map[key] = val
            return val
        else:
            # Not linked: Use default value
            if hasattr(socket, "default_value"):
                # Handle NodeSocketImage default value (native Blender Image pointer)
                if socket.bl_idname == 'NodeSocketImage':
                    img = socket.default_value
                    if not img:
                        return None
                    
                    fmt = "rgba32f" if img.is_float else "rgba8"
                    desc = ImageDesc(name=img.name, access=ResourceAccess.READ, format=fmt)
                    val = builder.add_resource(desc)
                    socket_value_map[key] = val
                    return val

                # Determine type based on socket type
                dtype = DataType.FLOAT 
                if socket.type == 'VECTOR': dtype = DataType.VEC3
                elif socket.type == 'RGBA': dtype = DataType.VEC4
                elif socket.type == 'INT': dtype = DataType.INT
                elif socket.type == 'BOOLEAN': dtype = DataType.BOOL
                
                const_val = builder.constant(socket.default_value, dtype)
                socket_value_map[key] = const_val
                return const_val
            
            # Unlinked non-value socket
            return None 

    from .node_context import NodeContext
    
    def process_node(node, out_socket=None, scope=()) -> Value:
        """
        Process a single node and return the value for the requested output socket.
        """
        key_node = get_node_key(node)
        
        # Cycle detection
        if key_node in recursion_stack:
            # Check for Loop Input nodes - they break cycles by valid design
            if node.bl_idname == 'ComputeNodeRepeatInput':
                # Return whatever is available (likely None if not processed, but handled by pass splitting)
                pass
            else:
                raise RecursionError(f"Cycle detected at node {node.name}")

        recursion_stack.add(key_node)
        
        try:
            handler = get_handler(node.bl_idname)
            if not handler:
                logger.warning(f"No handler for {node.bl_idname}")
                return None
            
            # Create typed context - include extraction_state reference for loop_depth tracking
            # Pass as 'extraction_state' key so the dict can be modified by handlers
            # Create scope-aware wrappers for this context
            def scoped_get_socket_key(socket):
                return get_socket_key(socket, scope)
            
            def scoped_get_socket_value(socket):
                return get_socket_value(socket, scope)
            
            ctx = NodeContext(
                builder=builder,
                node=node,
                socket_value_map=socket_value_map,
                get_socket_key=scoped_get_socket_key,
                get_socket_value=scoped_get_socket_value,
                extra_ctx={
                    'output_socket_needed': out_socket,
                    'extraction_state': extraction_state,
                    'scope_path': list(scope),  # Current scope as mutable list
                }
            )
            
            # Execute handler
            # Handlers execute side-effects (emit ops) and populate socket_value_map
            result = handler(node, ctx)
            
            return result
            
        finally:
            recursion_stack.remove(key_node)

    # Process all output nodes via their registered handlers
    # Process all output nodes via their registered handlers
    for output_node in output_nodes:
        # Create typed context for output handler
        ctx = NodeContext(
            builder=builder,
            node=output_node,
            socket_value_map=socket_value_map,
            get_socket_key=get_socket_key,
            get_socket_value=get_socket_value,
            extra_ctx={'output_socket_needed': None}
        )
        
        # Use the registered handler for output nodes
        handler = get_handler(output_node.bl_idname)
        if handler:
            handler(output_node, ctx)
        else:
            logger.error(f"No handler registered for {output_node.bl_idname}")
    
    return graph

