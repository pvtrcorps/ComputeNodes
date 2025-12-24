bl_info = {
    "name": "Compute Graph",
    "author": "Antigravity",
    "version": (0, 1),
    "blender": (4, 0, 0),
    "location": "Node Editor",
    "description": "GPU Compute Node System",
    "warning": "",
    "doc_url": "",
    "category": "Render",
}

import bpy
from . import compute_nodes

def register():
    compute_nodes.register()

def unregister():
    compute_nodes.unregister()
