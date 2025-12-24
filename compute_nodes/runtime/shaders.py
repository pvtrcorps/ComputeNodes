"""
ShaderManager for Compute Nodes runtime.

Manages compilation and caching of GLSL compute shaders.
"""

import logging
import hashlib
import gpu

logger = logging.getLogger(__name__)


class ShaderManager:
    """
    Manages the compilation and caching of GLSL compute shaders.
    Ensures that shaders are reused based on their source code and configuration.
    """
    
    def __init__(self):
        # Cache: hash(key) -> GPUShader
        self._shader_cache = {}

    def get_shader(self, source: str, resources=None) -> gpu.types.GPUShader:
        """
        Get or compile a compute shader.
        
        Args:
            source (str): The full GLSL source code.
            resources (List[ResourceDesc]): List of resources to define interface.
            
        Returns:
            gpu.types.GPUShader: The compiled shader.
        """
        # Create a robust cache key
        res_sig = ""
        if resources:
            for i, res in enumerate(resources):
                fmt_sig = getattr(res, 'format', 'NONE')
                res_sig += f"{i}:{res.name}:{res.access.name}:{fmt_sig};"
        
        key = hashlib.sha256((source + res_sig).encode('utf-8')).hexdigest()
        
        if key in self._shader_cache:
            logger.debug(f"Using cached shader: {key[:16]}...")
            return self._shader_cache[key]
        
        # Compile new shader
        try:
            shader_info = gpu.types.GPUShaderCreateInfo()
            
            # Define Interface from Resources
            if resources:
                from ..ir.resources import ImageDesc
                for i, res in enumerate(resources):
                    uniform_name = f"img_{i}"
                    access_name = res.access.name
                    
                    if access_name == 'READ':
                        # Use Sampler for Read-Only inputs
                        shader_info.sampler(i, "FLOAT_2D", uniform_name)
                    else:
                        # Write or Read-Write requires Image Load/Store
                        if hasattr(res, 'format') and res.format:
                            raw_fmt = res.format.upper()
                            # Map incompatible Blender formats
                            fmt_map = {
                                'SRGB8_A8': 'RGBA8', 
                                'SRGB8_A8_DXT1': 'RGBA8',
                                'SRGB8_A8_DXT3': 'RGBA8',
                                'SRGB8_A8_DXT5': 'RGBA8',
                            }
                            fmt = fmt_map.get(raw_fmt, raw_fmt)
                        else:
                            fmt = 'RGBA32F'
                            
                        qualifiers = {'READ', 'WRITE'}
                        shader_info.image(i, fmt, "FLOAT_2D", uniform_name, qualifiers=qualifiers)

            shader_info.compute_source(source)
            shader_info.local_group_size(16, 16, 1)
            
            shader = gpu.shader.create_from_info(shader_info)
            self._shader_cache[key] = shader
            logger.debug(f"Compiled new shader: {key[:16]}...")
            return shader
            
        except Exception as e:
            logger.error(f"Shader compile error: {e}")
            # Log source for debugging
            lines = source.split('\n')
            for i, line in enumerate(lines):
                logger.debug(f"{i+1:03d}: {line}")
            raise

    def clear(self):
        """Clear the shader cache."""
        self._shader_cache.clear()
        logger.debug("Shader cache cleared")
