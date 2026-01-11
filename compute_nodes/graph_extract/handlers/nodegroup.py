# Node Groups Handler
# Handles: ComputeNodeGroup, ComputeNodeGroupInput, ComputeNodeGroupOutput

from ...ir.types import DataType

# Note: get_handler is imported inside handle_nodegroup to avoid circular import


def handle_nodegroup(node, ctx):
    """
    Handle ComputeNodeGroup - recursively extract the referenced tree.
    """
    # DEBUG LOG
    scope = ctx.extra.get('scope_path', [])
    indent = "  " * len(scope)
    tree_name = node.node_tree.name if node.node_tree else "None"
    print(f"{indent}DEBUG_VISIT_GROUP: Node='{node.name}' Tree='{tree_name}' Scope={scope}")

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
    # Build the inner scope for this group instance
    current_scope = scope
    inner_scope = tuple(current_scope + [node.name])
    
    if group_input:
        for i, outer_socket in enumerate(node.inputs):
            if i < len(group_input.outputs):
                inner_socket = group_input.outputs[i]
                # Get the value from outer connection
                outer_value = ctx.get_input(i)

                if outer_value is not None:
                    # Use inner scope for the key so inner nodes find it
                    if hasattr(inner_socket, "as_pointer"):
                        ptr = inner_socket.as_pointer()
                    else:
                        ptr = id(inner_socket)
                    inner_key = (ptr, inner_scope)
                    ctx._socket_value_map[inner_key] = outer_value
                    
                    # DEBUG LOG
                    if node.node_tree and node.node_tree.name == "CN Erosion Moore Sample":
                        res_idx = getattr(outer_value, 'resource_index', 'NA') if outer_value else 'None'
                        print(f"{indent}  DEBUG_MOORE_CHECK: Input {i}")
                        print(f"{indent}    Outer: {outer_socket.name} -> Inner: {inner_socket.name}")
                        print(f"{indent}    Value: {outer_value} (Res: {res_idx})")
                else:
                    if node.node_tree and node.node_tree.name == "CN Erosion Moore Sample":
                        print(f"{indent}  FATAL_MOORE_FAIL: Input {i} ({outer_socket.name}) is NONE!")
                        print(f"{indent}    Scope: {inner_scope}")
                    # print(f"{indent}  DEBUG_GROUP_FAIL: Input {i} ({outer_socket.name}) is NONE")
    
    # Step 2: Process inner tree by getting GroupOutput's input values
    result_values = []
    
    for i, inner_socket in enumerate(group_output.inputs):
        if inner_socket.is_linked:
            # Traverse the inner tree
            link = inner_socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Check if we already have this value (with new scope)
            # We need to check with the INNER scope, not parent scope
            current_scope = ctx.extra.get('scope_path', [])
            new_scope = tuple(current_scope + [node.name])
            
            # Create scope-aware key for lookup
            if hasattr(from_socket, "as_pointer"):
                from_ptr = from_socket.as_pointer()
            else:
                from_ptr = id(from_socket)
            from_key = (from_ptr, new_scope)
            
            if from_key in ctx._socket_value_map:
                val = ctx._socket_value_map[from_key]
            else:
                # Need to process the inner node
                from ..registry import get_handler
                handler = get_handler(from_node.bl_idname)
                if handler:
                    # Create valid NodeContext for inner node
                    from ..node_context import NodeContext
                    
                    # Merge parent context with local requirements
                    new_extra = ctx.extra.copy()
                    new_extra['output_socket_needed'] = from_socket
                    new_extra['scope_path'] = list(new_scope)
                    
                    # Create SCOPE-AWARE closures for inner context
                    # This is critical: inner nodes must use the extended scope
                    def inner_get_socket_key(socket, _scope=new_scope):
                        if hasattr(socket, "as_pointer"):
                            ptr = socket.as_pointer()
                        else:
                            ptr = id(socket)
                        return (ptr, _scope)
                    
                    def inner_get_socket_value(socket, _scope=new_scope, _map=ctx._socket_value_map, _builder=builder, _parent_ctx=ctx):
                        key = inner_get_socket_key(socket, _scope)
                        if key in _map:
                            return _map[key]
                        # For linked sockets, we must traverse with the correct scope
                        if socket.is_linked:
                            link = socket.links[0]
                            from_socket = link.from_socket
                            from_node = link.from_node
                            
                            # Check if from_socket is already computed (with this scope)
                            from_key = inner_get_socket_key(from_socket, _scope)
                            if from_key in _map:
                                val = _map[from_key]
                                _map[key] = val
                                return val
                            
                            # Process the upstream node
                            from ..registry import get_handler
                            handler = get_handler(from_node.bl_idname)
                            if handler:
                                from ..node_context import NodeContext
                                upstream_extra = _parent_ctx.extra.copy()
                                upstream_extra['output_socket_needed'] = from_socket
                                upstream_extra['scope_path'] = list(_scope)
                                
                                upstream_ctx = NodeContext(
                                    builder=_builder,
                                    node=from_node,
                                    socket_value_map=_map,
                                    get_socket_key=inner_get_socket_key,
                                    get_socket_value=inner_get_socket_value,
                                    extra_ctx=upstream_extra
                                )
                                handler(from_node, upstream_ctx)
                                
                                val = _map.get(from_key)
                                if val is not None:
                                    _map[key] = val
                                return val
                            return None
                        # For unlinked sockets, use default value
                        if hasattr(socket, "default_value"):
                            from ...ir.types import DataType
                            dtype = DataType.FLOAT
                            if socket.type == 'VECTOR': dtype = DataType.VEC3
                            elif socket.type == 'RGBA': dtype = DataType.VEC4
                            elif socket.type == 'INT': dtype = DataType.INT
                            val = _builder.constant(socket.default_value, dtype)
                            _map[key] = val
                            return val
                        return None
                    
                    inner_ctx = NodeContext(
                        builder=builder,
                        node=from_node,
                        socket_value_map=ctx._socket_value_map,
                        get_socket_key=inner_get_socket_key,
                        get_socket_value=inner_get_socket_value,
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
    
    # DEBUG LOG
    print(f"DEBUG_GROUP_INPUT: Handle Inputs for '{node.name}'")
    if output_socket_needed:
        print(f"  Needed: {output_socket_needed.name}")
    
    # Return the value for the requested output socket
    # These should have been set by the parent NodeGroup handler
    if output_socket_needed:
        key = ctx._get_socket_key(output_socket_needed)
        if key in ctx._socket_value_map:
            val = ctx._socket_value_map[key]
            res_idx = getattr(val, 'resource_index', 'NA') if val else 'None'
            print(f"  FOUND Key: {key}")
            print(f"  Value: {val} (Res: {res_idx})")
            return val
        else:
            print(f"  MISSING Key: {key}")
            # printKeys = [str(k) for k in ctx._socket_value_map.keys() if 'Group' in str(k)]
            # print(f"  Available Group Keys: {printKeys}")
    
    # If no specific output requested, try first output
    if node.outputs:
        print(f"  Fallback to Output 0: {node.outputs[0].name}")
        key = ctx._get_socket_key(node.outputs[0])
        if key in ctx._socket_value_map:
            val = ctx._socket_value_map[key]
            res_idx = getattr(val, 'resource_index', 'NA') if val else 'None'
            print(f"  FOUND Key: {key} (Fallback)")
            print(f"  Value: {val} (Res: {res_idx})")
            return val
        else:
            print(f"  MISSING Key: {key} (Fallback)")
    
    print("  FAILED to find input value.")
    return None


def handle_group_output(node, ctx):
    """
    Handle ComputeNodeGroupOutput.
    """
    # GroupOutput doesn't need to do anything here
    # Its inputs are read directly by handle_nodegroup
    return None

