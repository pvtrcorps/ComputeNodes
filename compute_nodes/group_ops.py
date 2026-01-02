import bpy
from .nodes.nodegroup import ComputeNodeGroup, ComputeNodeGroupInput, ComputeNodeGroupOutput

# ============================================================================
# UTILITIES
# ============================================================================

def get_compute_path(context):
    """Retrieve the current path (list of trees) if in Compute context"""
    space = context.space_data
    if space.type != 'NODE_EDITOR' or space.tree_type != 'ComputeNodeTree':
        return None
    return space.path

# ============================================================================
# OPERATORS
# ============================================================================

class COMPUTE_OT_group_make(bpy.types.Operator):
    """Create a Node Group from selected nodes"""
    bl_idname = "compute.group_make"
    bl_label = "Make Group"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        space = context.space_data
        return (space.type == 'NODE_EDITOR' and 
                space.tree_type == 'ComputeNodeTree' and
                context.active_node is not None)

    def execute(self, context):
        tree = context.space_data.edit_tree  # Use edit_tree for nested group support
        selected_nodes = [n for n in tree.nodes if n.select]
        
        if not selected_nodes:
            self.report({'WARNING'}, "No nodes selected")
            return {'CANCELLED'}
        
        # 1. Analyze External Links
        # We need to know which sockets cross the boundary of selection
        node_names = {n.name for n in selected_nodes}
        
        inputs_to_create = []  # (from_node, from_socket, to_node, to_socket_name)
        outputs_to_create = [] # (from_node, from_socket_name, to_node, to_socket)
        
        # 2. Create New Tree
        group_tree = bpy.data.node_groups.new(name=f"NodeGroup", type='ComputeNodeTree')
        
        # 3. Copy Nodes
        # Manual copy to ensure it works in all contexts (nested groups, etc)
        # bpy.ops.node.clipboard_copy() removed as it is context-dependent and manual copy is implemented below
        
        # Switch context conceptually (we don't change UI, just act on new tree)
        # But clipboard_paste acts on context.node_tree
        # So we use an override
        
        # Trick: We can't easily override context.node_tree for paste operator if it relies on SpaceNodeEditor
        # But we can try just deselecting everything in current tree, renaming them to avoid collision? 
        # No, new tree is separate.
        
        # Helper to copy nodes manually since clipboard depends on UI context often
        # Actually clipboard_paste works with 'node_tree' in override usually?
        # Let's try manual copy for safety and control
        
        old_to_new = {} # Map old_node.name -> new_node object
        
        for old_node in selected_nodes:
            # Create new node
            new_node = group_tree.nodes.new(type=old_node.bl_idname)
            new_node.location = old_node.location
            new_node.width = old_node.width
            new_node.height = old_node.height
            new_node.label = old_node.label
            new_node.name = old_node.name # Try to keep name
            
            # Copy Properties (Simple iteration)
            # This is fragile for complex properties but let's assume basic ones
            # For robust copy, we might need more
            try:
                for prop in old_node.bl_rna.properties:
                    if not prop.is_readonly:
                        setattr(new_node, prop.identifier, getattr(old_node, prop.identifier))
            except Exception:
                pass
            
            old_to_new[old_node.name] = new_node

        # 3.5 Fix Repeat Node Pairings (Name references)
        for old_node in selected_nodes:
            if hasattr(old_node, "paired_output") and old_node.paired_output in old_to_new:
                new_node = old_to_new[old_node.name]
                new_node.paired_output = old_to_new[old_node.paired_output].name
                
            if hasattr(old_node, "paired_input") and old_node.paired_input in old_to_new:
                new_node = old_to_new[old_node.name]
                new_node.paired_input = old_to_new[old_node.paired_input].name
            
        # 4. Reconstruct Internal Links
        for old_node in selected_nodes:
            new_node = old_to_new[old_node.name]
            
            for out_sock in old_node.outputs:
                for link in out_sock.links:
                    if link.to_node.name in node_names:
                        # Internal Link
                        to_new_node = old_to_new[link.to_node.name]
                        
                        # Find matching sockets by index/identifier
                        # Assuming sockets match 1:1
                        # Note: Repeat Zone dynamic sockets might range
                        try:
                            # Use index if names might differ? Or name?
                            # Name is safest usually 
                            src = new_node.outputs[out_sock.name]
                            dst = to_new_node.inputs[link.to_socket.name]
                            group_tree.links.new(src, dst)
                        except Exception:
                            pass
        
        # 5. Handle Boundary Links (Inputs)
        # Links: Outside -> Inside
        # We need a Group Input node
        group_input = group_tree.nodes.new("ComputeNodeGroupInput")
        group_input.location = (min(n.location.x for n in selected_nodes) - 300, 
                                sum(n.location.y for n in selected_nodes)/len(selected_nodes))
        
        # 6. Handle Boundary Links (Outputs)
        # Links: Inside -> Outside
        group_output = group_tree.nodes.new("ComputeNodeGroupOutput")
        group_output.location = (max(n.location.x + n.width for n in selected_nodes) + 100, 
                                 sum(n.location.y for n in selected_nodes)/len(selected_nodes))
        
        # Logic to create sockets on interface and link them
        
        # INPUTS
        for old_node in selected_nodes:
            new_node = old_to_new[old_node.name]
            for input_sock in old_node.inputs:
                if input_sock.is_linked:
                    link = input_sock.links[0] # Inputs have 1 link
                    if link.from_node.name not in node_names:
                        # Boundary Crossing: Outside -> Inside
                        # 1. Create Socket in Interface
                        socket_type = input_sock.bl_idname
                        # Map custom types if needed
                        # Use our helper if available, or just guess
                        if 'Grid' in socket_type: s_type = 'ComputeSocketGrid'
                        elif 'Buffer' in socket_type: s_type = 'ComputeSocketBuffer'
                        elif 'Vector' in socket_type: s_type = 'NodeSocketVector'
                        elif 'Color' in socket_type: s_type = 'NodeSocketColor'
                        elif 'Int' in socket_type: s_type = 'NodeSocketInt'
                        elif 'Bool' in socket_type: s_type = 'NodeSocketBool'
                        else: s_type = 'NodeSocketFloat'
                        
                        sock_name = input_sock.name
                        item = group_tree.interface.new_socket(sock_name, in_out='INPUT', socket_type=s_type)
                        
                        # 2. Sync Group Input
                        group_input.sync_from_interface()
                        
                        # 3. Link Group Input -> New Node
                        if item.name in group_input.outputs:
                            group_tree.links.new(group_input.outputs[item.name], new_node.inputs[input_sock.name])
                            
                        # 4. Store info to link Outside later
                        inputs_to_create.append({
                            'socket_name': item.name,
                            'from_node': link.from_node,
                            'from_socket': link.from_socket
                        })

        # OUTPUTS
        for old_node in selected_nodes:
            new_node = old_to_new[old_node.name]
            for output_sock in old_node.outputs:
                for link in output_sock.links:
                    if link.to_node.name not in node_names:
                        # Boundary Crossing: Inside -> Outside
                        # 1. Create Socket in Interface (if not already for this output?)
                        # Actually we might have multiple links from same output going to different outside nodes
                        # We only need 1 Interface Socket per Internal Output
                        
                        # Check if we already mapped this internal output?
                        # Use a map: old_sock_unique_id -> interface_name
                        # For simplicity, let's create a socket for each usage or reuse?
                        # Standard behavior: One group output per internal socket used externally.
                        
                        # Key: (old_node, output_sock)
                        
                        socket_type = output_sock.bl_idname
                        if 'Grid' in socket_type: s_type = 'ComputeSocketGrid'
                        elif 'Buffer' in socket_type: s_type = 'ComputeSocketBuffer'
                        elif 'Vector' in socket_type: s_type = 'NodeSocketVector'
                        elif 'Color' in socket_type: s_type = 'NodeSocketColor'
                        else: s_type = 'NodeSocketFloat'

                        # Create Interface Socket
                        sock_name = output_sock.name
                        item = group_tree.interface.new_socket(sock_name, in_out='OUTPUT', socket_type=s_type)
                        
                        # Sync Group Output
                        group_output.sync_from_interface()
                        
                        # Link New Node -> Group Output
                        if item.name in group_output.inputs:
                            group_tree.links.new(new_node.outputs[output_sock.name], group_output.inputs[item.name])
                            
                        # Store info to link Outside later (multiple links possible)
                        outputs_to_create.append({
                            'socket_name': item.name,
                            'to_node': link.to_node,
                            'to_socket': link.to_socket
                        })

        # 7. Create Group Node in Parent Tree
        group_node = tree.nodes.new("ComputeNodeGroup")
        group_node.node_tree = group_tree
        group_node.location = (sum(n.location.x for n in selected_nodes)/len(selected_nodes),
                               sum(n.location.y for n in selected_nodes)/len(selected_nodes))
        
        # 8. Reconnect Outside Links
        # INPUTS (Parent -> Group Node)
        for info in inputs_to_create:
            if info['socket_name'] in group_node.inputs:
                tree.links.new(info['from_socket'], group_node.inputs[info['socket_name']])
        
        # OUTPUTS (Group Node -> Parent)
        for info in outputs_to_create:
            if info['socket_name'] in group_node.outputs:
                tree.links.new(group_node.outputs[info['socket_name']], info['to_socket'])
        
        # 9. Cleanup Old Nodes
        for n in selected_nodes:
            tree.nodes.remove(n)
            
        # Select the group node
        group_node.select = True
        tree.nodes.active = group_node
        
        return {'FINISHED'}


class COMPUTE_OT_group_ungroup(bpy.types.Operator):
    """Ungroup selected Group Node"""
    bl_idname = "compute.group_ungroup"
    bl_label = "Ungroup"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        space = context.space_data
        return (space.type == 'NODE_EDITOR' and 
                space.tree_type == 'ComputeNodeTree' and
                context.active_node and 
                isinstance(context.active_node, ComputeNodeGroup))

    def execute(self, context):
        tree = context.space_data.edit_tree  # Use edit_tree for nested group support
        group_node = context.active_node
        inner_tree = group_node.node_tree
        
        if not inner_tree:
            return {'CANCELLED'}
        
        # 1. Map Interface Nodes
        # Find Group Input and Output nodes inside
        group_inputs = [n for n in inner_tree.nodes if isinstance(n, ComputeNodeGroupInput)]
        group_outputs = [n for n in inner_tree.nodes if isinstance(n, ComputeNodeGroupOutput)]
        
        # 2. Copy Nodes to Parent
        old_to_new = {}
        nodes_to_copy = [n for n in inner_tree.nodes 
                         if not isinstance(n, (ComputeNodeGroupInput, ComputeNodeGroupOutput))]
        
        offset = group_node.location
        
        for old_node in nodes_to_copy:
            new_node = tree.nodes.new(type=old_node.bl_idname)
            new_node.location = old_node.location + offset
            new_node.width = old_node.width
            new_node.height = old_node.height
            new_node.label = old_node.label
            
             # Copy props
            try:
                for prop in old_node.bl_rna.properties:
                    if not prop.is_readonly:
                        setattr(new_node, prop.identifier, getattr(old_node, prop.identifier))
            except Exception:
                pass
            
            old_to_new[old_node.name] = new_node
            
        # 2.5 Fix Repeat Node Pairings (Name references)
        for old_node in nodes_to_copy:
            if hasattr(old_node, "paired_output") and old_node.paired_output in old_to_new:
                new_node = old_to_new[old_node.name]
                new_node.paired_output = old_to_new[old_node.paired_output].name
                
            if hasattr(old_node, "paired_input") and old_node.paired_input in old_to_new:
                new_node = old_to_new[old_node.name]
                new_node.paired_input = old_to_new[old_node.paired_input].name

        # 3. Reconstruct Internal Links
        for old_node in nodes_to_copy:
            new_node = old_to_new[old_node.name]
            for out_sock in old_node.outputs:
                for link in out_sock.links:
                    if link.to_node.name in old_to_new:
                        to_new_node = old_to_new[link.to_node.name]
                        try:
                            tree.links.new(new_node.outputs[out_sock.name], 
                                           to_new_node.inputs[link.to_socket.name])
                        except: pass

        # 4. Reconnect External Inputs (Parent -> Inside Nodes)
        # Iterate Group Input links inside
        for g_input in group_inputs:
            for out_sock in g_input.outputs:
                if out_sock.name == "Empty": continue
                # Find matching input on Group Node
                if out_sock.name in group_node.inputs:
                    g_input_sock = group_node.inputs[out_sock.name]
                    if g_input_sock.is_linked:
                        external_source = g_input_sock.links[0].from_socket
                        
                        # Where does it go inside?
                        for link in out_sock.links:
                            if link.to_node.name in old_to_new:
                                to_node_real = old_to_new[link.to_node.name]
                                tree.links.new(external_source, to_node_real.inputs[link.to_socket.name])

        # 5. Reconnect External Outputs (Inside Nodes -> Parent)
        # Iterate Group Output links inside
        for g_output in group_outputs:
            for in_sock in g_output.inputs:
                if in_sock.name == "Empty": continue
                
                if in_sock.is_linked:
                    internal_source_link = in_sock.links[0]
                    if internal_source_link.from_node.name in old_to_new:
                        real_source_node = old_to_new[internal_source_link.from_node.name]
                        real_source_socket = real_source_node.outputs[internal_source_link.from_socket.name]
                        
                        # Connect to whatever Group Node was outputting to
                        if in_sock.name in group_node.outputs:
                            g_out_sock = group_node.outputs[in_sock.name]
                            for link in g_out_sock.links:
                                tree.links.new(real_source_socket, link.to_socket)

        # 6. Cleanup
        tree.nodes.remove(group_node)
        
        # Select new nodes
        for n in old_to_new.values():
            n.select = True
            
        return {'FINISHED'}


class COMPUTE_OT_group_action(bpy.types.Operator):
    """Enter Group on Double Click, or Exit if Background"""
    bl_idname = "compute.group_action"
    bl_label = "Group Action"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Check context
        space = context.space_data
        if space.type != 'NODE_EDITOR': return {'PASS_THROUGH'}
        
        # Logic:
        # If node is active and selected -> Enter
        # If no node selected (background click?) -> Exit
        
        active = context.active_node
        selected = context.selected_nodes
        
        if active and active.select and isinstance(active, ComputeNodeGroup):
            # ENTER GROUP
            # Native way to enter group:
            if active.node_tree:
                space.path.append(active.node_tree, node=active)
                return {'FINISHED'}
        
        elif not selected and len(space.path) > 1:
            # EXIT GROUP (Go Up)
            space.path.pop()
            return {'FINISHED'}
            
        return {'PASS_THROUGH'}


classes = (
    COMPUTE_OT_group_make,
    COMPUTE_OT_group_ungroup,
    COMPUTE_OT_group_action,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
