# Repeat Zone Nodes - Dynamic sockets for iterative simulations
# 
# Architecture:
# - RepeatInput: Entry point with Iterations + dynamic state pairs
# - RepeatOutput: Exit point with matching state pairs
# - Extension socket pattern for Blender-like UX
# - Paired nodes linked via pointer property

import bpy
from bpy.props import (
    IntProperty, 
    StringProperty, 
    EnumProperty,
    CollectionProperty,
    PointerProperty,
)
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid, ComputeSocketEmpty
from ..utils.sockets import with_sync_guard


# =============================================================================
# PropertyGroup for Repeat State Items
# =============================================================================

def update_repeat_item_name(self, context):
    """Callback when a repeat state name changes."""
    # Find the node that owns this item
    # Since we can't easily get the owner from PropertyGroup, we assume
    # the active node is the one being edited (or its pair)
    node = context.active_node
    if not node:
        return

    # If we are editing via the Output node, switch to Input node (Source of Truth)
    if node.bl_idname == 'ComputeNodeRepeatOutput':
        if node.paired_input and node.paired_input in node.id_data.nodes:
            node = node.id_data.nodes[node.paired_input]
    
    # Verify this item belongs to the node
    index = -1
    for i, item in enumerate(node.repeat_items):
        if item == self:
            index = i
            break
    
    if index == -1:
        return
        
    # Rename sockets on Input Node (preserving links)
    # Input Node: [Iterations, Item0, Item1... Empty]
    if 1 + index < len(node.inputs) - 1:
        node.inputs[1 + index].name = self.name
    
    # Input Node Outputs: [Iteration, Item0, Item1... Empty]
    if 1 + index < len(node.outputs) - 1:
        node.outputs[1 + index].name = self.name
        
    # Sync to Paired Output Node
    if node.paired_output and node.paired_output in node.id_data.nodes:
        pair = node.id_data.nodes[node.paired_output]
        
        # Update Pair Item Name (Mirror)
        if index < len(pair.repeat_items):
            # Avoid recursion if name is already set
            if pair.repeat_items[index].name != self.name:
                pair.repeat_items[index].name = self.name
                
        # Rename Pair Sockets
        # Output Node: [Item0... Empty] (No Iterations input)
        if index < len(pair.inputs) - 1:
            pair.inputs[index].name = self.name
            
        if index < len(pair.outputs) - 1:
            pair.outputs[index].name = self.name


class ComputeRepeatItem(bpy.types.PropertyGroup):
    """A single state variable in a Repeat Zone."""
    
    name: StringProperty(
        name="Name",
        default="State",
        description="Name of this state variable",
        update=update_repeat_item_name
    )

    
    socket_type: EnumProperty(
        name="Type",
        items=[
            ('NodeSocketFloat', "Float", "Scalar value"),
            ('NodeSocketVector', "Vector", "3D vector"),
            ('NodeSocketColor', "Color", "RGBA color"),
            ('ComputeSocketGrid', "Grid", "GPU texture buffer"),
        ],
        default='NodeSocketFloat',
        description="Data type for this state"
    )

# =============================================================================
# Repeat Input Node
# =============================================================================

# =============================================================================
# Repeat Input Node
# =============================================================================

class ComputeNodeRepeatInput(ComputeNode):
    """Repeat Zone (Input) - Start of an iterative loop.
    
    Supports N state variables that persist across iterations.
    States can be Float, Vector, Color, or Grid (with ping-pong).
    
    UX Pattern:
    - Drag a connection to the extension socket to add new state
    - Use N-panel to manage states when node is selected
    """
    
    bl_idname = 'ComputeNodeRepeatInput'
    bl_label = 'Repeat Zone (Input)'
    bl_icon = 'LOOP_FORWARDS'
    node_category = "CONTROL"
    
    # Collection of state items
    repeat_items: CollectionProperty(type=ComputeRepeatItem)
    
    # Active item index for UI
    active_index: IntProperty(default=0)
    
    # Pointer to paired output node (stored by name for serialization)
    paired_output: StringProperty(
        name="Paired Output",
        default="",
        description="Name of the paired Repeat Output node"
    )
    
    def init(self, context):
        # Fixed: Iterations input
        iter_socket = self.inputs.new('NodeSocketInt', "Iterations")
        iter_socket.default_value = 10
        # Note: NodeSocketInt doesn't have min_value, use subtype or clamp in handler
        
        # Fixed: Iteration counter output
        self.outputs.new('NodeSocketInt', "Iteration")
        
        # Extension socket (blank, for drag-to-add) - added last
        self._ensure_extension_socket()
    
    def _ensure_extension_socket(self):
        """Add the special extension socket for drag-to-add pattern."""
        # Input side Empty
        if not self.inputs or self.inputs[-1].bl_idname != 'ComputeSocketEmpty':
            self.inputs.new('ComputeSocketEmpty', "Empty")
        
        # Output side Empty (for connecting Current values)
        if not self.outputs or self.outputs[-1].bl_idname != 'ComputeSocketEmpty':
            self.outputs.new('ComputeSocketEmpty', "Empty")
    
    def _make_unique_name(self, base_name):
        """Ensure name is unique among repeat_items."""
        existing = {item.name for item in self.repeat_items}
        if base_name not in existing:
            return base_name
        
        # Add number suffix like Blender does
        i = 1
        while True:
            new_name = f"{base_name}.{i:03d}"
            if new_name not in existing:
                return new_name
            i += 1
            
    def draw_socket(self, context, layout, socket, text):
        if socket.bl_idname == 'ComputeSocketEmpty':
            layout.label(text="")
            return
        layout.label(text=text)
    
    def _is_extension_socket(self, socket):
        """Check if socket is the extension socket."""
        return socket.bl_idname == 'ComputeSocketEmpty'
    
    def _get_extension_socket(self, is_output=False):
        """Find the extension socket."""
        sockets = self.outputs if is_output else self.inputs
        if sockets and sockets[-1].bl_idname == 'ComputeSocketEmpty':
            return sockets[-1]
        return None
    
    def update(self):
        """Called when node connections change."""
        # Check BOTH input and output extension sockets
        # Input Empty: for connecting Initial values
        # Output Empty: for connecting Current values (inside loop)
        
        for is_output in [False, True]:
            ext_socket = self._get_extension_socket(is_output=is_output)
            if not ext_socket or not ext_socket.is_linked:
                continue
            
            # Get the link
            link = ext_socket.links[0]
            
            # Determine the connected socket type
            if is_output:
                # Output socket connected: check destination
                connected_socket = link.to_socket
            else:
                # Input socket connected: check source
                connected_socket = link.from_socket
            
            # GRID-ONLY VALIDATION
            if 'Grid' not in connected_socket.bl_idname:
                self.id_data.links.remove(link)
                self.report({'ERROR'}, 
                    f"Repeat zone only accepts Grid state. "
                    f"Use Capture to convert Field → Grid before the loop.")
                continue
            
            # Store reconnection info
            if is_output:
                # Output connected: reconnect to new Current output
                to_node = link.to_node
                to_socket_name = link.to_socket.name
            else:
                # Input connected: reconnect to new Initial input
                from_node = link.from_node
                from_socket_name = link.from_socket.name
            
            # Remove link
            self.id_data.links.remove(link)
            
            # Add new state item
            # Inherit name from connected socket (like Geometry Nodes)
            inherited_name = connected_socket.name if connected_socket.name else "State"
            unique_name = self._make_unique_name(inherited_name)
            
            item = self.repeat_items.add()
            item.name = unique_name
            item.socket_type = 'ComputeSocketGrid'
            
            # Sync sockets
            self._sync_sockets()
            
            # Reconnect to new socket
            if is_output:
                # Reconnect from new Current output
                new_socket_name = item.name
                if new_socket_name in self.outputs:
                    self.id_data.links.new(
                        self.outputs[new_socket_name],
                        to_node.inputs[to_socket_name]
                    )
            else:
                # Reconnect to new Initial input
                new_socket_name = item.name
                if new_socket_name in self.inputs:
                    self.id_data.links.new(
                        from_node.outputs[from_socket_name],
                        self.inputs[new_socket_name]
                    )
            
            # Sync paired output
            self._sync_paired_output()
            
            # Only process one connection at a time
            break
    
    @with_sync_guard
    def _sync_sockets(self):
        """Rebuild sockets to match repeat_items collection."""
        # Keep track of existing connections by SOCKET NAME
        # This correctly handles both add and remove operations
        connections_by_name = {}
        
        for socket in self.inputs:
            if socket.name == "Iterations" or self._is_extension_socket(socket):
                continue
            if socket.is_linked:
                for link in socket.links:
                    if socket.name not in connections_by_name:
                        connections_by_name[socket.name] = {}
                    connections_by_name[socket.name]['input'] = (link.from_node.name, link.from_socket.name)
        
        for socket in self.outputs:
            if socket.name == "Iteration" or self._is_extension_socket(socket):
                continue
            if socket.is_linked:
                for link in socket.links:
                    if socket.name not in connections_by_name:
                        connections_by_name[socket.name] = {}
                    if 'output' not in connections_by_name[socket.name]:
                        connections_by_name[socket.name]['output'] = []
                    connections_by_name[socket.name]['output'].append((link.to_node.name, link.to_socket.name))
        
        # Clear dynamic sockets (keep Iterations input and Iteration output)
        # Remove from end to avoid index issues
        while len(self.inputs) > 1:
            socket = self.inputs[-1]
            if socket.name == "Iterations":
                break
            self.inputs.remove(socket)
        
        while len(self.outputs) > 1:
            socket = self.outputs[-1]
            if socket.name == "Iteration":
                break
            self.outputs.remove(socket)
        
        # Add sockets for each repeat item (create all first)
        for item in self.repeat_items:
            socket_type = item.socket_type
            
            # Input: Initial value (just use state name)
            self.inputs.new(socket_type, item.name)
            
            # Output: Current value (just use state name for use inside loop)
            self.outputs.new(socket_type, item.name)
        
        # Re-add extension socket
        self._ensure_extension_socket()
        
        
        # Restore connections by SOCKET NAME (not index)
        # The socket name we saved should still exist if the item wasn't removed
        tree = self.id_data
        for socket_name, conn_data in connections_by_name.items():
            # Restore input connection
            if 'input' in conn_data and socket_name in self.inputs:
                from_node_name, from_socket_name = conn_data['input']
                if from_node_name in tree.nodes:
                    from_node = tree.nodes[from_node_name]
                    if from_socket_name in from_node.outputs:
                        tree.links.new(
                            from_node.outputs[from_socket_name],
                            self.inputs[socket_name]
                        )
            
            # Restore output connections
            if 'output' in conn_data and socket_name in self.outputs:
                for to_node_name, to_socket_name in conn_data['output']:
                    if to_node_name in tree.nodes:
                        to_node = tree.nodes[to_node_name]
                        if to_socket_name in to_node.inputs:
                            tree.links.new(
                                self.outputs[socket_name],
                                to_node.inputs[to_socket_name]
                            )
    
    def _sync_paired_output(self):
        """Synchronize state items to paired Repeat Output."""
        if not self.paired_output:
            return
        
        tree = self.id_data
        if self.paired_output not in tree.nodes:
            return
        
        output_node = tree.nodes[self.paired_output]
        if output_node.bl_idname != 'ComputeNodeRepeatOutput':
            return
        
        # Clear and rebuild output's repeat_items to match ours
        output_node.repeat_items.clear()
        for item in self.repeat_items:
            new_item = output_node.repeat_items.add()
            new_item.name = item.name
            new_item.socket_type = item.socket_type
        
        output_node._sync_sockets()
    
    def draw_buttons(self, context, layout):
        """Draw node body (minimal - main UI in sidebar)."""
        pass  # Clean appearance, no messages
    
    def add_state(self, name="State", socket_type='NodeSocketFloat'):
        """Add a new state variable (called from operator)."""
        unique_name = self._make_unique_name(name)
        item = self.repeat_items.add()
        item.name = unique_name
        item.socket_type = socket_type
        self._sync_sockets()
        self._sync_paired_output()
        return item
    
    def remove_state(self, index):
        """Remove a state variable by index (called from operator)."""
        if 0 <= index < len(self.repeat_items):
            self.repeat_items.remove(index)
            self._sync_sockets()
            self._sync_paired_output()


# =============================================================================
# Repeat Output Node
# =============================================================================

class ComputeNodeRepeatOutput(ComputeNode):
    """Repeat Zone (Output) - End of an iterative loop.
    
    Receives Next values and outputs Final values after all iterations.
    Must be paired with a Repeat Input node.
    """
    
    bl_idname = 'ComputeNodeRepeatOutput'
    bl_label = 'Repeat Zone (Output)'
    bl_icon = 'LOOP_BACK'
    node_category = "CONTROL"
    
    # Mirror of input's collection (synced automatically)
    repeat_items: CollectionProperty(type=ComputeRepeatItem)
    
    # Pointer to paired input node
    paired_input: StringProperty(
        name="Paired Input",
        default="",
        description="Name of the paired Repeat Input node"
    )
    
    def init(self, context):
        # Extension socket for drag-to-add pattern (same as Input)
        self._ensure_extension_socket()
    
    def _ensure_extension_socket(self):
        """Add the special extension socket for drag-to-add pattern."""
        # Input side Empty (for Next values)
        if not self.inputs or self.inputs[-1].bl_idname != 'ComputeSocketEmpty':
            self.inputs.new('ComputeSocketEmpty', "Empty")
        
        # Output side Empty (for Final values)
        if not self.outputs or self.outputs[-1].bl_idname != 'ComputeSocketEmpty':
            self.outputs.new('ComputeSocketEmpty', "Empty")
    
    def _is_extension_socket(self, socket):
        """Check if socket is the extension socket."""
        return socket.bl_idname == 'ComputeSocketEmpty'
    
    def _get_extension_socket(self, is_output=False):
        """Find the extension socket."""
        sockets = self.outputs if is_output else self.inputs
        if sockets and sockets[-1].bl_idname == 'ComputeSocketEmpty':
            return sockets[-1]
        return None
    
    def draw_socket(self, context, layout, socket, text):
        if socket.bl_idname == 'ComputeSocketEmpty':
            layout.label(text="")
            return
        layout.label(text=text)
    
    def update(self):
        """Called when node connections change."""
        # Check BOTH input and output extension sockets
        # Input Empty: for connecting Next values
        # Output Empty: for connecting Final values (after loop)
        
        for is_output in [False, True]:
            ext_socket = self._get_extension_socket(is_output=is_output)
            if not ext_socket or not ext_socket.is_linked:
                continue
            
            # Get the link
            link = ext_socket.links[0]
            
            # Determine the connected socket type
            if is_output:
                # Output socket connected: check destination
                connected_socket = link.to_socket
            else:
                # Input socket connected: check source
                connected_socket = link.from_socket
            
            # GRID-ONLY VALIDATION
            if 'Grid' not in connected_socket.bl_idname:
                self.id_data.links.remove(link)
                self.report({'ERROR'}, 
                    f"Repeat zone only accepts Grid state. "
                    f"Use Capture to convert Field → Grid before the loop.")
                continue
            
            # Store reconnection info
            if is_output:
                # Output connected: reconnect to new Final output
                to_node = link.to_node
                to_socket_name = link.to_socket.name
            else:
                # Input connected: reconnect to new Next input
                from_node = link.from_node
                from_socket_name = link.from_socket.name
            
            # Remove link first
            self.id_data.links.remove(link)
            
            # Push new item to PAIRED INPUT (Input remains source of truth)
            tree = self.id_data
            if self.paired_input and self.paired_input in tree.nodes:
                input_node = tree.nodes[self.paired_input]
                
                # Inherit name from connected socket (like Geometry Nodes)
                inherited_name = connected_socket.name if connected_socket.name else "State"
                unique_name = input_node._make_unique_name(inherited_name)
                
                # Add new state item to Input
                item = input_node.repeat_items.add()
                item.name = unique_name
                item.socket_type = 'ComputeSocketGrid'
                
                # Sync Input's sockets
                input_node._sync_sockets()
                
                # Sync back to Output (us)
                input_node._sync_paired_output()
                
                # Reconnect to new socket on Output
                new_socket_name = item.name
                if is_output:
                    # Reconnect from new Final output
                    if new_socket_name in self.outputs:
                        self.id_data.links.new(
                            self.outputs[new_socket_name],
                            to_node.inputs[to_socket_name]
                        )
                else:
                    # Reconnect to new Next input
                    if new_socket_name in self.inputs:
                        self.id_data.links.new(
                            from_node.outputs[from_socket_name],
                            self.inputs[new_socket_name]
                        )
            
            # Only process one connection at a time
            break
    
    @with_sync_guard
    def _sync_sockets(self):
        """Rebuild sockets to match repeat_items collection from paired input."""
        # Keep track of existing connections by SOCKET NAME
        connections_by_name = {}
        
        for socket in self.inputs:
            if self._is_extension_socket(socket):
                continue
            if socket.is_linked:
                for link in socket.links:
                    if socket.name not in connections_by_name:
                        connections_by_name[socket.name] = {}
                    connections_by_name[socket.name]['input'] = (link.from_node.name, link.from_socket.name)
        
        for socket in self.outputs:
            if self._is_extension_socket(socket):
                continue
            if socket.is_linked:
                for link in socket.links:
                    if socket.name not in connections_by_name:
                        connections_by_name[socket.name] = {}
                    if 'output' not in connections_by_name[socket.name]:
                        connections_by_name[socket.name]['output'] = []
                    connections_by_name[socket.name]['output'].append((link.to_node.name, link.to_socket.name))
        
        # Clear all sockets
        self.inputs.clear()
        self.outputs.clear()
        
        # Get repeat_items from paired input
        if not self.paired_input:
            self._ensure_extension_socket()
            return
        
        node_tree = self.id_data
        if not node_tree:
            self._ensure_extension_socket()
            return
        
        paired = node_tree.nodes.get(self.paired_input)
        if not paired or not hasattr(paired, 'repeat_items'):
            self._ensure_extension_socket()
            return
        
        # Add sockets for each repeat item from paired input
        for item in paired.repeat_items:
            socket_type = item.socket_type
            self.inputs.new(socket_type, item.name)
            self.outputs.new(socket_type, item.name)
        
        # Re-add extension socket
        self._ensure_extension_socket()
        
        # Restore connections by socket name
        tree = self.id_data
        for socket_name, conn_data in connections_by_name.items():
            # Restore input connection
            if 'input' in conn_data and socket_name in self.inputs:
                from_node_name, from_socket_name = conn_data['input']
                if from_node_name in tree.nodes:
                    from_node = tree.nodes[from_node_name]
                    if from_socket_name in from_node.outputs:
                        tree.links.new(
                            from_node.outputs[from_socket_name],
                            self.inputs[socket_name]
                        )
            
            # Restore output connections
            if 'output' in conn_data and socket_name in self.outputs:
                for to_node_name, to_socket_name in conn_data['output']:
                    if to_node_name in tree.nodes:
                        to_node = tree.nodes[to_node_name]
                        if to_socket_name in to_node.inputs:
                            tree.links.new(
                                self.outputs[socket_name],
                                to_node.inputs[to_socket_name]
                            )
    
    def draw_buttons(self, context, layout):
        """Draw node body."""
        pass  # Clean appearance, no messages


# =============================================================================
# Operators for Add/Remove States
# =============================================================================

class COMPUTE_OT_add_repeat_state(bpy.types.Operator):
    """Add a new state variable to the Repeat Zone"""
    bl_idname = "compute.add_repeat_state"
    bl_label = "Add State"
    bl_options = {'REGISTER', 'UNDO'}
    
    socket_type: EnumProperty(
        name="Type",
        items=[
            ('NodeSocketFloat', "Float", ""),
            ('NodeSocketVector', "Vector", ""),
            ('NodeSocketColor', "Color", ""),
            ('ComputeSocketGrid', "Grid", ""),
        ],
        default='NodeSocketFloat'
    )
    
    @classmethod
    def poll(cls, context):
        node = context.active_node
        return node and node.bl_idname == 'ComputeNodeRepeatInput'
    
    def execute(self, context):
        node = context.active_node
        node.add_state(f"State {len(node.repeat_items) + 1}", self.socket_type)
        return {'FINISHED'}


class COMPUTE_OT_remove_repeat_state(bpy.types.Operator):
    """Remove a state variable from the Repeat Zone"""
    bl_idname = "compute.remove_repeat_state"
    bl_label = "Remove State"
    bl_options = {'REGISTER', 'UNDO'}
    
    index: IntProperty(default=0)
    
    @classmethod
    def poll(cls, context):
        node = context.active_node
        return (node and 
                node.bl_idname == 'ComputeNodeRepeatInput' and
                len(node.repeat_items) > 0)
    
    def execute(self, context):
        node = context.active_node
        node.remove_state(self.index)
        return {'FINISHED'}


class COMPUTE_OT_pair_repeat_nodes(bpy.types.Operator):
    """Pair Repeat Input and Output nodes together"""
    bl_idname = "compute.pair_repeat_nodes"
    bl_label = "Pair Repeat Nodes"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        # Need exactly 2 selected nodes: one input, one output
        if not context.space_data or not context.space_data.edit_tree:
            return False
        selected = [n for n in context.space_data.edit_tree.nodes if n.select]
        if len(selected) != 2:
            return False
        types = {n.bl_idname for n in selected}
        return types == {'ComputeNodeRepeatInput', 'ComputeNodeRepeatOutput'}
    
    def execute(self, context):
        selected = [n for n in context.space_data.edit_tree.nodes if n.select]
        
        input_node = None
        output_node = None
        for n in selected:
            if n.bl_idname == 'ComputeNodeRepeatInput':
                input_node = n
            else:
                output_node = n
        
        # Set pairing
        input_node.paired_output = output_node.name
        output_node.paired_input = input_node.name
        
        # Sync states
        input_node._sync_paired_output()
        
        self.report({'INFO'}, f"Paired {input_node.name} with {output_node.name}")
        return {'FINISHED'}

class COMPUTE_OT_add_repeat_zone_pair(bpy.types.Operator):
    """Add a Repeat Input and Output pair, linked and paired automatically."""
    bl_idname = "compute.add_repeat_zone_pair"
    bl_label = "Repeat Zone"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree: return {'CANCELLED'}
        
        # Create Input
        input_node = tree.nodes.new('ComputeNodeRepeatInput')
        input_node.location = context.space_data.cursor_location
        input_node.select = True
        tree.nodes.active = input_node
        
        # Create Output
        output_node = tree.nodes.new('ComputeNodeRepeatOutput')
        output_node.location = (input_node.location.x + 300, input_node.location.y)
        output_node.select = True
        
        # Link Iterations
        # Logic: We might want a default loop. But for now just pairing them is enough.
        
        # Pair them
        input_node.paired_output = output_node.name
        output_node.paired_input = input_node.name
        
        # Sync
        input_node._sync_paired_output()
        
        return {'FINISHED'}

# =============================================================================
# Sidebar Panel
# =============================================================================

class COMPUTE_UL_repeat_items(bpy.types.UIList):
    """Custom UI List for Repeat States"""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # Determine icon based on type
        t = item.socket_type
        icn = 'DOT'
        if 'Vector' in t: icn = 'Gm'
        elif 'Color' in t: icn = 'COLOR'
        elif 'Float' in t: icn = 'HOME'
        elif 'Grid' in t: icn = 'RENDERLAYERS'
        elif 'Buffer' in t: icn = 'BUFFER'
        
        layout.label(text="", icon=icn)
        layout.prop(item, "name", text="", emboss=False)


class COMPUTE_PT_repeat_zone(bpy.types.Panel):
    """Sidebar panel for managing Repeat Zone states."""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Node'  # Show in the "Node" tab
    bl_label = "Repeat Zone"
    
    @classmethod
    def poll(cls, context):
        if not context.space_data or not context.space_data.edit_tree:
            return False
        tree = context.space_data.edit_tree
        if tree.bl_idname != 'ComputeNodeTree':
            return False
        node = context.active_node
        return node and node.bl_idname in {
            'ComputeNodeRepeatInput',
            'ComputeNodeRepeatOutput'
        }
    
    def draw(self, context):
        layout = self.layout
        node = context.active_node
        
        # Get the RepeatInput
        if node.bl_idname == 'ComputeNodeRepeatOutput':
            if node.paired_input and node.paired_input in context.space_data.edit_tree.nodes:
                repeat_input = context.space_data.edit_tree.nodes[node.paired_input]
            else:
                layout.label(text="Not paired to Input", icon='ERROR')
                return
        else:
            repeat_input = node
        
        # Main List
        row = layout.row()
        row.template_list(
            "COMPUTE_UL_repeat_items", "",
            repeat_input, "repeat_items",
            repeat_input, "active_index",
            rows=5
        )
        
        col = row.column(align=True)
        col.operator_menu_enum("compute.add_repeat_state", "socket_type", text="", icon='ADD')
        
        # Remove active
        if repeat_input.repeat_items:
             op = col.operator("compute.remove_repeat_state", text="", icon='X')
             op.index = repeat_input.active_index
             
        # Properties of Active Item
        if (repeat_input.repeat_items and 
            0 <= repeat_input.active_index < len(repeat_input.repeat_items)):
            item = repeat_input.repeat_items[repeat_input.active_index]
            
            box = layout.box()
            box.prop(item, "name")
            # Socket type is always Grid (no selector needed)


# =============================================================================
# Registration
# =============================================================================

# Classes registered by THIS module (operators and panel only)
# PropertyGroup and Nodes are registered by main compute_nodes/__init__.py
_local_classes = [
    COMPUTE_OT_add_repeat_state,
    COMPUTE_OT_remove_repeat_state,
    COMPUTE_OT_pair_repeat_nodes,
    COMPUTE_OT_add_repeat_zone_pair,
    COMPUTE_UL_repeat_items,
    COMPUTE_PT_repeat_zone,
]


def register():
    """Register operators and panel (nodes/PropertyGroup registered elsewhere)."""
    for cls in _local_classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister operators and panel."""
    for cls in reversed(_local_classes):
        bpy.utils.unregister_class(cls)


# For node registration in nodes/__init__.py
node_classes = [
    ComputeNodeRepeatInput,
    ComputeNodeRepeatOutput,
]

