# Node Groups Handler
# Handles: ComputeNodeGroup, ComputeNodeGroupInput, ComputeNodeGroupOutput
#
# Strategy for recursive group evaluation:
# 1. When ComputeNodeGroup is processed, we find GroupInput/GroupOutput in the inner tree
# 2. Map outer inputs → GroupInput's outputs (in socket_value_map with inner socket keys)
# 3. Process by asking for GroupOutput's input values (recursive traversal of inner tree)
# 4. Map GroupOutput's inputs → outer outputs

from ...ir.types import DataType

# Note: get_handler is imported inside handle_nodegroup to avoid circular import


def handle_nodegroup(node, ctx):
    """
    Handle ComputeNodeGroup - recursively extract the referenced tree.
    
    This is complex because we need to:
    1. Map the outer node's inputs to the inner tree's GroupInput outputs
    2. Recursively process the inner tree's nodes
    3. Return the inner tree's GroupOutput input values as our outputs
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')
    
    inner_tree = node.node_tree
    if not inner_tree:
        return None
    
    # Find GroupInput and GroupOutput in inner tree
    group_input = None
    group_output = None
    
    for inner_node in inner_tree.nodes:
        if inner_node.bl_idname == 'ComputeNodeGroupInput':
            group_input = inner_node
        elif inner_node.bl_idname == 'ComputeNodeGroupOutput':
            if group_output is None or getattr(inner_node, 'is_active_output', False):
                group_output = inner_node
    
    if not group_output:
        # No output defined, nothing to compute
        return None
    
    # Step 1: Map outer inputs to GroupInput outputs
    # When inner nodes ask for GroupInput's output values, they get the outer values
    if group_input:
        for i, outer_socket in enumerate(node.inputs):
            if i < len(group_input.outputs):
                inner_socket = group_input.outputs[i]
                # Get the value from outer connection
                outer_value = get_socket_value(outer_socket)
                if outer_value is not None:
                    inner_key = get_socket_key(inner_socket)
                    socket_value_map[inner_key] = outer_value
    
    # Step 2: Process inner tree by getting GroupOutput's input values
    # This will recursively traverse the inner tree
    result_values = []
    
    for i, inner_socket in enumerate(group_output.inputs):
        if inner_socket.is_linked:
            # Traverse the inner tree
            link = inner_socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Check if we already have this value
            from_key = get_socket_key(from_socket)
            if from_key in socket_value_map:
                val = socket_value_map[from_key]
            else:
                # Need to process the inner node
                # Use the inner node's handler - import here to avoid circular import
                from ..registry import get_handler
                handler = get_handler(from_node.bl_idname)
                if handler:
                    inner_ctx = {
                        'builder': builder,
                        'socket_value_map': socket_value_map,
                        'get_socket_key': get_socket_key,
                        'get_socket_value': get_socket_value,
                        'output_socket_needed': from_socket,
                    }
                    val = handler(from_node, inner_ctx)
                    
                    # If handler returns value, cache it for the output socket
                    if val is not None:
                        socket_value_map[from_key] = val
                else:
                    val = None
            
            result_values.append(val)
            
            # Map to outer output socket
            if i < len(node.outputs):
                outer_output_key = get_socket_key(node.outputs[i])
                socket_value_map[outer_output_key] = val
        else:
            # Not linked - use default value if any
            if hasattr(inner_socket, 'default_value'):
                dtype = DataType.FLOAT
                if inner_socket.type == 'VECTOR': dtype = DataType.VEC3
                elif inner_socket.type == 'RGBA': dtype = DataType.VEC4
                val = builder.constant(inner_socket.default_value, dtype)
                result_values.append(val)
                
                if i < len(node.outputs):
                    outer_output_key = get_socket_key(node.outputs[i])
                    socket_value_map[outer_output_key] = val
            else:
                result_values.append(None)
    
    # Return appropriate value based on output_socket_needed
    if output_socket_needed:
        for i, out in enumerate(node.outputs):
            if out == output_socket_needed and i < len(result_values):
                return result_values[i]
    
    # Return first value by default
    return result_values[0] if result_values else None


def handle_group_input(node, ctx):
    """
    Handle ComputeNodeGroupInput.
    
    This node doesn't compute anything itself - its output values
    are populated by the parent ComputeNodeGroup handler when it
    maps outer inputs to inner GroupInput outputs.
    
    If we reach here, it means we need to return the pre-mapped values.
    """
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    output_socket_needed = ctx.get('output_socket_needed')
    
    # Return the value for the requested output socket
    # These should have been set by the parent NodeGroup handler
    if output_socket_needed:
        key = get_socket_key(output_socket_needed)
        if key in socket_value_map:
            return socket_value_map[key]
    
    # If no specific output requested, try first output
    if node.outputs:
        key = get_socket_key(node.outputs[0])
        if key in socket_value_map:
            return socket_value_map[key]
    
    return None


def handle_group_output(node, ctx):
    """
    Handle ComputeNodeGroupOutput.
    
    This node collects inputs and marks them as the group's outputs.
    It doesn't produce any output values itself - the values flow
    from connected nodes through its inputs.
    
    The actual output mapping is handled by handle_nodegroup when
    it reads the GroupOutput's input connections.
    """
    # GroupOutput doesn't need to do anything here
    # Its inputs are read directly by handle_nodegroup
    return None
