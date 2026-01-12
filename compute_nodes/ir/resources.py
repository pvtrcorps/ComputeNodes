from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
from .types import DataType

class ResourceType(Enum):
    SAMPLER_2D = auto() # Filtered reading (texture())
    IMAGE_1D = auto()   # Storage 1D (imageLoad/Store) - for buffer emulation
    IMAGE_2D = auto()   # Storage 2D (imageLoad/Store)
    IMAGE_3D = auto()   # Storage 3D (imageLoad/Store) - for volumes
    BUFFER_1D = auto()  # Storage buffer (SSBO) or Uniform Buffer (UBO) - future

class ResourceAccess(Enum):
    READ = auto()
    WRITE = auto()
    READ_WRITE = auto()

@dataclass(unsafe_hash=True)
class ResourceDesc:
    """Base class for all resource descriptors."""
    name: str
    # Binding is layout-dependent, not semantic. 
    # Exclude from hash/eq comparison.
    binding: int = field(default=-1, compare=False, hash=False)
    type: ResourceType = None

@dataclass(unsafe_hash=True)
class ImageDesc(ResourceDesc):
    """
    Descriptor for Storage Images (image1D, image2D, image3D).
    
    Supports 1D, 2D, and 3D textures via the 'dimensions' field.
    Size tuple length should match dimensions:
      - 1D: (width,)
      - 2D: (width, height)  
      - 3D: (width, height, depth)
    
    is_internal: If True, this is a GPU-only texture (Rasterize, Resize).
                 If False, this needs a Blender Image datablock (Output).
    
    dynamic_size: If True, size is computed at runtime (e.g., Resize in loop).
                  The executor uses DynamicTexturePool for allocation.
    
    size_expression: When dynamic_size=True, contains Value objects or expressions
                     that can be evaluated at runtime to determine actual size.
                     Format: {'width': Value, 'height': Value, 'depth': Value}
    """
    format: str = "rgba32f"
    size: tuple = (0, 0)  # Variable length based on dimensions
    access: ResourceAccess = ResourceAccess.READ_WRITE
    dimensions: int = 2   # 1, 2, or 3
    is_internal: bool = True  # GPU-only by default
    dynamic_size: bool = False  # True if size computed at runtime
    size_expression: dict = field(default_factory=dict, compare=False, hash=False)  # Runtime size computation
    loop_body_resource: bool = False  # True if this resource is written INSIDE a loop body
    trigger_update: bool = False  # Force dependency graph update
    
    def __post_init__(self):
        # Set appropriate resource type based on dimensions
        if self.dimensions == 1:
            self.type = ResourceType.IMAGE_1D
        elif self.dimensions == 3:
            self.type = ResourceType.IMAGE_3D
        else:
            self.type = ResourceType.IMAGE_2D
    
    @property
    def width(self) -> int:
        """Get width (first dimension)."""
        return self.size[0] if len(self.size) > 0 else 0
    
    @property
    def height(self) -> int:
        """Get height (second dimension). Returns 1 for 1D textures."""
        return self.size[1] if len(self.size) > 1 else 1
    
    @property
    def depth(self) -> int:
        """Get depth (third dimension). Returns 1 for 1D/2D textures."""
        return self.size[2] if len(self.size) > 2 else 1

@dataclass(unsafe_hash=True)
class SamplerDesc(ResourceDesc):
    """
    Descriptor for Samplers (sampler2D).
    """
    def __post_init__(self):
        self.type = ResourceType.SAMPLER_2D

@dataclass(unsafe_hash=True)
class BufferDesc(ResourceDesc):
    """
    Descriptor for Buffers.
    """
    data_type: DataType = DataType.FLOAT
    access: ResourceAccess = ResourceAccess.READ
    
    def __post_init__(self):
        self.type = ResourceType.BUFFER_1D
