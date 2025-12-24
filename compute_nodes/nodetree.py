import bpy
from bpy.types import NodeTree, Node, NodeSocket

class ComputeNodeTree(NodeTree):
    """Compute Graph Node Tree"""
    bl_idname = 'ComputeNodeTree'
    bl_label = 'Compute Graph'
    bl_icon = 'SHADERFX' # Placeholder icon
    
    @classmethod
    def poll(cls, context):
        return True
        
    def update(self):
        """Called when links/nodes change"""
        if getattr(self, "auto_execute", False):
            try:
                from .operators import execute_compute_tree
                import bpy
                # Use a catch-all context
                execute_compute_tree(self, bpy.context)
            except Exception as e:
                print(f"Tree update failed: {e}")

    auto_execute: bpy.props.BoolProperty(
        name="Auto Execute",
        description="Automatically execute graph on changes",
        default=False
    )

class ComputeNode(Node):
    """Base class for Compute Nodes"""
    bl_label = "Compute Node"
    
    @classmethod
    def poll(cls, nodetree):
        return nodetree.bl_idname == 'ComputeNodeTree'
    
    def update(self):
        # Trigger graph update if auto-execute is enabled
        try:
            tree = self.id_data
            if getattr(tree, "auto_execute", False):
                # Avoid circular import at top level
                from .operators import execute_compute_tree
                import bpy
                
                # We need a context, but 'update' runs in a restrictive context.
                # However, execute_compute_tree needs context for scene/window_manager.
                # using bpy.context here is often safe enough for property updates from UI.
                execute_compute_tree(tree, bpy.context)
        except Exception as e:
            print(f"Node update failed: {e}")
