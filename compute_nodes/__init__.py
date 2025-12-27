import bpy
from .nodetree import ComputeNodeTree, ComputeNode
from .sockets import ComputeSocketGrid, ComputeSocketBuffer

# Import repeat module PropertyGroup (must be registered before nodes that use it)
from .nodes.repeat import ComputeRepeatItem

# Import node classes (excluding ComputeRepeatItem which is registered separately)
from .nodes import node_classes as specific_nodes, repeat_module, nodegroup_module

# PropertyGroup must come before nodes that reference it
classes = [
    ComputeRepeatItem,  # PropertyGroup first
    ComputeNodeTree,
    ComputeNode,
    ComputeSocketGrid,
    ComputeSocketBuffer,
] + specific_nodes

from . import categories
from . import operators

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    categories.register()
    operators.register()
    # Register repeat module extras (operators, panel)
    repeat_module.register()
    # Register nodegroup operators
    nodegroup_module.register()

def unregister():
    nodegroup_module.unregister()
    repeat_module.unregister()
    operators.unregister()
    categories.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

