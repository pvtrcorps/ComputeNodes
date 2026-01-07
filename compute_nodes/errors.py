"""
Custom exceptions for Compute Nodes addon.

This module provides a hierarchy of exceptions for better error handling
and debugging. Use specific exceptions for clearer error messages.

Exception Hierarchy:
    ComputeNodesError (base)
    ├── CompilationError
    │   ├── ShaderCompileError
    │   └── GraphExtractionError
    ├── ExecutionError
    │   ├── TextureBindError
    │   ├── DispatchError
    │   └── LoopExecutionError
    └── ResourceError
        ├── TextureCreateError
        └── ResourceNotFoundError
"""


class ComputeNodesError(Exception):
    """Base exception for all Compute Nodes errors."""
    pass


# =============================================================================
# Compilation Errors
# =============================================================================

class CompilationError(ComputeNodesError):
    """Base exception for compilation/code generation errors."""
    pass


class ShaderCompileError(CompilationError):
    """
    Raised when GLSL shader compilation fails.
    
    Attributes:
        source: The GLSL source code that failed to compile
        error_message: The error from the GPU driver
    """
    
    def __init__(self, message: str, source: str = None, error_message: str = None):
        super().__init__(message)
        self.source = source
        self.error_message = error_message
    
    def format_with_source(self) -> str:
        """Format error with numbered source lines."""
        if not self.source:
            return str(self)
        
        lines = []
        lines.append(f"ShaderCompileError: {self}")
        if self.error_message:
            lines.append(f"GPU Error: {self.error_message}")
        lines.append("--- SHADER SOURCE ---")
        for i, line in enumerate(self.source.split('\n')):
            lines.append(f"{i+1:03d}: {line}")
        lines.append("---------------------")
        return '\n'.join(lines)


class GraphExtractionError(CompilationError):
    """Raised when node graph extraction fails."""
    
    def __init__(self, message: str, node_name: str = None):
        super().__init__(message)
        self.node_name = node_name


# =============================================================================
# Execution Errors
# =============================================================================

class ExecutionError(ComputeNodesError):
    """Base exception for runtime execution errors."""
    pass


class TextureBindError(ExecutionError):
    """Raised when texture binding to shader fails."""
    
    def __init__(self, message: str, uniform_name: str = None, texture_size: tuple = None):
        super().__init__(message)
        self.uniform_name = uniform_name
        self.texture_size = texture_size


class DispatchError(ExecutionError):
    """Raised when compute dispatch fails."""
    
    def __init__(self, message: str, dispatch_size: tuple = None, pass_id: int = None):
        super().__init__(message)
        self.dispatch_size = dispatch_size
        self.pass_id = pass_id


class LoopExecutionError(ExecutionError):
    """Raised when loop execution fails."""
    
    def __init__(self, message: str, iteration: int = None, state_name: str = None):
        super().__init__(message)
        self.iteration = iteration
        self.state_name = state_name


class GPUDispatchError(ExecutionError):
    """Raised when GPU compute dispatch fails."""
    
    def __init__(self, message: str, group_size: tuple = None, operation: str = None):
        super().__init__(message)
        self.group_size = group_size
        self.operation = operation


class CopyTextureError(ExecutionError):
    """Raised when texture copy operation fails."""
    
    def __init__(self, message: str, src_size: tuple = None, dst_size: tuple = None,
                 format: str = None):
        super().__init__(message)
        self.src_size = src_size
        self.dst_size = dst_size
        self.format = format


# =============================================================================
# Resource Errors
# =============================================================================

class ResourceError(ComputeNodesError):
    """Base exception for resource-related errors."""
    pass


class TextureCreateError(ResourceError):
    """Raised when GPU texture creation fails."""
    
    def __init__(self, message: str, size: tuple = None, format: str = None):
        super().__init__(message)
        self.size = size
        self.format = format


class TextureReadbackError(ResourceError):
    """Raised when texture data readback to CPU fails."""
    
    def __init__(self, message: str, texture_size: tuple = None, image_name: str = None):
        super().__init__(message)
        self.texture_size = texture_size
        self.image_name = image_name


class ResourceNotFoundError(ResourceError):
    """Raised when a required resource is not found."""
    
    def __init__(self, message: str, resource_name: str = None, resource_index: int = None):
        super().__init__(message)
        self.resource_name = resource_name
        self.resource_index = resource_index


# =============================================================================
# Rasterizer Errors
# =============================================================================

class RasterizeError(ComputeNodesError):
    """Base exception for rasterization errors."""
    pass


class InvalidCameraError(RasterizeError):
    """Raised when camera is invalid or missing."""
    pass


class MissingAttributeError(RasterizeError):
    """Raised when mesh attribute is not found."""
    
    def __init__(self, message: str, attribute_name: str = None):
        super().__init__(message)
        self.attribute_name = attribute_name
