# UI Module for Compute Nodes
# Contains visual enhancements like zone drawing

from . import zone_drawing
from . import keymaps
from . import header

def register():
    zone_drawing.register()
    keymaps.register()
    header.register()

def unregister():
    header.unregister()
    keymaps.unregister()
    zone_drawing.unregister()
