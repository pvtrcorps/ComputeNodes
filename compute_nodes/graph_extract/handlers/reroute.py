# Reroute Node Handler
# NodeReroute is a layout helper that passes data through unchanged.

def handle_reroute(node, ctx):
    """
    Handle NodeReroute (Standard Blender Reroute Node).
    
    Logic:
    - Pass-through: Just return the Value from the input socket.
    - If unlinked, return None.
    """
    get_socket_value = ctx['get_socket_value']
    
    # Reroute nodes have one input (index 0) and one output (index 0).
    # We just need to resolve the input and return it.
    # The extraction core will map this return value to the node's output key automatically needed?
    # Actually, core.process_node returns the value, but we also need to map it 
    # to the output socket if this node is used as a dependency.
    
    # However, core.get_socket_value calls process_node. 
    # If process_node returns a Value, that Value is what get_socket_value returns 
    # to the caller (the downstream node).
    
    # Let's look at core.py:
    # val = process_node(from_node, from_socket)
    # socket_value_map[key] = val
    
    # So yes, we just need to return the Value.
    
    if not node.inputs:
        return None
        
    # Get value from upstream
    val = get_socket_value(node.inputs[0])
    
    return val
