from .math import ComputeNodeMath
from .input import ComputeNodeImageInput, ComputeNodeImageInfo
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

node_classes = [
    ComputeNodeMath,
    ComputeNodeImageInput,
    ComputeNodeImageInfo,
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
]

def register():
    # Only exposing list of classes to be registered by main
    pass

def unregister():
    pass
