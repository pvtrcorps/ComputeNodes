# Reroute Node Handler
# NodeReroute is a layout helper that passes data through unchanged.

def handle_reroute(node, ctx):
    """
    Handle NodeReroute (Standard Blender Reroute Node).
    
    Logic:
    - Pass-through: Just return the Value from the input socket.
    - If unlinked, return None.
    """
    # Reroute nodes have one input (index 0).
    if not node.inputs:
        return None
        
    # Get value from upstream using NodeContext
    val = ctx.get_input(0)
    
    return val
