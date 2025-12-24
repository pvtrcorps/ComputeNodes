from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
from .types import DataType

class ResourceType(Enum):
    SAMPLER_2D = auto() # Filtered reading (texture())
    IMAGE_2D = auto()   # Storage reading/writing (imageLoad/Store)
    BUFFER_1D = auto()  # Storage buffer (SSBO) or Uniform Buffer (UBO)

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
    Descriptor for Storage Images (image2D).
    """
    format: str = "rgba32f"
    size: tuple = (0, 0) # (width, height), 0 means "context dependent"
    access: ResourceAccess = ResourceAccess.READ_WRITE
    
    def __post_init__(self):
        self.type = ResourceType.IMAGE_2D

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
