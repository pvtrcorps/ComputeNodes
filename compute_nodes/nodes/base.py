import bpy
from . import *

class ComputeNode(bpy.types.Node):
    """Base class for all Compute Nodes"""
    bl_label = "Compute Node"
    
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'ComputeNodeTree'
        
    def init(self, context):
        pass

    def copy(self, node):
        pass
        
    def free(self):
        pass
        
    def draw_buttons(self, context, layout):
        pass
        
    def draw_buttons_ext(self, context, layout):
        pass
        
    def draw_label(self):
        return self.bl_label
