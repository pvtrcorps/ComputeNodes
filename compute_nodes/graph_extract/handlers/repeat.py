# Repeat Zone Handlers - Multi-pass loop support
#
# Handles: ComputeNodeRepeatInput, ComputeNodeRepeatOutput

import logging
from typing import Optional, Any, List, Dict

from ...ir.graph import ValueKind
from ...ir.ops import OpCode
from ...ir.types import DataType
from ...ir.resources import ImageDesc, ResourceAccess


logger = logging.getLogger(__name__)


# Socket type to DataType mapping
SOCKET_TO_DATATYPE = {
    'NodeSocketFloat': DataType.FLOAT,
    'NodeSocketVector': DataType.VEC3,
    'NodeSocketColor': DataType.VEC4,
    'ComputeSocketGrid': DataType.HANDLE,
    'NodeSocketInt': DataType.INT,
}

# Import centralized resource tracing from graph.py
from ...ir.graph import _trace_resource_index
from ...ir.state import StateVar


def _find_source_resource(val, graph):
    """
    Find the source ResourceDesc for a value by tracing through SSA origins.
    """
    res_idx = _trace_resource_index(val)
    if res_idx is not None and res_idx < len(graph.resources):
        return graph.resources[res_idx]
    return None


def handle_repeat_output(node, ctx):
    """
    Handle ComputeNodeRepeatOutput node.
    This is the main entry point for the loop - we process from Output
    backwards to find the Input and build the complete loop structure.
    """
    builder = ctx.builder
    
    # Find paired RepeatInput
    repeat_input = _find_repeat_input(node)
    
    if not repeat_input:
        logger.warning(f"Repeat Output '{node.name}' has no paired Repeat Input")
        return builder.constant(0.0, DataType.FLOAT)
    
    # Get iteration count
    # Use _get_socket_value directly because the socket belongs to RepeatInput, not RepeatOutput (ctx.node)
    val_iters = ctx._get_socket_value(repeat_input.inputs["Iterations"])
    if val_iters is None:
        val_iters = builder.constant(10, DataType.INT)
    val_iters = builder.cast(val_iters, DataType.INT)
    
    # Build state variable descriptors
    state_vars = []
    repeat_items = list(repeat_input.repeat_items)
    
    for i, item in enumerate(repeat_items):
        socket_name = item.name
        
        val_initial = None
        if socket_name in repeat_input.inputs:
            # We access RepeatInput's input sockets using the value map present in ctx
            # ctx has access to socket_value_map which should contain values processed before
            socket_in = repeat_input.inputs[socket_name]
            val_initial = ctx._get_socket_value(socket_in)
        
        # Determine data type
        is_grid = item.socket_type == 'ComputeSocketGrid'
        
        # GRID-ONLY VALIDATION
        if not is_grid:
            raise ValueError(
                f"Repeat zone state '{item.name}' must be a Grid (got {item.socket_type}).\n"
                f"Multi-pass GPU loops cannot pass Fields or scalar values between iterations.\n"
                f"Solution: Use Capture to convert Field → Grid before the loop."
            )
        
        data_type = DataType.HANDLE  # Always HANDLE for Grids
        
        # Create StateVar object instead of dict
        state = StateVar(
            name=item.name,
            index=i,
            is_grid=True,
            data_type=data_type,
            initial_value=val_initial,
            socket_name=socket_name
        )
        
        # For Grid states, create ping-pong buffer resources
        if is_grid and val_initial is not None:
             # Get size and format from initial
            source_resource = _find_source_resource(val_initial, builder.graph)
            
            if source_resource:
                size = source_resource.size
                dims = source_resource.dimensions
                fmt = getattr(source_resource, 'format', 'RGBA32F')
                
                state.format = fmt
                
                desc_ping = ImageDesc(name=f"loop_{node.name}_{item.name}_ping", access=ResourceAccess.READ_WRITE, format=fmt, size=size, dimensions=dims, is_internal=True)
                desc_pong = ImageDesc(name=f"loop_{node.name}_{item.name}_pong", access=ResourceAccess.READ_WRITE, format=fmt, size=size, dimensions=dims, is_internal=True)
                
                val_ping = builder.add_resource(desc_ping)
                val_pong = builder.add_resource(desc_pong)
                
                state.ping_idx = val_ping.resource_index
                state.pong_idx = val_pong.resource_index
                state.size = size
                state.dimensions = dims
        
        state_vars.append(state)
    
    # Emit PASS_LOOP_BEGIN
    val_iters_arg = val_iters 
    
    loop_metadata = {
        'iterations': val_iters_arg,
        'state_vars': state_vars,
        'repeat_input_name': repeat_input.name,
        'repeat_output_name': node.name,
    }
    
    op_begin = builder.add_op(OpCode.PASS_LOOP_BEGIN, [val_iters_arg])
    op_begin.metadata = loop_metadata
    
    # Create valid values for the loop iteration
    val_iteration = builder._new_value(ValueKind.SSA, DataType.INT, origin=op_begin)
    op_begin.add_output(val_iteration)
    
    # Manually map to RepeatInput's Iteration output socket
    key_iteration = ctx._get_socket_key(repeat_input.outputs["Iteration"])
    ctx._socket_value_map[key_iteration] = val_iteration
    
    # Create read values for each state variable
    for state in state_vars:
        op_read = builder.add_op(OpCode.PASS_LOOP_READ, [])
        op_read.metadata = {'state_index': state.index, 'state_name': state.name}
        
        val_current = builder._new_value(ValueKind.SSA, DataType.HANDLE, origin=op_read)
        if state.ping_idx is not None:
            val_current.resource_index = state.ping_idx
        op_read.add_output(val_current)
        
        # Map to Current socket (on RepeatInput)
        current_key = ctx._get_socket_key(repeat_input.outputs[state.socket_name])
        ctx._socket_value_map[current_key] = val_current
        state.current_value = val_current
    
    # Process body - Inputs to RepeatOutput
    for state in state_vars:
        val_next = None
        if state.socket_name in node.inputs:
            # We can use ctx.get_input() here because we are at the RepeatOutput node
            val_next = ctx.get_input(state.socket_name)
        
        if val_next is None:
            val_next = state.current_value
        
        if val_next is None:
            val_next = builder.constant(0.0, state.data_type)
        
        if state.is_grid and state.pong_idx is not None:
            if val_next.resource_index is not None and val_next.resource_index != state.pong_idx:
                logger.debug(f"Adding copy: resource {val_next.resource_index} -> pong {state.pong_idx}")
                state.copy_from_resource = val_next.resource_index
        
        state.next_value = val_next
    
    # Emit PASS_LOOP_END
    next_values = [s.next_value for s in state_vars]
    op_end = builder.add_op(OpCode.PASS_LOOP_END, next_values)
    op_end.metadata = loop_metadata
    
    # Create output values for Final sockets
    results = {}
    for i, state in enumerate(state_vars):
        val_final = builder._new_value(ValueKind.SSA, state.data_type, origin=op_end)
        op_end.add_output(val_final)
        
        if state.is_grid and state.pong_idx is not None:
            val_final.resource_index = state.pong_idx
        
        # Map to Final socket (on RepeatOutput)
        ctx.set_output(state.socket_name, val_final)
        results[state.name] = val_final
    
    # Return requested socket
    output_socket_needed = ctx.extra.get('output_socket_needed')
    if output_socket_needed:
        for state in state_vars:
            if state.socket_name == output_socket_needed.name:
                return results.get(state.name)
    
    if state_vars:
        return results.get(state_vars[0].name)
    return None


def handle_repeat_input(node, ctx):
    """
    Handle ComputeNodeRepeatInput node.
    Triggers RepeatOutput processing if needed.
    """
    builder = ctx.builder
    # Access internal map directly since this handler has logic that crosses node boundaries
    socket_value_map = ctx._socket_value_map
    get_socket_key = ctx._get_socket_key
    
    output_socket_needed = ctx.extra.get('output_socket_needed')
    
    # Check if values are already mapped
    key_iteration = get_socket_key(node.outputs["Iteration"])
    
    if key_iteration in socket_value_map:
        if output_socket_needed:
            req_key = get_socket_key(output_socket_needed)
            if req_key in socket_value_map:
                return socket_value_map[req_key]
        return socket_value_map[key_iteration]
    
    # Not yet processed - process paired RepeatOutput
    paired_output = _find_repeat_output(node)
    
    if paired_output:
        from ..registry import get_handler
        handler = get_handler(paired_output.bl_idname)
        if handler:
            logger.debug(f"Triggering RepeatOutput processing from RepeatInput")
            
            # Create a temporary context for the paired node
            # This is critical REFACTOR point: we need to instantiate NodeContext here too
            # We reuse internal dependencies but swap node
            from ..node_context import NodeContext
            ctx_paired = NodeContext(
                builder=builder,
                node=paired_output,
                socket_value_map=socket_value_map,
                get_socket_key=get_socket_key,
                get_socket_value=ctx._get_socket_value,
                extra_ctx=ctx.extra
            )
            
            handler(paired_output, ctx_paired)
            
            if output_socket_needed:
                req_key = get_socket_key(output_socket_needed)
                if req_key in socket_value_map:
                    return socket_value_map[req_key]
            
            if key_iteration in socket_value_map:
                return socket_value_map[key_iteration]
    
    logger.warning(f"RepeatInput '{node.name}' values not available, returning placeholder")
    return builder.constant(0, DataType.INT)


def _find_repeat_output(input_node):
    if hasattr(input_node, 'paired_output') and input_node.paired_output:
        tree = input_node.id_data
        if input_node.paired_output in tree.nodes:
            return tree.nodes[input_node.paired_output]
    return None

def _find_repeat_input(output_node) -> Optional[Any]:
    """Find the paired RepeatInput for a RepeatOutput."""
    if hasattr(output_node, 'paired_input') and output_node.paired_input:
        tree = output_node.id_data
        if output_node.paired_input in tree.nodes:
            return tree.nodes[output_node.paired_input]
    return _search_upstream_repeat_input(output_node)


def _search_upstream_repeat_input(start_node) -> Optional[Any]:
    """Search upstream from a node to find RepeatInput."""
    stack = list(start_node.inputs)
    visited = set()
    
    while stack:
        sock = stack.pop()
        sock_id = id(sock)
        if sock_id in visited:
            continue
        visited.add(sock_id)
        
        if sock.is_linked:
            link = sock.links[0]
            nd = link.from_node
            if nd.bl_idname == 'ComputeNodeRepeatInput':
                return nd
            for inp in nd.inputs:
                stack.append(inp)
    
    return None
