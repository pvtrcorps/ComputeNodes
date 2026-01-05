import bpy
from nodeitems_utils import NodeCategory, NodeItem

class ComputeNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ComputeNodeTree'

# Note: CATEGORY_COLORS is now defined in nodetree.py
# Import it from there for consistency
from .nodetree import CATEGORY_COLORS

def get_category_color(category_name: str) -> tuple:
    """Get the color for a node category."""
    return CATEGORY_COLORS.get(category_name, CATEGORY_COLORS["DEFAULT"])

# Define the menu structure
node_categories = [
    ComputeNodeCategory("COMPUTE_INPUT", "Input", items=[
        NodeItem("ComputeNodeImageInput"),
        NodeItem("ComputeNodeImageInfo"),
        NodeItem("ComputeNodeValue"),
        # Input Vectors and scalars
        NodeItem("ComputeNodeInputVector"),
        NodeItem("ComputeNodeInputColor"),
        NodeItem("ComputeNodeInputBool"),
        NodeItem("ComputeNodeInputInt"),
        NodeItem("ComputeNodePosition"),
    ]),
    ComputeNodeCategory("COMPUTE_CONTROL", "Control", items=[
        NodeItem("ComputeNodeSwitch"),
        NodeItem("ComputeNodeMix"),
        # Repeat nodes are added via draw function below
    ]),
    ComputeNodeCategory("COMPUTE_TEXTURE", "Texture", items=[
        NodeItem("ComputeNodeSample"),
        NodeItem("ComputeNodeNoiseTexture"),
        NodeItem("ComputeNodeWhiteNoise"),
        NodeItem("ComputeNodeVoronoiTexture"),
    ]),
    ComputeNodeCategory("COMPUTE_VECTOR", "Vector", items=[
        NodeItem("ComputeNodeVectorMath"),
        NodeItem("ComputeNodeVectorRotate"),
    ]),
    ComputeNodeCategory("COMPUTE_MATH", "Math", items=[
        NodeItem("ComputeNodeMath"),
        NodeItem("ComputeNodeBooleanMath"),
    ]),
    ComputeNodeCategory("COMPUTE_CONVERTER", "Converter", items=[
        NodeItem("ComputeNodeSeparateXYZ"),
        NodeItem("ComputeNodeCombineXYZ"),
        NodeItem("ComputeNodeSeparateColor"),
        NodeItem("ComputeNodeCombineColor"),
        NodeItem("ComputeNodeMapRange"),
        NodeItem("ComputeNodeClamp"),
    ]),
    ComputeNodeCategory("COMPUTE_GRID", "Grid", items=[
        NodeItem("ComputeNodeCapture"),
        NodeItem("ComputeNodeResize"),
    ]),
    ComputeNodeCategory("COMPUTE_GROUPS", "Groups", items=[
        NodeItem("ComputeNodeGroup"),
        NodeItem("ComputeNodeGroupInput"),
        NodeItem("ComputeNodeGroupOutput"),
    ]),
    ComputeNodeCategory("COMPUTE_OUTPUT", "Output", items=[
        NodeItem("ComputeNodeOutputImage"),
        NodeItem("ComputeNodeOutputSequence"),
        NodeItem("ComputeNodeViewer"),
    ]),
]

def add_node_button(layout, node_type):
    """Helper to add a node button that matches Blender's style."""
    props = layout.operator("node.add_node", text=node_type.bl_label)
    props.type = node_type.bl_idname
    props.use_transform = True

def draw_add_menu(self, context):
    """Custom draw function for node add menu to inject Repeat Zone operator."""
    layout = self.layout
    
    # Only show for ComputeNodeTree
    if context.space_data.tree_type != 'ComputeNodeTree':
        return
    
    # This gets called for each category - we only want to inject into Control
    # Since we can't easily detect which category we're in, we'll add our custom section
    # This is a bit of a hack but works reliably
    pass

# Alternative: Draw function that adds to a specific category
def draw_repeat_zone_in_menu(self, context):
    """Inject Repeat Zone operator into the node add menu."""
    layout = self.layout
    
    # Only for ComputeNodeTree
    if not hasattr(context.space_data, 'tree_type'):
        return
    if context.space_data.tree_type != 'ComputeNodeTree':
        return
    
    # Add separator and our operator
    layout.separator()
    layout.operator("compute.add_repeat_zone_pair", text="Repeat Zone", icon='LOOP_FORWARDS')

def register():
    try:
        import nodeitems_utils
        nodeitems_utils.register_node_categories("COMPUTE_NODES", node_categories)
        
        # Register our custom menu draw function
        # This adds to the NODE_MT_add menu (the main Add menu in node editor)
        import bpy
        bpy.types.NODE_MT_add.append(draw_repeat_zone_in_menu)
        
    except Exception as e:
        print(f"Failed to register node categories: {e}")

def unregister():
    try:
        import nodeitems_utils
        nodeitems_utils.unregister_node_categories("COMPUTE_NODES")
        
        # Unregister menu draw function
        import bpy
        if hasattr(bpy.types.NODE_MT_add, 'remove'):
            bpy.types.NODE_MT_add.remove(draw_repeat_zone_in_menu)
        
    except Exception as e:
        print(f"Failed to unregister node categories: {e}")
