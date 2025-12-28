# UI Module for Compute Nodes
# Contains visual enhancements like zone drawing

from . import zone_drawing


def register():
    zone_drawing.register()


def unregister():
    zone_drawing.unregister()
