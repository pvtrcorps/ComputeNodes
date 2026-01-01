# Node Groups Handler
# Handles: ComputeNodeGroup, ComputeNodeGroupInput, ComputeNodeGroupOutput

from ...ir.types import DataType

# Note: get_handler is imported inside handle_nodegroup to avoid circular import


def handle_nodegroup(node, ctx):
    """
    Handle ComputeNodeGroup - recursively extract the referenced tree.
    """
    builder = ctx.builder
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
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
                outer_value = ctx.get_input(outer_socket.name) # Using name lookup on outer node
                # Or better (more consistent with core):
                # out_val = ctx._get_socket_value(outer_socket) 
                # But NodeContext.get_input handles name or index.
                # Let's use get_input with index which is safer for order
                outer_value = ctx.get_input(i)

                if outer_value is not None:
                    inner_key = ctx._get_socket_key(inner_socket)
                    ctx._socket_value_map[inner_key] = outer_value
    
    # Step 2: Process inner tree by getting GroupOutput's input values
    result_values = []
    
    for i, inner_socket in enumerate(group_output.inputs):
        if inner_socket.is_linked:
            # Traverse the inner tree
            link = inner_socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Check if we already have this value
            from_key = ctx._get_socket_key(from_socket)
            if from_key in ctx._socket_value_map:
                val = ctx._socket_value_map[from_key]
            else:
                # Need to process the inner node
                from ..registry import get_handler
                handler = get_handler(from_node.bl_idname)
                if handler:
                    # Create valid NodeContext for inner node
                    # We reuse the SAME socket_value_map to share values across group boundaries
                    # This is key for efficient processing (memoization works globally)
                    from ..node_context import NodeContext
                    
                    # Merge parent context with local requirements
                    # Copy to avoid polluting parent context with child's output requirement
                    new_extra = ctx.extra.copy()
                    new_extra['output_socket_needed'] = from_socket
                    
                    inner_ctx = NodeContext(
                        builder=builder,
                        node=from_node,
                        socket_value_map=ctx._socket_value_map,
                        get_socket_key=ctx._get_socket_key,
                        get_socket_value=ctx._get_socket_value,
                        extra_ctx=new_extra
                    )
                    
                    handler(from_node, inner_ctx)
                    
                    val = ctx._socket_value_map.get(from_key)
                else:
                    val = None
            
            result_values.append(val)
            
            # Map to outer output socket
            if i < len(node.outputs):
                outer_output_key = ctx._get_socket_key(node.outputs[i])
                ctx._socket_value_map[outer_output_key] = val
        else:
            # Not linked - use default value if any
            if hasattr(inner_socket, 'default_value'):
                dtype = DataType.FLOAT
                if inner_socket.type == 'VECTOR': dtype = DataType.VEC3
                elif inner_socket.type == 'RGBA': dtype = DataType.VEC4
                val = builder.constant(inner_socket.default_value, dtype)
                result_values.append(val)
                
                if i < len(node.outputs):
                    outer_output_key = ctx._get_socket_key(node.outputs[i])
                    ctx._socket_value_map[outer_output_key] = val
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
    """
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Return the value for the requested output socket
    # These should have been set by the parent NodeGroup handler
    if output_socket_needed:
        key = ctx._get_socket_key(output_socket_needed)
        if key in ctx._socket_value_map:
            return ctx._socket_value_map[key]
    
    # If no specific output requested, try first output
    if node.outputs:
        key = ctx._get_socket_key(node.outputs[0])
        if key in ctx._socket_value_map:
            return ctx._socket_value_map[key]
    
    return None


def handle_group_output(node, ctx):
    """
    Handle ComputeNodeGroupOutput.
    """
    # GroupOutput doesn't need to do anything here
    # Its inputs are read directly by handle_nodegroup
    return None

