import bpy
from .nodetree import ComputeNodeTree, ComputeNode
from .sockets import ComputeSocketImage, ComputeSocketBuffer
from .nodes import node_classes as specific_nodes

classes = [
    ComputeNodeTree,
    ComputeNode,
    ComputeSocketImage,
    ComputeSocketBuffer,
] + specific_nodes

from . import categories
from . import operators

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    categories.register()
    operators.register()

def unregister():
    operators.unregister()
    categories.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
