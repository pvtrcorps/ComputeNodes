# UI Module for Compute Nodes
# Contains visual enhancements like zone drawing

from . import zone_drawing
from . import breadcrumbs
from . import keymaps
from . import header

def register():
    zone_drawing.register()
    breadcrumbs.register()
    keymaps.register()
    header.register()

def unregister():
    header.unregister()
    keymaps.unregister()
    breadcrumbs.unregister()
    zone_drawing.unregister()
