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
        NodeItem("ComputeNodePosition"),
    ]),
    ComputeNodeCategory("COMPUTE_CONTROL", "Control", items=[
        NodeItem("ComputeNodeSwitch"),
        NodeItem("ComputeNodeMix"),
        NodeItem("ComputeNodeRepeatInput"),
        NodeItem("ComputeNodeRepeatOutput"),
    ]),
    ComputeNodeCategory("COMPUTE_TEXTURE", "Texture", items=[
        NodeItem("ComputeNodeSample"),
        NodeItem("ComputeNodeNoiseTexture"),
        NodeItem("ComputeNodeWhiteNoise"),
        NodeItem("ComputeNodeVoronoiTexture"),
    ]),
    ComputeNodeCategory("COMPUTE_VECTOR", "Vector", items=[
        NodeItem("ComputeNodeVectorMath"),
    ]),
    ComputeNodeCategory("COMPUTE_MATH", "Math", items=[
        NodeItem("ComputeNodeMath"),
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

def register():
    try:
        import nodeitems_utils
        nodeitems_utils.register_node_categories("COMPUTE_NODES", node_categories)
    except Exception as e:
        print(f"Failed to register node categories: {e}")

def unregister():
    try:
        import nodeitems_utils
        nodeitems_utils.unregister_node_categories("COMPUTE_NODES")
    except Exception as e:
        print(f"Failed to unregister node categories: {e}")
