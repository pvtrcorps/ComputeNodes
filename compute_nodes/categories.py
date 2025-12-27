import bpy
from nodeitems_utils import NodeCategory, NodeItem

class ComputeNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'ComputeNodeTree'

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
