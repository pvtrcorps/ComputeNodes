# Viewer Node - GPU-only visualization for Grids
# Zero CPU readback - draws directly from GPU texture

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty, PointerProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid

# Global storage for draw handlers and viewer textures
_viewer_handlers = {}  # viewer_id -> handler
_viewer_textures = {}  # viewer_id -> (texture_manager, texture_name)


class ComputeNodeViewer(ComputeNode):
    """Viewer - GPU-only Grid visualization.
    
    Displays the Grid content directly from GPU without CPU readback.
    Zero overhead for real-time debugging.
    
    Features:
    - Channel selection (RGBA, R, G, B, A)
    - Exposure control
    - GPU-only rendering (no overhead)
    """
    bl_idname = 'ComputeNodeViewer'
    bl_label = 'Viewer'
    bl_icon = 'HIDE_OFF'
    
    # Preview settings
    channel: EnumProperty(
        name="Channel",
        items=[
            ('RGBA', "RGBA", "Show all channels"),
            ('R', "R", "Red only"),
            ('G', "G", "Green only"),
            ('B', "B", "Blue only"),
            ('A', "A", "Alpha only"),
        ],
        default='RGBA'
    )
    
    exposure: FloatProperty(
        name="Exposure",
        default=0.0,
        min=-10.0,
        max=10.0,
        description="Exposure adjustment (stops)"
    )
    
    # Display position in viewport (normalized 0-1)
    display_x: FloatProperty(name="X", default=0.02, min=0.0, max=1.0)
    display_y: FloatProperty(name="Y", default=0.02, min=0.0, max=1.0)
    display_size: IntProperty(name="Size", default=200, min=50, max=800)
    
    # Internal: texture name
    preview_image_name: StringProperty(default="")
    
    def init(self, context):
        # Accept Grid
        self.inputs.new('ComputeSocketGrid', "Grid")
        
    def free(self):
        """Called when node is deleted - cleanup draw handler."""
        viewer_id = str(self.as_pointer())
        unregister_viewer_handler(viewer_id)
        super().free()
        
    def draw_buttons(self, context, layout):
        # Channel selector
        row = layout.row(align=True)
        row.prop(self, "channel", expand=True)
        
        # Exposure
        layout.prop(self, "exposure", slider=True)
        
        # Display settings
        col = layout.column(align=True)
        col.prop(self, "display_size")
        row = col.row(align=True)
        row.prop(self, "display_x", text="X")
        row.prop(self, "display_y", text="Y")
    
    def get_preview_name(self):
        """Returns the name for this viewer's preview texture."""
        return f"Viewer_{self.name}"
    
    def get_viewer_id(self):
        """Unique ID for this viewer instance."""
        return str(self.as_pointer())


def register_viewer_handler(viewer_id: str, texture_manager, texture_name: str, 
                            node: ComputeNodeViewer):
    """Register a draw handler for a viewer node."""
    global _viewer_handlers, _viewer_textures
    
    # Unregister existing
    unregister_viewer_handler(viewer_id)
    
    # Store texture reference
    _viewer_textures[viewer_id] = (texture_manager, texture_name, node)
    
    # Create draw callback
    def draw_viewer():
        _draw_viewer_texture(viewer_id)
    
    # Register for SpaceNodeEditor POST_PIXEL (Node Editor overlay)
    handler = bpy.types.SpaceNodeEditor.draw_handler_add(
        draw_viewer, (), 'WINDOW', 'POST_PIXEL'
    )
    _viewer_handlers[viewer_id] = handler


def unregister_viewer_handler(viewer_id: str):
    """Remove draw handler for a viewer."""
    global _viewer_handlers, _viewer_textures
    
    if viewer_id in _viewer_handlers:
        try:
            bpy.types.SpaceNodeEditor.draw_handler_remove(
                _viewer_handlers[viewer_id], 'WINDOW'
            )
        except:
            pass
        del _viewer_handlers[viewer_id]
    
    if viewer_id in _viewer_textures:
        del _viewer_textures[viewer_id]


def _draw_viewer_texture(viewer_id: str):
    """Draw the viewer texture as overlay in Node Editor."""
    import gpu
    from gpu_extras.batch import batch_for_shader
    
    global _viewer_textures
    
    data = _viewer_textures.get(viewer_id)
    if not data:
        return
    
    texture_manager, texture_name, node = data
    
    # Get cached GPU texture
    texture = texture_manager.get_cached_texture(texture_name)
    if not texture:
        return
    
    try:
        # Get node display settings
        size = node.display_size
        exposure = node.exposure
        channel = node.channel
        
        # Get viewport dimensions
        region = bpy.context.region
        if not region:
            return
        
        x = int(node.display_x * region.width)
        y = int(node.display_y * region.height)
        
        # Quad vertices (screen space)
        vertices = [
            (x, y), (x + size, y),
            (x, y + size), (x + size, y + size)
        ]
        texcoords = [(0, 0), (1, 0), (0, 1), (1, 1)]
        indices = [(0, 1, 2), (2, 1, 3)]
        
        # Use builtin image shader
        shader = gpu.shader.from_builtin('IMAGE')
        batch = batch_for_shader(
            shader, 'TRIS',
            {"pos": vertices, "texCoord": texcoords},
            indices=indices
        )
        
        shader.bind()
        shader.uniform_sampler("image", texture)
        
        # Enable blending for transparency
        gpu.state.blend_set('ALPHA')
        batch.draw(shader)
        gpu.state.blend_set('NONE')
        
    except Exception as e:
        # Silently fail - texture may be invalid
        pass


def cleanup_all_viewers():
    """Cleanup all viewer handlers (call on addon unregister)."""
    global _viewer_handlers, _viewer_textures
    
    for viewer_id in list(_viewer_handlers.keys()):
        unregister_viewer_handler(viewer_id)
    
    _viewer_handlers.clear()
    _viewer_textures.clear()


node_classes = [ComputeNodeViewer]
