# Node Groups - ComputeNodeGroup, GroupInput, GroupOutput
# Complete implementation with dynamic socket add/remove
import bpy
from bpy.props import PointerProperty, StringProperty, CollectionProperty, BoolProperty, IntProperty
from .base import ComputeNode
from ..sockets import ComputeSocketGrid


# ============================================================================
# OPERATOR: Remove Socket from GroupInput/GroupOutput
# ============================================================================

class COMPUTE_OT_remove_group_socket(bpy.types.Operator):
    """Remove a socket from Group Input/Output node"""
    bl_idname = "compute.remove_group_socket"
    bl_label = "Remove Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    node_name: StringProperty()
    socket_index: IntProperty()
    socket_type: StringProperty()  # "INPUT" or "OUTPUT"
    tree_name: StringProperty()
    
    def execute(self, context):
        # Find the node tree
        tree = bpy.data.node_groups.get(self.tree_name)
        if not tree:
            self.report({'ERROR'}, f"Tree '{self.tree_name}' not found")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if not node:
            self.report({'ERROR'}, f"Node '{self.node_name}' not found")
            return {'CANCELLED'}
        
        sockets = node.inputs if self.socket_type == "INPUT" else node.outputs
        
        if self.socket_index < 0 or self.socket_index >= len(sockets):
            self.report({'ERROR'}, "Invalid socket index")
            return {'CANCELLED'}
        
        socket = sockets[self.socket_index]
        
        # Don't allow removing the "Empty" socket
        if socket.name == "Empty":
            self.report({'WARNING'}, "Cannot remove the Empty socket")
            return {'CANCELLED'}
        
        # Remove the socket
        sockets.remove(socket)
        
        # Notify parent groups to update
        if hasattr(node, '_notify_parent_groups'):
            node._notify_parent_groups()
        
        return {'FINISHED'}


# ============================================================================
# COMPUTE NODE GROUP
# ============================================================================

class ComputeNodeGroup(ComputeNode):
    """
    Node Group - References another ComputeNodeTree.
    Sockets are synced from the referenced tree's GroupInput/GroupOutput nodes.
    """
    bl_idname = 'ComputeNodeGroup'
    bl_label = 'Group'
    bl_icon = 'NODETREE'
    node_category = "GROUPS"
    
    def poll_compute_trees(self, node_tree):
        """Only show ComputeNodeTree and exclude self"""
        return (node_tree.bl_idname == 'ComputeNodeTree' and 
                node_tree != getattr(self, "id_data", None))
    
    node_tree: PointerProperty(
        type=bpy.types.NodeTree,
        name="Node Tree",
        poll=poll_compute_trees,
        update=lambda self, ctx: self.update_sockets()
    )
    
    def init(self, context):
        self.apply_node_color()
        pass
    
    def draw_buttons(self, context, layout):
        layout.template_ID(self, "node_tree", new="node.new_compute_tree")
    
    def draw_label(self):
        self._draw_node_color()
        if self.node_tree:
            return self.node_tree.name
        return "Group"
    

    def update_sockets(self):
        """Sync sockets with referenced tree's Interface."""
        if not self.node_tree:
            self.inputs.clear()
            self.outputs.clear()
            return
        
        # Save existing links
        saved_links_in = {}
        saved_links_out = {}
        
        for inp in self.inputs:
            if inp.is_linked:
                link = inp.links[0]
                saved_links_in[inp.name] = (link.from_node.name, link.from_socket.name)
        
        for out in self.outputs:
            for link in out.links:
                if out.name not in saved_links_out:
                    saved_links_out[out.name] = []
                saved_links_out[out.name].append((link.to_node.name, link.to_socket.name))
        
        # Clear and recreate from Interface
        self.inputs.clear()
        self.outputs.clear()
        
        interface = self.node_tree.interface
        
        # Inputs from Interface Inputs
        for item in interface.items_tree:
            if item.item_type == 'SOCKET':
                socket_type = self._map_socket_type(item.socket_type)
                if item.in_out == 'INPUT':
                    self.inputs.new(socket_type, item.name)
                elif item.in_out == 'OUTPUT':
                    self.outputs.new(socket_type, item.name)
        
        # Restore links
        tree = self.id_data
        for name, (from_node, from_socket) in saved_links_in.items():
            if name in self.inputs:
                node = tree.nodes.get(from_node)
                if node and from_socket in node.outputs:
                    tree.links.new(node.outputs[from_socket], self.inputs[name])
        
        for name, targets in saved_links_out.items():
            if name in self.outputs:
                for to_node, to_socket in targets:
                    node = tree.nodes.get(to_node)
                    if node and to_socket in node.inputs:
                        tree.links.new(self.outputs[name], node.inputs[to_socket])

    def _map_socket_type(self, interface_type):
        """Map Blender interface socket type to our socket types."""
        # Generic mapping, expanded as needed
        if 'Vector' in interface_type: return 'NodeSocketVector'
        if 'Color' in interface_type: return 'NodeSocketColor'
        if 'Int' in interface_type: return 'NodeSocketInt'
        if 'Bool' in interface_type: return 'NodeSocketBool'
        return 'ComputeSocketGrid' # Default to Float/Grid


# ============================================================================
# GROUP INPUT NODE
# ============================================================================

class ComputeNodeGroupInput(ComputeNode):
    """
    Group Input - Exposes inputs inside a group.
    Syncs with tree.interface inputs.
    """
    bl_idname = 'ComputeNodeGroupInput'
    bl_label = 'Group Input'
    bl_icon = 'IMPORT'
    node_category = "GROUPS"
    
    def init(self, context):
        self.apply_node_color()
        self._ensure_empty_socket()
        self.sync_from_interface()
    
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
    
    def sync_from_interface(self):
        """Rebuild outputs from tree.interface inputs."""
        tree = self.id_data
        if not tree: return
        
        # We need to preserve the "Empty" socket at the end
        # And preserve links on existing sockets if possible (by name match)
        
        # Current sockets (excluding Empty)
        current_sockets = [s for s in self.outputs if s.name != "Empty"]
        
        # Interface Inputs
        interface_inputs = [item for item in tree.interface.items_tree 
                           if item.item_type == 'SOCKET' and item.in_out == 'INPUT']
        
        # Naive rebuild: Clear all except Empty? 
        # Better: Check diff. For MVP, we clear and rebuild but save links.
        
        saved_links = {}
        for sock in self.outputs:
            if sock.name != "Empty" and sock.is_linked:
                 saved_links[sock.name] = []
                 for link in sock.links:
                     saved_links[sock.name].append((link.to_node.name, link.to_socket.name))
        
        self.outputs.clear()
        
        for item in interface_inputs:
            # Our mapping: Interface INPUT -> Node OUTPUT
            # socket_type mapping might need refinement
            stype = 'NodeSocketFloat' # Default
            if 'Vector' in item.socket_type: stype = 'NodeSocketVector'
            
            sock = self.outputs.new(stype, item.name)
            
            # Restore links
            if item.name in saved_links:
                for to_node, to_socket in saved_links[item.name]:
                     node = tree.nodes.get(to_node)
                     if node and to_socket in node.inputs:
                         tree.links.new(sock, node.inputs[to_socket])
                         
        self._ensure_empty_socket()

    def _ensure_empty_socket(self):
        if not self.outputs or self.outputs[-1].name != "Empty":
            self.outputs.new('NodeSocketFloat', "Empty")
    
    def draw_socket(self, context, layout, socket, text):
        row = layout.row(align=True)
        if socket.name != "Empty":
            # Delete via Interface API (custom operator wrapper)
            op = row.operator("compute.remove_group_socket_interface", text="", icon="X", emboss=False)
            op.socket_name = socket.name
            op.socket_type = "INPUT"
        row.label(text=text)
    
    def update(self):
        """Called when links change. Handle dynamic socket creation."""
        self._handle_dynamic_sockets()
        

    def _handle_dynamic_sockets(self):
        """If Empty linked -> Add to Interface."""
        if not self.outputs: return
        last = self.outputs[-1]
        
        if last.name == "Empty" and last.is_linked:
            link = last.links[0]
            to_socket = link.to_socket
            
            # Add to Interface
            interface = self.id_data.interface
            new_idx = len(interface.items_tree)
            
            # Determine type
            stype = 'NodeSocketFloat'
            if to_socket and 'Vector' in to_socket.bl_idname: stype = 'NodeSocketVector'
            
            item = interface.new_socket(f"Input {new_idx}", in_out='INPUT', socket_type=stype)
            
            # Force sync (this node)
            self.sync_from_interface()
            
            # Re-link
            new_socket = self.outputs[item.name]
            tree = self.id_data
            if tree:
                tree.links.new(new_socket, to_socket)

            # Update parent groups
            update_parent_groups(self.id_data)


# ============================================================================
# GROUP OUTPUT NODE
# ============================================================================

class ComputeNodeGroupOutput(ComputeNode):
    """
    Group Output - Exposes outputs inside a group.
    Syncs with tree.interface outputs.
    """
    bl_idname = 'ComputeNodeGroupOutput'
    bl_label = 'Group Output'
    bl_icon = 'EXPORT'
    node_category = "GROUPS"
    
    is_active_output: BoolProperty(default=True)
    
    def init(self, context):
        self.apply_node_color()
        self._ensure_empty_socket()
        self.sync_from_interface()
        
    def draw_label(self):
        self._draw_node_color()
        return self.bl_label
        
    def sync_from_interface(self):
        tree = self.id_data
        if not tree: return
        
        # Save links
        saved_links = {}
        for sock in self.inputs:
            if sock.name != "Empty" and sock.is_linked:
                 link = sock.links[0]
                 saved_links[sock.name] = (link.from_node.name, link.from_socket.name)

        self.inputs.clear()
        
        interface_outputs = [item for item in tree.interface.items_tree 
                           if item.item_type == 'SOCKET' and item.in_out == 'OUTPUT']
        
        for item in interface_outputs:
            stype = 'NodeSocketFloat'
            if 'Vector' in item.socket_type: stype = 'NodeSocketVector'
            
            sock = self.inputs.new(stype, item.name)
            
            if item.name in saved_links:
                from_node, from_socket = saved_links[item.name]
                node = tree.nodes.get(from_node)
                if node and from_socket in node.outputs:
                    tree.links.new(node.outputs[from_socket], sock)

        self._ensure_empty_socket()
        
    def _ensure_empty_socket(self):
        if not self.inputs or self.inputs[-1].name != "Empty":
            self.inputs.new('NodeSocketFloat', "Empty")

    def draw_socket(self, context, layout, socket, text):
        row = layout.row(align=True)
        if socket.name != "Empty":
            op = row.operator("compute.remove_group_socket_interface", text="", icon="X", emboss=False)
            op.socket_name = socket.name
            op.socket_type = "OUTPUT"
        row.label(text=text)

    def update(self):
        self._handle_dynamic_sockets()

    def _handle_dynamic_sockets(self):
        if not self.inputs: return
        last = self.inputs[-1]
        
        if last.name == "Empty" and last.is_linked:
            link = last.links[0]
            from_socket = link.from_socket
            
            interface = self.id_data.interface
            new_idx = len(interface.items_tree)
            
            stype = 'NodeSocketFloat'
            if from_socket and 'Vector' in from_socket.bl_idname: stype = 'NodeSocketVector'
            
            item = interface.new_socket(f"Output {new_idx}", in_out='OUTPUT', socket_type=stype)
            
            self.sync_from_interface()
            
            new_socket = self.inputs[item.name]
            tree = self.id_data
            if tree:
                tree.links.new(from_socket, new_socket)
            
            # Update parent groups
            update_parent_groups(self.id_data)





def update_parent_groups(inner_tree):
    """
    Find all ComputeNodeGroup nodes referencing inner_tree and update their sockets.
    This ensures that changes to the interface are propagated to parent groups.
    """
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'ComputeNodeTree':
            for node in tree.nodes:
                if isinstance(node, ComputeNodeGroup) and node.node_tree == inner_tree:
                    node.update_sockets()

class COMPUTE_OT_remove_group_socket_interface(bpy.types.Operator):
    """Remove a socket from the Group Interface"""
    bl_idname = "compute.remove_group_socket_interface"
    bl_label = "Remove Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    socket_name: StringProperty()
    socket_type: StringProperty()  # "INPUT" or "OUTPUT"
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree:
            return {'CANCELLED'}
        
        # Remove from Interface
        interface = tree.interface
        item = interface.items_tree.get(self.socket_name)
        if item:
            interface.remove(item)
            
            # Force update of GroupInput/GroupOutput nodes in this tree
            for node in tree.nodes:
                if isinstance(node, (ComputeNodeGroupInput, ComputeNodeGroupOutput)):
                    node.sync_from_interface()
            
            # Update parent groups
            update_parent_groups(tree)
            
            return {'FINISHED'}
        
        return {'CANCELLED'}


# ============================================================================
# REGISTRATION
# ============================================================================

node_classes = [
    ComputeNodeGroup,
    ComputeNodeGroupInput,
    ComputeNodeGroupOutput,
]

operator_classes = [
    COMPUTE_OT_remove_group_socket,
    COMPUTE_OT_remove_group_socket_interface,
]

def register():
    # Only register operators here - nodes are registered via the main classes list
    for cls in operator_classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(operator_classes):
        bpy.utils.unregister_class(cls)

