from .math import ComputeNodeMath
from .input import ComputeNodeImageInput, ComputeNodeImageInfo, ComputeNodeImageWrite
from .output import ComputeNodeOutput
from .accessors import ComputeNodePosition, ComputeNodeSample
from .vector import ComputeNodeVectorMath
from .control_flow import ComputeNodeSwitch, ComputeNodeMix, ComputeNodeRepeatInput, ComputeNodeRepeatOutput
from .textures import ComputeNodeNoiseTexture, ComputeNodeWhiteNoise, ComputeNodeVoronoiTexture
from .converter import ComputeNodeSeparateXYZ, ComputeNodeCombineXYZ, ComputeNodeSeparateColor, ComputeNodeCombineColor, ComputeNodeMapRange, ComputeNodeClamp

node_classes = [
    ComputeNodeMath,
    ComputeNodeImageInput,
    ComputeNodeImageInfo,
    ComputeNodeImageWrite,
    ComputeNodeOutput,
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
]

def register():
    # Only exposing list of classes to be registered by main
    pass

def unregister():
    pass
