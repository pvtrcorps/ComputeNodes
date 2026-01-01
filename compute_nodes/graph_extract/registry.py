# Node Handler Registry
# Maps bl_idname -> handler function

from .handlers.images import handle_image_input, handle_image_info, handle_sample
from .handlers.math_ops import handle_math, handle_vector_math
from .handlers.textures import handle_noise_texture, handle_white_noise, handle_voronoi_texture
from .handlers.control_flow import handle_position, handle_switch, handle_mix
from .handlers.repeat import handle_repeat_output, handle_repeat_input
from .handlers.converter import handle_separate_xyz, handle_combine_xyz, handle_separate_color, handle_combine_color, handle_map_range, handle_clamp
from .handlers.output import handle_output_image
from .handlers.output_sequence import handle_output_sequence
from .handlers.resize import handle_resize
from .handlers.rasterize import handle_capture
from .handlers.viewer import handle_viewer
from .handlers.nodegroup import handle_nodegroup, handle_group_input, handle_group_output
from .handlers.reroute import handle_reroute

from typing import Dict, Optional, Callable, Any
from ..ir.graph import Value

# Registry mapping node bl_idname to handler function
# Handler signature: (node: Any, ctx: Dict[str, Any]) -> Optional[Value]
HandlerType = Callable[[Any, Dict[str, Any]], Optional[Value]]

HANDLER_REGISTRY: Dict[str, HandlerType] = {
    # Images
    'ComputeNodeImageInput': handle_image_input,
    'ComputeNodeImageInfo': handle_image_info,
    'ComputeNodeSample': handle_sample,
    
    # Output
    'ComputeNodeOutputImage': handle_output_image,
    'ComputeNodeOutputSequence': handle_output_sequence,
    
    # Math
    'ComputeNodeMath': handle_math,
    'ComputeNodeVectorMath': handle_vector_math,
    
    # Textures
    'ComputeNodeNoiseTexture': handle_noise_texture,
    'ComputeNodeWhiteNoise': handle_white_noise,
    'ComputeNodeVoronoiTexture': handle_voronoi_texture,
    
    # Control Flow
    'ComputeNodePosition': handle_position,
    'ComputeNodeSwitch': handle_switch,
    'ComputeNodeMix': handle_mix,
    'ComputeNodeRepeatOutput': handle_repeat_output,
    'ComputeNodeRepeatInput': handle_repeat_input,
    
    # Converter
    'ComputeNodeSeparateXYZ': handle_separate_xyz,
    'ComputeNodeCombineXYZ': handle_combine_xyz,
    'ComputeNodeSeparateColor': handle_separate_color,
    'ComputeNodeCombineColor': handle_combine_color,
    'ComputeNodeMapRange': handle_map_range,
    'ComputeNodeClamp': handle_clamp,
    
    # Grid Operations
    'ComputeNodeResize': handle_resize,
    'ComputeNodeCapture': handle_capture,
    
    # Node Groups
    'ComputeNodeGroup': handle_nodegroup,
    'ComputeNodeGroupInput': handle_group_input,
    'ComputeNodeGroupOutput': handle_group_output,
    
    # Debug
    'ComputeNodeViewer': handle_viewer,
    
    # Layout
    'NodeReroute': handle_reroute,
}

def get_handler(bl_idname: str) -> Optional[HandlerType]:
    """Get handler function for a node type, or None if not found."""
    return HANDLER_REGISTRY.get(bl_idname)

__all__ = ['HANDLER_REGISTRY', 'get_handler']
