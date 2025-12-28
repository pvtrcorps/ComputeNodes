from .math import ComputeNodeMath
from .input import ComputeNodeImageInput, ComputeNodeImageInfo, ComputeNodeValue
from .output import ComputeNodeOutputImage
from .output_sequence import ComputeNodeOutputSequence
from .accessors import ComputeNodePosition, ComputeNodeSample
from .vector import ComputeNodeVectorMath
from .control_flow import ComputeNodeSwitch, ComputeNodeMix
from .repeat import ComputeNodeRepeatInput, ComputeNodeRepeatOutput, ComputeRepeatItem
from . import repeat as repeat_module  # For extra registrations
from .textures import ComputeNodeNoiseTexture, ComputeNodeWhiteNoise, ComputeNodeVoronoiTexture
from .converter import ComputeNodeSeparateXYZ, ComputeNodeCombineXYZ, ComputeNodeSeparateColor, ComputeNodeCombineColor, ComputeNodeMapRange, ComputeNodeClamp
from .resize import ComputeNodeResize
from .rasterize import ComputeNodeCapture
from .viewer import ComputeNodeViewer
from .nodegroup import ComputeNodeGroup, ComputeNodeGroupInput, ComputeNodeGroupOutput, COMPUTE_OT_remove_group_socket
from . import nodegroup as nodegroup_module  # For operator registrations

node_classes = [
    ComputeNodeMath,
    ComputeNodeImageInput,
    ComputeNodeImageInfo,
    ComputeNodeValue,
    ComputeNodeOutputImage,
    ComputeNodeOutputSequence,
    ComputeNodePosition,
    ComputeNodeSample,
    ComputeNodeVectorMath,
    ComputeNodeSwitch,
    ComputeNodeMix,
    ComputeNodeRepeatInput,
    ComputeNodeRepeatOutput,
    ComputeNodeNoiseTexture,
    ComputeNodeWhiteNoise,
    ComputeNodeVoronoiTexture,
    ComputeNodeSeparateXYZ,
    ComputeNodeCombineXYZ,
    ComputeNodeSeparateColor,
    ComputeNodeCombineColor,
    ComputeNodeMapRange,
    ComputeNodeClamp,
    ComputeNodeResize,
    ComputeNodeCapture,
    ComputeNodeViewer,
    ComputeNodeGroup,
    ComputeNodeGroupInput,
    ComputeNodeGroupOutput,
]

operator_classes = [
    COMPUTE_OT_remove_group_socket,
]

def register():
    import bpy
    for cls in operator_classes:
        bpy.utils.register_class(cls)

def unregister():
    import bpy
    for cls in reversed(operator_classes):
        bpy.utils.unregister_class(cls)
