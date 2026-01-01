# UI Module for Compute Nodes
# Contains visual enhancements like zone drawing

from . import zone_drawing
from . import keymaps

def register():
    zone_drawing.register()
    keymaps.register()

def unregister():
    keymaps.unregister()
    zone_drawing.unregister()
