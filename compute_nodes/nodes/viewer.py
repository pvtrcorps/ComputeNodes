# Viewer Node - GPU-only visualization for Grids
# Zero CPU readback - draws directly from GPU texture

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty, PointerProperty
from ..nodetree import ComputeNode
from ..sockets import ComputeSocketGrid

# Global storage for viewer textures
# viewer_id -> (texture_manager, texture_name, node)
_viewer_textures = {}  


class ComputeNodeViewer(ComputeNode):
    """Viewer - GPU-only Grid visualization.
    
    Displays the Grid content directly from GPU without CPU readback.
    Zero overhead for real-time debugging.
    
    Features:
    - GPU-only rendering (no overhead)
    """
    bl_idname = 'ComputeNodeViewer'
    bl_label = 'Viewer'
    bl_icon = 'HIDE_OFF'
    node_category = "OUTPUT"
    
    # Internal: texture name
    preview_image_name: StringProperty(default="")
    
    def init(self, context):
        # Accept Grid
        self.inputs.new('ComputeSocketGrid', "Grid")
        
    def free(self):
        """Called when node is deleted - cleanup texture ref."""
        viewer_id = str(self.as_pointer())
        unregister_viewer_handler(viewer_id)
        super().free()
        
    def draw_buttons(self, context, layout):
        pass # No options visible
        
    def draw_label(self):
        """Draw label and viewer image."""
        # Standard header drawing first
        label = super().draw_label()
        
        # Custom Viewer Image Drawing
        # This executes in the Node Drawing context, so transforms are valid
        self._draw_viewer_image()
        
        return label

    def _draw_viewer_image(self):
        """Draw the viewer texture using exact same transform logic as Node Headers."""
        import gpu
        from gpu_extras.batch import batch_for_shader
        
        # Find our texture data
        viewer_id = self.get_viewer_id()
        data = _viewer_textures.get(viewer_id)
        
        if not data:
            return
            
        texture_manager, texture_name, _ = data
        texture = texture_manager.get_cached_texture(texture_name)
        
        if not texture:
            return

        try:
            # ---------------------------------------------------------------------
            # COORDINATE SYSTEM
            # ---------------------------------------------------------------------
            # This mimics compute_nodes/nodetree.py _draw_node_color behavior.
            # Using self.location * ui_scale inside the draw_label context
            # gives the correct position relative to the graph view.
            
            ui_scale = bpy.context.preferences.system.ui_scale
            x, y = self.location.x * ui_scale, self.location.y * ui_scale
            w = self.dimensions.x
            
            # Aspect ratio height logic
            tex_w = texture.width
            tex_h = texture.height
            aspect = tex_h / tex_w if tex_w > 0 else 1.0
            h = w * aspect # Standard 1.0 scale
            
            # Draw ABOVE the node
            # y is the top-left corner of the node body.
            # We want to draw upwards from there.
            
            x_draw = x
            y_draw = y + (10 * ui_scale) # 10px padding above node
            
            # Dimensions from self.dimensions DO NOT need UI Scale multiplication
            # (Matches logic in nodetree.py)
            w_draw = w
            h_draw = h
            
            # Vertices (Bottom-Left to Top-Right in standard 2D Cartesian)
            vertices = [
                (x_draw, y_draw),                   (x_draw + w_draw, y_draw),
                (x_draw, y_draw + h_draw),          (x_draw + w_draw, y_draw + h_draw)
            ]
            
            texcoords = [(0, 0), (1, 0), (0, 1), (1, 1)]
            indices = [(0, 1, 2), (2, 1, 3)]
            
            shader = gpu.shader.from_builtin('IMAGE')
            batch = batch_for_shader(
                shader, 'TRIS',
                {"pos": vertices, "texCoord": texcoords},
                indices=indices
            )
            
            shader.bind()
            shader.uniform_sampler("image", texture)
            
            gpu.state.blend_set('ALPHA')
            batch.draw(shader)
            gpu.state.blend_set('NONE')
            
        except Exception as e:
            pass
    
    def get_preview_name(self):
        """Returns the name for this viewer's preview texture."""
        return f"Viewer_{self.name}"
    
    def get_viewer_id(self):
        """Unique ID for this viewer instance."""
        return str(self.as_pointer())


def register_viewer_handler(viewer_id: str, texture_manager, texture_name: str, 
                            node: ComputeNodeViewer):
    """Register viewer data (used to be handler, now just storage)."""
    global _viewer_textures
    
    # Store texture reference for draw_label to find
    _viewer_textures[viewer_id] = (texture_manager, texture_name, node)


def unregister_viewer_handler(viewer_id: str):
    """Remove data for a viewer."""
    global _viewer_textures
    
    if viewer_id in _viewer_textures:
        del _viewer_textures[viewer_id]


def cleanup_all_viewers():
    """Cleanup all viewer data (call on addon unregister)."""
    global _viewer_textures
    _viewer_textures.clear()


node_classes = [ComputeNodeViewer]
