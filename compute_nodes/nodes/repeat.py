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
from ..sockets import ComputeSocketGrid


# =============================================================================
# PropertyGroup for Repeat State Items
# =============================================================================

class ComputeRepeatItem(bpy.types.PropertyGroup):
    """A single state variable in a Repeat Zone."""
    
    name: StringProperty(
        name="Name",
        default="State",
        description="Name of this state variable"
    )
    
    socket_type: EnumProperty(
        name="Type",
        items=[
            ('FLOAT', "Float", "Scalar value"),
            ('VECTOR', "Vector", "3D vector"),
            ('COLOR', "Color", "RGBA color"),
            ('GRID', "Grid", "GPU texture buffer"),
        ],
        default='FLOAT',
        description="Data type for this state"
    )


# Socket type mapping
SOCKET_TYPE_MAP = {
    'FLOAT': 'NodeSocketFloat',
    'VECTOR': 'NodeSocketVector', 
    'COLOR': 'NodeSocketColor',
    'GRID': 'ComputeSocketGrid',
}

# Reverse mapping for type inference
SOCKET_TO_REPEAT_TYPE = {
    'NodeSocketFloat': 'FLOAT',
    'NodeSocketVector': 'VECTOR',
    'NodeSocketColor': 'COLOR',
    'ComputeSocketGrid': 'GRID',
    # Handle common alternatives
    'NodeSocketInt': 'FLOAT',  # Treat as float for now
    'NodeSocketBool': 'FLOAT',
}


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
        self._add_extension_socket()
    
    # Special name for extension socket (must be unique)
    EXTENSION_SOCKET_NAME = "···"
    
    def _add_extension_socket(self):
        """Add the special extension socket for drag-to-add pattern."""
        # Check if already exists
        if self.EXTENSION_SOCKET_NAME in self.inputs:
            return
        
        ext = self.inputs.new('NodeSocketFloat', self.EXTENSION_SOCKET_NAME)
        ext.hide_value = True
    
    def _is_extension_socket(self, socket):
        """Check if socket is the extension socket."""
        return socket.name == self.EXTENSION_SOCKET_NAME
    
    def _get_extension_socket(self):
        """Find the extension socket."""
        if self.EXTENSION_SOCKET_NAME in self.inputs:
            return self.inputs[self.EXTENSION_SOCKET_NAME]
        return None
    
    def update(self):
        """Called when node connections change."""
        # Check if extension socket got connected
        ext_socket = self._get_extension_socket()
        if ext_socket and ext_socket.is_linked:
            # Get type from incoming connection
            link = ext_socket.links[0]
            from_socket = link.from_socket
            
            # Infer type
            socket_type = from_socket.bl_idname
            repeat_type = SOCKET_TO_REPEAT_TYPE.get(socket_type, 'FLOAT')
            
            # Store the from_node and from_socket for reconnection
            from_node = link.from_node
            from_socket_name = from_socket.name
            
            # Remove the link first (we'll recreate it to the new socket)
            self.id_data.links.remove(link)
            
            # Add new state item
            item = self.repeat_items.add()
            item.name = f"State {len(self.repeat_items)}"
            item.socket_type = repeat_type
            
            # Sync sockets and reconnect
            self._sync_sockets()
            
            # Find the new Initial socket and reconnect
            new_socket_name = f"Initial: {item.name}"
            if new_socket_name in self.inputs:
                new_socket = self.inputs[new_socket_name]
                # Reconnect via operator or direct link
                self.id_data.links.new(from_node.outputs[from_socket_name], new_socket)
            
            # Sync paired output
            self._sync_paired_output()
    
    def _sync_sockets(self):
        """Rebuild sockets to match repeat_items collection."""
        # Keep track of existing connections to restore
        connections = {}
        for socket in self.inputs:
            if socket.is_linked and not self._is_extension_socket(socket):
                for link in socket.links:
                    connections[socket.name] = (link.from_node.name, link.from_socket.name)
        
        for socket in self.outputs:
            if socket.is_linked and socket.name != "Iteration":
                for link in socket.links:
                    connections[socket.name] = (link.to_node.name, link.to_socket.name)
        
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
        
        # Add sockets for each repeat item
        for item in self.repeat_items:
            socket_type = SOCKET_TYPE_MAP.get(item.socket_type, 'NodeSocketFloat')
            
            # Input: Initial value
            input_name = f"Initial: {item.name}"
            self.inputs.new(socket_type, input_name)
            
            # Output: Current value (for use inside loop)
            output_name = f"Current: {item.name}"
            self.outputs.new(socket_type, output_name)
        
        # Re-add extension socket
        self._add_extension_socket()
        
        # Restore connections where possible
        tree = self.id_data
        for socket_name, (node_name, other_socket_name) in connections.items():
            if socket_name in self.inputs:
                # Input connection: from other node to this
                if node_name in tree.nodes:
                    other_node = tree.nodes[node_name]
                    if other_socket_name in other_node.outputs:
                        tree.links.new(
                            other_node.outputs[other_socket_name],
                            self.inputs[socket_name]
                        )
            elif socket_name in self.outputs:
                # Output connection: from this to other node
                if node_name in tree.nodes:
                    other_node = tree.nodes[node_name]
                    if other_socket_name in other_node.inputs:
                        tree.links.new(
                            self.outputs[socket_name],
                            other_node.inputs[other_socket_name]
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
        col = layout.column()
        col.scale_y = 0.8
        if len(self.repeat_items) == 0:
            col.label(text="Drag link to add state", icon='INFO')
        else:
            col.label(text=f"{len(self.repeat_items)} state(s)")
    
    def add_state(self, name="State", socket_type='FLOAT'):
        """Add a new state variable (called from operator)."""
        item = self.repeat_items.add()
        item.name = name
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
    
    # Mirror of input's collection (synced automatically)
    repeat_items: CollectionProperty(type=ComputeRepeatItem)
    
    # Pointer to paired input node
    paired_input: StringProperty(
        name="Paired Input",
        default="",
        description="Name of the paired Repeat Input node"
    )
    
    def init(self, context):
        # Sockets will be created by pairing with RepeatInput
        pass
    
    def _sync_sockets(self):
        """Rebuild sockets to match repeat_items collection from paired input."""
        # Clear all sockets
        self.inputs.clear()
        self.outputs.clear()
        
        # Get repeat_items from paired input
        if not self.paired_input:
            return
        
        node_tree = self.id_data
        if not node_tree:
            return
        
        paired = node_tree.nodes.get(self.paired_input)
        if not paired or not hasattr(paired, 'repeat_items'):
            return
        
        # Add sockets for each repeat item from paired input
        for item in paired.repeat_items:
            socket_type = SOCKET_TYPE_MAP.get(item.socket_type, 'NodeSocketFloat')
            
            # Input: Next value (computed inside loop)
            input_name = f"Next: {item.name}"
            self.inputs.new(socket_type, input_name)
            
            # Output: Final value (after all iterations)
            output_name = f"Final: {item.name}"
            self.outputs.new(socket_type, output_name)
    
    def draw_buttons(self, context, layout):
        """Draw node body."""
        if not self.paired_input:
            layout.label(text="Not paired", icon='ERROR')
        elif len(self.repeat_items) == 0:
            layout.label(text="No states", icon='INFO')


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
            ('FLOAT', "Float", ""),
            ('VECTOR', "Vector", ""),
            ('COLOR', "Color", ""),
            ('GRID', "Grid", ""),
        ],
        default='FLOAT'
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


# =============================================================================
# Sidebar Panel
# =============================================================================

class COMPUTE_PT_repeat_zone(bpy.types.Panel):
    """Sidebar panel for managing Repeat Zone states."""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Compute'
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
        
        # Get the RepeatInput (navigate from output if needed)
        if node.bl_idname == 'ComputeNodeRepeatOutput':
            if node.paired_input and node.paired_input in context.space_data.edit_tree.nodes:
                repeat_input = context.space_data.edit_tree.nodes[node.paired_input]
            else:
                layout.label(text="Not paired to Input", icon='ERROR')
                return
        else:
            repeat_input = node
        
        # Pairing section
        box = layout.box()
        box.label(text="Pairing", icon='LINKED')
        if repeat_input.paired_output:
            box.label(text=f"Output: {repeat_input.paired_output}")
        else:
            box.label(text="No output paired", icon='INFO')
            box.operator("compute.pair_repeat_nodes", text="Pair Selected Nodes")
        
        layout.separator()
        
        # State variables section
        box = layout.box()
        box.label(text="State Variables", icon='PROPERTIES')
        
        if len(repeat_input.repeat_items) == 0:
            box.label(text="No states defined")
            box.label(text="Drag a link to extension socket")
        else:
            for i, item in enumerate(repeat_input.repeat_items):
                row = box.row(align=True)
                row.prop(item, "name", text="")
                row.prop(item, "socket_type", text="")
                op = row.operator("compute.remove_repeat_state", text="", icon='X')
                op.index = i
        
        # Add button with type selector
        row = box.row(align=True)
        row.operator_menu_enum(
            "compute.add_repeat_state",
            "socket_type",
            text="Add State",
            icon='ADD'
        )


# =============================================================================
# Registration
# =============================================================================

# Classes registered by THIS module (operators and panel only)
# PropertyGroup and Nodes are registered by main compute_nodes/__init__.py
_local_classes = [
    COMPUTE_OT_add_repeat_state,
    COMPUTE_OT_remove_repeat_state,
    COMPUTE_OT_pair_repeat_nodes,
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

