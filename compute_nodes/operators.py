# =============================================================================
# Compute Nodes - UI Operators
# =============================================================================
#
# This module contains Blender operators for user actions.
# Core execution logic has been moved to execution.py.
# UI panels have been moved to panels.py.

import bpy

# Backward compatibility - re-export execution functions
from .execution import (
    ExecutionContext,
    get_executor,
    execute_compute_tree,
)

__all__ = [
    'ExecutionContext',
    'get_executor',
    'execute_compute_tree',
    'ComputeExecuteOperator',
    'COMPUTE_OT_add_group_socket',
    'COMPUTE_OT_move_group_socket',
]


# =============================================================================
# Execution Operator
# =============================================================================

class ComputeExecuteOperator(bpy.types.Operator):
    """Execute the current Compute Node Tree on GPU"""
    bl_idname = "compute.execute_graph"
    bl_label = "Execute Compute Graph"
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree:
            self.report({'ERROR'}, "No active node tree")
            return {'CANCELLED'}
            
        try:
            count = execute_compute_tree(tree, context)
            
            from .logger import log_info
            log_info(f"Execution complete. Ran {count} passes.")
            
            self.report({'INFO'}, f"Executed {count} passes.")
            return {'FINISHED'}
            
        except Exception as e:
            from .logger import log_error
            log_error(f"Execution Failed: {e}")
            import traceback
            traceback.print_exc()
            
            self.report({'ERROR'}, f"Execution Failed: {e}")
            return {'CANCELLED'}


# =============================================================================
# Group Socket Operators
# =============================================================================

class COMPUTE_OT_add_group_socket(bpy.types.Operator):
    """Add a new socket to the group interface"""
    bl_idname = "compute.add_group_socket"
    bl_label = "Add Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    in_out: bpy.props.EnumProperty(
        items=[('INPUT', "Input", ""), ('OUTPUT', "Output", "")],
        name="Type"
    )
    
    socket_type: bpy.props.EnumProperty(
        items=[
            ('NodeSocketFloat', "Float", "Floating point value", 'IPO', 0),
            ('NodeSocketInt', "Integer", "Integer value", 'IPO_CONSTANT', 1),
            ('NodeSocketBool', "Boolean", "Boolean value", 'IPO_LINEAR', 2),
            ('NodeSocketVector', "Vector", "3D Vector", 'IPO_BEZIER', 3),
            ('NodeSocketColor', "Color", "RGBA Color", 'COLOR', 4),
            ('NodeSocketString', "String", "Text string", 'FONT_DATA', 5),
            ('ComputeSocketGrid', "Grid", "Compute Grid Data", 'RENDERLAYERS', 6),
            ('ComputeSocketBuffer', "Buffer", "Compute Buffer Data", 'BUFFER', 7),
        ],
        name="Socket Type"
    )
    
    def execute(self, context):
        tree = context.space_data.node_tree
        if not tree: return {'CANCELLED'}
        
        # Determine name base
        base_name = "Value"
        if "Vector" in self.socket_type: base_name = "Vector"
        if "Color" in self.socket_type: base_name = "Color"
        if "Grid" in self.socket_type: base_name = "Grid"
        
        # New Socket
        tree.interface.new_socket(base_name, in_out=self.in_out, socket_type=self.socket_type)
        
        # Trigger Sync
        try:
            from .nodes.nodegroup import update_parent_groups
            update_parent_groups(tree)
            for node in tree.nodes:
                if hasattr(node, "sync_from_interface"):
                    node.sync_from_interface()
        except Exception:
            pass
            
        return {'FINISHED'}


class COMPUTE_OT_move_group_socket(bpy.types.Operator):
    """Move a socket up or down"""
    bl_idname = "compute.move_group_socket"
    bl_label = "Move Socket"
    bl_options = {'REGISTER', 'UNDO'}
    
    socket_name: bpy.props.StringProperty()
    direction: bpy.props.EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")])
    
    def execute(self, context):
        tree = context.space_data.node_tree
        interface = tree.interface
        item = interface.items_tree.get(self.socket_name)
        if not item: return {'CANCELLED'}
        
        keys = list(interface.items_tree.keys())
        current_idx = keys.index(item.name)
        
        new_idx = current_idx - 1 if self.direction == 'UP' else current_idx + 1
        
        if 0 <= new_idx < len(keys):
            interface.move(item, new_idx)
            
            # Sync
            try:
                from .nodes.nodegroup import update_parent_groups
                update_parent_groups(tree)
                for node in tree.nodes:
                    if hasattr(node, "sync_from_interface"):
                        node.sync_from_interface()
            except Exception:
                pass
                
        return {'FINISHED'}


# =============================================================================
# Registration
# =============================================================================

classes = (
    ComputeExecuteOperator,
    COMPUTE_OT_add_group_socket,
    COMPUTE_OT_move_group_socket,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
