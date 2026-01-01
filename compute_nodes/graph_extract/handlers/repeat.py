# Repeat Zone Handlers - Multi-pass loop support
#
# Handles: ComputeNodeRepeatInput, ComputeNodeRepeatOutput
#
# Architecture:
# - RepeatInput provides "Current" values from ping-pong buffer
# - RepeatOutput collects "Next" values and writes to output buffer
# - PASS_LOOP_BEGIN/END mark the loop region for scheduler
# - Scheduler creates PassLoop with ping-pong buffer pairs

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
    
    This is a thin wrapper around _trace_resource_index that returns
    the actual ResourceDesc instead of just the index.
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
    
    Emits:
    - PASS_LOOP_BEGIN with loop metadata
    - Values for each state variable (from ping-pong buffers)
    - PASS_LOOP_END after body processing
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    
    # Find paired RepeatInput
    repeat_input = _find_repeat_input(node)
    
    if not repeat_input:
        logger.warning(f"Repeat Output '{node.name}' has no paired Repeat Input")
        return builder.constant(0.0, DataType.FLOAT)
    
    # Get iteration count
    val_iters = get_socket_value(repeat_input.inputs["Iterations"])
    if val_iters is None:
        val_iters = builder.constant(10, DataType.INT)
    val_iters = builder.cast(val_iters, DataType.INT)
    
    # Build state variable descriptors
    state_vars = []
    repeat_items = list(repeat_input.repeat_items)
    
    for i, item in enumerate(repeat_items):
        # Socket names now use just the item name (no prefixes)
        # RepeatInput: inputs use item.name, outputs use item.name
        # RepeatOutput: inputs use item.name, outputs use item.name
        socket_name = item.name
        
        val_initial = None
        if socket_name in repeat_input.inputs:
            val_initial = get_socket_value(repeat_input.inputs[socket_name])
        
        # Determine data type
        # socket_type uses Blender socket bl_idnames (e.g. 'ComputeSocketGrid', 'NodeSocketFloat')
        is_grid = item.socket_type == 'ComputeSocketGrid'
        
        # GRID-ONLY VALIDATION
        # Multi-pass GPU loops can only pass Grid state between iterations
        # Fields/scalars cannot be serialized between separate shader programs
        if not is_grid:
            raise ValueError(
                f"Repeat zone state '{item.name}' must be a Grid (got {item.socket_type}).\n"
                f"Multi-pass GPU loops cannot pass Fields or scalar values between iterations.\n"
                f"Each iteration runs as a separate shader with no shared variables.\n\n"
                f"Solution: Use Capture to convert Field → Grid before the loop:\n"
                f"  Noise → Capture → Repeat Input ✅\n"
                f"  Noise → Repeat Input ❌\n\n"
                f"See GEMINI.md for details on Grid vs Field architecture."
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
            # Get size and format from initial (trace through origin chain if needed)
            source_resource = _find_source_resource(val_initial, builder.graph)
            
            if source_resource:
                size = source_resource.size
                dims = source_resource.dimensions
                # Inherit format from source (no more hardcoded RGBA32F)
                fmt = getattr(source_resource, 'format', 'RGBA32F')
                
                # Store format in state for executor
                state.format = fmt
                
                # Create ping-pong buffer pair with inherited format
                desc_ping = ImageDesc(
                    name=f"loop_{node.name}_{item.name}_ping",
                    access=ResourceAccess.READ_WRITE,
                    format=fmt,
                    size=size,
                    dimensions=dims,
                    is_internal=True
                )
                desc_pong = ImageDesc(
                    name=f"loop_{node.name}_{item.name}_pong",
                    access=ResourceAccess.READ_WRITE,
                    format=fmt,
                    size=size,
                    dimensions=dims,
                    is_internal=True
                )
                
                val_ping = builder.add_resource(desc_ping)
                val_pong = builder.add_resource(desc_pong)
                
                state.ping_idx = val_ping.resource_index
                state.pong_idx = val_pong.resource_index
                state.size = size
                state.dimensions = dims
        
        state_vars.append(state)
    
    # Emit PASS_LOOP_BEGIN
    loop_metadata = {
        'iterations': val_iters,
        'state_vars': state_vars,
        'repeat_input_name': repeat_input.name,
        'repeat_output_name': node.name,
    }
    
    op_begin = builder.add_op(OpCode.PASS_LOOP_BEGIN, [val_iters])
    op_begin.metadata = loop_metadata
    
    # Create output values for RepeatInput's Current sockets
    val_iteration = builder._new_value(ValueKind.SSA, DataType.INT, origin=op_begin)
    op_begin.add_output(val_iteration)
    
    # Map Iteration output
    key_iteration = get_socket_key(repeat_input.outputs["Iteration"])
    socket_value_map[key_iteration] = val_iteration
    
    # Create read values for each state variable (all Grids now)
    for state in state_vars:
        # Grid: emit PASS_LOOP_READ that references ping buffer
        op_read = builder.add_op(OpCode.PASS_LOOP_READ, [])
        op_read.metadata = {'state_index': state.index, 'state_name': state.name}
        
        val_current = builder._new_value(ValueKind.SSA, DataType.HANDLE, origin=op_read)
        if state.ping_idx is not None:
            val_current.resource_index = state.ping_idx
        op_read.add_output(val_current)
        
        # Map to Current socket (same name on output)
        current_key = get_socket_key(repeat_input.outputs[state.socket_name])
        socket_value_map[current_key] = val_current
        state.current_value = val_current
    
    # Now process the body (get values flowing into Next sockets)
    for state in state_vars:
        val_next = None
        if state.socket_name in node.inputs:
            val_next = get_socket_value(node.inputs[state.socket_name])
        
        if val_next is None:
            val_next = state.current_value
        
        if val_next is None:
            val_next = builder.constant(0.0, state.data_type)
        
        # For Grid states: if the "next" value comes from a different resource,
        # we need to copy it to the pong buffer. This happens when e.g. Blur
        # creates its own output resource.
        if state.is_grid and state.pong_idx is not None:
            if val_next.resource_index is not None and val_next.resource_index != state.pong_idx:
                # Need to copy from blur output to pong buffer
                logger.debug(f"Adding copy: resource {val_next.resource_index} -> pong {state.pong_idx}")
                
                # Create pong resource value
                pong_val = builder._new_value(ValueKind.SSA, DataType.HANDLE)
                pong_val.resource_index = state.pong_idx
                
                # Add IMAGE_STORE to copy - using the sample+store pattern
                # Actually, we should create a proper COPY op or use the blur directly
                # For now, mark that the pong should mirror the blur output
                # The executor will handle this via the val_next -> pong mapping
                state.copy_from_resource = val_next.resource_index
        
        state.next_value = val_next
    
    # Emit PASS_LOOP_END
    next_values = [s.next_value for s in state_vars]
    op_end = builder.add_op(OpCode.PASS_LOOP_END, next_values)
    op_end.metadata = loop_metadata
    
    # Create output values for Final sockets (same name on output)
    results = {}
    for i, state in enumerate(state_vars):
        val_final = builder._new_value(ValueKind.SSA, state.data_type, origin=op_end)
        op_end.add_output(val_final)
        
        if state.is_grid and state.pong_idx is not None:
            val_final.resource_index = state.pong_idx
        
        # Map to Final socket (same name on RepeatOutput output)
        final_key = get_socket_key(node.outputs[state.socket_name])
        socket_value_map[final_key] = val_final
        results[state.name] = val_final
    
    # Return the requested output value (based on which Final socket was asked for)
    output_socket_needed = ctx.get('output_socket_needed')
    if output_socket_needed:
        # Find which state matches the requested socket
        for state in state_vars:
            if state.socket_name == output_socket_needed.name:
                return results.get(state.name)
    
    # Fallback: return first output
    if state_vars:
        return results.get(state_vars[0].name)
    return None


def handle_repeat_input(node, ctx):
    """
    Handle ComputeNodeRepeatInput node.
    
    This is called when a node needs values from RepeatInput's outputs.
    Since loops are processed from Output backwards, we need to ensure
    the RepeatOutput has been processed first to populate socket values.
    
    If not processed yet, we trigger processing of the paired RepeatOutput.
    """
    builder = ctx['builder']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    get_socket_value = ctx['get_socket_value']
    output_socket_needed = ctx.get('output_socket_needed')  # Which output socket was requested
    
    # Check if values are already mapped (RepeatOutput was processed)
    key_iteration = get_socket_key(node.outputs["Iteration"])
    
    if key_iteration in socket_value_map:
        # Already processed - return the requested socket value
        if output_socket_needed:
            req_key = get_socket_key(output_socket_needed)
            if req_key in socket_value_map:
                return socket_value_map[req_key]
        return socket_value_map[key_iteration]
    
    # Not yet processed - we need to process the paired RepeatOutput first
    # Find and process the RepeatOutput
    paired_output = None
    if hasattr(node, 'paired_output') and node.paired_output:
        tree = node.id_data
        if node.paired_output in tree.nodes:
            paired_output = tree.nodes[node.paired_output]
    
    if paired_output:
        # Process RepeatOutput - this will populate socket_value_map
        from ..registry import get_handler
        handler = get_handler(paired_output.bl_idname)
        if handler:
            logger.debug(f"Triggering RepeatOutput processing from RepeatInput")
            handler(paired_output, ctx)
            
            # Now check if our requested socket is available
            if output_socket_needed:
                req_key = get_socket_key(output_socket_needed)
                if req_key in socket_value_map:
                    return socket_value_map[req_key]
            
            # Return Iteration if available
            if key_iteration in socket_value_map:
                return socket_value_map[key_iteration]
    
    # Fallback: return placeholder
    logger.warning(f"RepeatInput '{node.name}' values not available, returning placeholder")
    return builder.constant(0, DataType.INT)


def _find_repeat_input(output_node) -> Optional[Any]:
    """Find the paired RepeatInput for a RepeatOutput."""
    # First check the pairing property
    if hasattr(output_node, 'paired_input') and output_node.paired_input:
        tree = output_node.id_data
        if output_node.paired_input in tree.nodes:
            return tree.nodes[output_node.paired_input]
    
    # Fallback: search upstream
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


def _socket_type_to_datatype(socket_type: str) -> DataType:
    """Convert repeat item socket_type to DataType.
    
    socket_type uses Blender socket bl_idnames, not short names.
    """
    mapping = {
        # Blender socket bl_idnames
        'NodeSocketFloat': DataType.FLOAT,
        'NodeSocketVector': DataType.VEC3,
        'NodeSocketColor': DataType.VEC4,
        'ComputeSocketGrid': DataType.HANDLE,
        'NodeSocketInt': DataType.INT,
    }
    return mapping.get(socket_type, DataType.FLOAT)
