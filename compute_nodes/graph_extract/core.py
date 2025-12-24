# Core Graph Extraction Logic
# Converts a ComputeNodeTree into an IR Graph using modular handlers

import logging
from typing import Dict, Set

from ..ir.graph import Graph, IRBuilder, Value, ValueKind
from ..ir.ops import OpCode
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
    builder = IRBuilder(graph)
    
    # Map: Socket Pointer (int) -> Value (SSA)
    socket_value_map: Dict[int, Value] = {}
    
    # Recursion stack for cycle detection
    recursion_stack: Set[int] = set()
    
    # Find Output Nodes
    output_nodes = []
    for node in nodetree.nodes:
        if node.bl_idname == 'ComputeNodeOutput':
            output_nodes.append(node)
            
    if not output_nodes:
        logger.warning("No Output Node found")
        return graph

    def get_socket_key(socket):
        """Get unique key for a socket."""
        if hasattr(socket, "as_pointer"):
            return socket.as_pointer()
        return id(socket)

    def get_node_key(node):
        """Get unique key for a node."""
        if hasattr(node, "as_pointer"):
            return node.as_pointer()
        return id(node)

    def get_socket_value(socket) -> Value:
        """Recursively get or compute the value for a socket."""
        key = get_socket_key(socket)
        if key in socket_value_map:
            return socket_value_map[key]
            
        # If linked, traverse
        if socket.is_linked:
            if len(socket.links) > 1:
                raise ValueError(f"Socket {socket.name} has multiple links, which is not supported for Inputs.")
            
            link = socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Recursive call to process dependency
            val = process_node(from_node, from_socket)
            socket_value_map[key] = val
            return val
        else:
            # Not linked: Use default value
            if hasattr(socket, "default_value"):
                # Handle ComputeSocketImage default value (PointerProperty)
                if socket.bl_idname == 'ComputeSocketImage':
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

    def process_node(node, output_socket_needed=None) -> Value:
        """Process a node using the handler registry."""
        node_key = get_node_key(node)
        if node_key in recursion_stack:
            raise RecursionError(f"Cycle detected at node {node.name}")
        
        recursion_stack.add(node_key)
        
        try:
            # Look up handler in registry
            handler = get_handler(node.bl_idname)
            
            if handler is not None:
                # Build context for handler
                ctx = {
                    'builder': builder,
                    'socket_value_map': socket_value_map,
                    'get_socket_key': get_socket_key,
                    'get_socket_value': get_socket_value,
                    'output_socket_needed': output_socket_needed,
                }
                return handler(node, ctx)
            else:
                # Unknown node type
                logger.warning(f"Unknown node type: {node.bl_idname}")
                return None
                
        finally:
            recursion_stack.remove(node_key)

    # Process all output nodes
    for output_node in output_nodes:
        # NEW DESIGN: Get properties from node instead of socket
        output_name = output_node.output_name
        output_width = output_node.width
        output_height = output_node.height
        output_format = output_node.format
        
        # Create ImageDesc for the output
        desc = ImageDesc(
            name=output_name,
            access=ResourceAccess.WRITE,
            format=output_format,
            size=(output_width, output_height)
        )
        val_target = builder.add_resource(desc)
        
        # Data socket is now inputs[0] (Color)
        data_socket = output_node.inputs[0]
        
        # Data to Write
        val_data = get_socket_value(data_socket)
        if val_data is None:
            logger.warning(f"Output node {output_node.name} has no data to write")
            continue
            
        # Ensure VEC4 for RGBA formats
        if val_data.type == DataType.VEC3:
            val_data = builder.cast(val_data, DataType.VEC4)
        if val_data.type == DataType.IVEC2:
            val_data = builder.cast(val_data, DataType.VEC4)
        if val_data.type == DataType.FLOAT:
            val_data = builder.cast(val_data, DataType.VEC4)
        
        # Coord construction
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_coord_uvec = builder.swizzle(val_gid, "xy")
        val_coord_ivec = builder.cast(val_coord_uvec, DataType.IVEC2)
        
        # Image Store
        builder.image_store(val_target, val_coord_ivec, val_data)
    
    return graph

