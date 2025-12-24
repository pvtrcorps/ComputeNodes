from enum import Enum, auto

class DataType(Enum):
    # Scalars
    FLOAT = auto()
    INT = auto()
    UINT = auto() # New unsigned int type
    BOOL = auto()
    
    # Vectors
    VEC2 = auto()
    VEC3 = auto()
    VEC4 = auto()
    
    IVEC2 = auto()
    IVEC3 = auto()
    IVEC4 = auto()
    
    UVEC2 = auto()
    UVEC3 = auto()
    UVEC4 = auto()
    
    # Generic Handle for Resources (Image, Buffer, Sampler)
    # The actual resource info is in the ResourceDesc, not the type.
    HANDLE = auto()

    # NOTE: Resources (Image, Buffer) are no longer DataTypes. 
    # They are Resources handled by ResourceDesc.

    def is_vector(self):
        return self in {
            DataType.VEC2, DataType.VEC3, DataType.VEC4,
            DataType.IVEC2, DataType.IVEC3, DataType.IVEC4,
            DataType.UVEC2, DataType.UVEC3, DataType.UVEC4
        }

    def is_scalar(self):
        return self in {DataType.FLOAT, DataType.INT, DataType.UINT, DataType.BOOL}
    
    def is_integer(self):
        """Returns True if the type is based on integer (signed or unsigned)."""
        return self in {
            DataType.INT, DataType.UINT,
            DataType.IVEC2, DataType.IVEC3, DataType.IVEC4,
            DataType.UVEC2, DataType.UVEC3, DataType.UVEC4
        }
        
    def is_unsigned(self):
        return self in {
            DataType.UINT,
            DataType.UVEC2, DataType.UVEC3, DataType.UVEC4
        }

    def component_count(self):
        if self in {DataType.VEC2, DataType.IVEC2, DataType.UVEC2}: return 2
        if self in {DataType.VEC3, DataType.IVEC3, DataType.UVEC3}: return 3
        if self in {DataType.VEC4, DataType.IVEC4, DataType.UVEC4}: return 4
        return 1

    def base_type(self):
        """Returns the scalar type of the vector components."""
        if self in {DataType.VEC2, DataType.VEC3, DataType.VEC4}: return DataType.FLOAT
        if self in {DataType.IVEC2, DataType.IVEC3, DataType.IVEC4}: return DataType.INT
        if self in {DataType.UVEC2, DataType.UVEC3, DataType.UVEC4}: return DataType.UINT
        return self

    def __str__(self):
        return self.name.lower()
