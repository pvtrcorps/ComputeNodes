import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import math
from bpy.types import NodeTree, Node, NodeSocket

# -----------------------------------------------------------------------------
# GPU Drawing Utilities for Node Coloring
# -----------------------------------------------------------------------------

def _rounded_rect(x, y, w, h, radius=8, segments=6, size=0):
    """
    Generate coordinates for a rounded rectangle.
    """
    coords = []
    
    # Center of original rect
    cx = x + w * 0.5
    cy = y - h * 0.5
    
    # Adjust dimensions
    w += size * 2
    h += size * 2
    
    # Limit radius to avoid artifacts on small nodes
    radius = min(radius, w * 0.5, h * 0.5)
    if radius < 0: radius = 0
    
    # Recalculate top-left corner
    x = cx - w * 0.5
    y = cy + h * 0.5
    
    def arc(cx, cy, start, end):
        for i in range(segments + 1):
            t = start + (end - start) * (i / segments)
            coords.append((
                cx + math.cos(t) * radius,
                cy + math.sin(t) * radius
            ))
    
    # Top-left
    arc(x + radius, y - radius, math.pi, math.pi / 2)
    # Top-right
    arc(x + w - radius, y - radius, math.pi / 2, 0)
    # Bottom-right
    arc(x + w - radius, y - h + radius, 0, -math.pi / 2)
    # Bottom-left
    arc(x + radius, y - h + radius, -math.pi / 2, -math.pi)
    
    coords.append(coords[0])  # Close the shape
    return coords


def _draw_polygon_color(coords, color=(0.2, 0.8, 1.0, 0.5)):
    """Draw a filled polygon using TRI_FAN."""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    verts = [(v[0], v[1]) if isinstance(v, tuple) else (v.x, v.y) for v in coords]
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
    
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.blend_set('NONE')




# -----------------------------------------------------------------------------
# Node Category Colors (RGB)
# -----------------------------------------------------------------------------

CATEGORY_COLORS = {
    "INPUT":     (0.35, 0.55, 0.35),
    "OUTPUT":    (0.55, 0.35, 0.35),
    "TEXTURE":   (0.45, 0.35, 0.55),
    "MATH":      (0.35, 0.45, 0.55),
    "VECTOR":    (0.35, 0.45, 0.55),
    "CONVERTER": (0.45, 0.45, 0.35),
    "CONTROL":   (0.45, 0.40, 0.35),
    "GRID":      (0.35, 0.50, 0.50),
    "GROUPS":    (0.40, 0.40, 0.40),
    "DEFAULT":   (0.35, 0.35, 0.35),
}


# -----------------------------------------------------------------------------
# ComputeNodeTree
# -----------------------------------------------------------------------------

class ComputeNodeTree(NodeTree):
    """Compute Graph Node Tree"""
    bl_idname = 'ComputeNodeTree'
    bl_label = 'Compute Graph'
    bl_icon = 'SHADERFX'
    
    @classmethod
    def poll(cls, context):
        return True
        

    def update(self):
        # 1. Sync Interface Changes
        # This ensures GroupInput/Output nodes and Parent Groups stay in sync
        # when the user edits the interface via the properties panel.
        try:
            from .nodes.nodegroup import update_parent_groups
            
            # Sync internal nodes
            for node in self.nodes:
                if hasattr(node, "sync_from_interface"):
                    node.sync_from_interface()
            
            # Sync parent groups
            update_parent_groups(self)
            
        except AttributeError:
             pass # Likely _RestrictData during registration
        except Exception as e:
            print(f"Interface sync failed: {e}")

        # 2. Sync Reroute Nodes (Visual Fix)
        self._sync_reroute_nodes()

        # 3. Auto Execute
        if getattr(self, "auto_execute", False):
            try:
                from .operators import execute_compute_tree
                import bpy
                execute_compute_tree(self, bpy.context)
            except Exception as e:
                print(f"Tree update failed: {e}")

    def _sync_reroute_nodes(self):
        """
        Force all NodeReroute nodes to use ComputeSocketReroute.
        ComputeSocketReroute's draw_color dynamically matches the source.
        """
        for node in self.nodes:
            if node.bl_idname == 'NodeReroute':
                if hasattr(node, "socket_idname"):
                    node.socket_idname = 'ComputeSocketReroute'

    def _update_auto_execute(self, context):
        if self.auto_execute:
            try:
                from .operators import execute_compute_tree
                execute_compute_tree(self, context)
            except Exception as e:
                print(f"Auto-execute trigger failed: {e}")

    auto_execute: bpy.props.BoolProperty(
        name="Auto Execute",
        description="Automatically execute graph on changes",
        default=False,
        update=_update_auto_execute
    )
    
    profile_execution: bpy.props.BoolProperty(
        name="Profile Execution",
        description="Measure execution time of each node",
        default=False
    )
    
    execution_time_total: bpy.props.FloatProperty(
        name="Total Execution Time",
        default=0.0
    )


# -----------------------------------------------------------------------------
# ComputeNode Base Class
# -----------------------------------------------------------------------------

class ComputeNode(Node):
    """Base class for Compute Nodes"""
    bl_label = "Compute Node"
    
    node_category = "DEFAULT"
    
    # Performance profiling
    execution_time: bpy.props.FloatProperty(
        name="Execution Time",
        description="Time spent executing this node (ms)",
        default=0.0,
        precision=3
    )
    
    @classmethod
    def poll(cls, nodetree):
        return nodetree.bl_idname == 'ComputeNodeTree'
    
    def get_node_color(self):
        """Get the base gray color for the node body."""
        return (0.18, 0.18, 0.18)
    
    def get_category_color(self):
        """Get the category accent color for this node."""
        from .categories import get_category_color
        return get_category_color(self.node_category)
        
    def apply_node_color(self):
        """Apply the base gray color to the node."""
        color = self.get_node_color()
        self.use_custom_color = True
        self.color = color
    
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Wrap init to ensure color application
        if 'init' in cls.__dict__:
            original_init = cls.init
            def wrapped_init(self, context):
                if hasattr(self, 'apply_node_color'):
                    try:
                        self.apply_node_color()
                    except:
                        pass
                return original_init(self, context)
            cls.init = wrapped_init

    def init(self, context):
        """Initialize the node - apply category color."""
        self.apply_node_color()
        
    def _draw_node_color(self):
        """Draw a thin colored band at the top of the node for category identification."""
        if self.hide:
            return
            
        ui_scale = bpy.context.preferences.system.ui_scale
        
        # Calculate absolute position by adding parent frame offsets
        abs_x, abs_y = self.location.x, self.location.y
        parent = self.parent
        while parent:
            abs_x += parent.location.x
            abs_y += parent.location.y
            parent = parent.parent
        
        x, y = abs_x * ui_scale, abs_y * ui_scale
        try:
            width, height = self.dimensions.x, self.dimensions.y
        except AttributeError:
             return
        
        # Avoid drawing collapsed/invalid nodes
        if width <= 0 or height <= 0:
            return
        
        # Draw the main gray body
        body_coords = _rounded_rect(
            x, y,
            width, height,
            radius=6,
            segments=6,
            size=1
        )
        gray_color = (self.color[0], self.color[1], self.color[2], 1.0)
        _draw_polygon_color(body_coords, color=gray_color)
        
        # Draw the colored top band (3 pixels tall)
        band_height = 4
        category_color = self.get_category_color()
        
        # Create a thin rectangle at the top
        # We need to create a simple quad for the band
        band_coords = [
            (x, y),                          # Top-left
            (x + width, y),                  # Top-right
            (x + width, y - band_height),    # Bottom-right
            (x, y - band_height),            # Bottom-left
            (x, y)                           # Close the loop
        ]
        
        band_color = (category_color[0], category_color[1], category_color[2], 1.0)
        _draw_polygon_color(band_coords, color=band_color)
    
    def draw_label(self):
        """Draw the node label and color overlay."""
        # Calling this here draws inside the node drawing context matchin GeneralRig
        self._draw_node_color()
        
        # Draw execution time if available and significant
        if self.execution_time > 0.001:
             return f"{self.bl_label} ({self.execution_time:.2f} ms)"
        return self.bl_label
    
    def update(self):
        try:
            tree = self.id_data
            if getattr(tree, "auto_execute", False):
                from .operators import execute_compute_tree
                import bpy
                execute_compute_tree(tree, bpy.context)
        except Exception as e:
            print(f"Node update failed: {e}")


