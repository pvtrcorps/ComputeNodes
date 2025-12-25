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

    def get_shader(self, source: str, resources=None, reads_idx=None, writes_idx=None):
        """
        Compile or return a cached compute shader.
        
        Args:
            source (str): GLSL compute shader source code.
            resources (List[ResourceDesc]): List of resources to define interface.
            reads_idx (set): Resource indices that are READ in this pass (use sampler)
            writes_idx (set): Resource indices that are WRITTEN in this pass (use image)
            
        Returns:
            gpu.types.GPUShader: The compiled shader.
        """
        # Create a robust cache key
        res_sig = ""
        reads_set = reads_idx or set()
        writes_set = writes_idx or set()
        
        if resources:
            for i, res in enumerate(resources):
                fmt_sig = getattr(res, 'format', 'NONE')
                # Include pass-specific access in cache key
                pass_access = "R" if i in reads_set else ""
                pass_access += "W" if i in writes_set else ""
                res_sig += f"{i}:{res.name}:{pass_access}:{fmt_sig};"
        
        key = hashlib.sha256((source + res_sig).encode('utf-8')).hexdigest()
        
        if key in self._shader_cache:
            logger.debug(f"Using cached shader: {key[:16]}...")
            return self._shader_cache[key]
        
        # Compile new shader
        try:
            shader_info = gpu.types.GPUShaderCreateInfo()
            
            # Define Interface from Resources
            if resources:
                from ..ir.resources import ImageDesc, ResourceType
                
                # Only bind resources used in this pass
                used_indices = reads_set | writes_set
                
                for i, res in enumerate(resources):
                    if i not in used_indices:
                        continue
                        
                    uniform_name = f"img_{i}"
                    
                    # Determine image type based on dimensions
                    if isinstance(res, ImageDesc):
                        dims = getattr(res, 'dimensions', 2)
                        if dims == 1:
                            sampler_type = "FLOAT_1D"
                            image_type = "FLOAT_1D"
                        elif dims == 3:
                            sampler_type = "FLOAT_3D"
                            image_type = "FLOAT_3D"
                        else:
                            sampler_type = "FLOAT_2D"
                            image_type = "FLOAT_2D"
                    else:
                        sampler_type = "FLOAT_2D"
                        image_type = "FLOAT_2D"
                    
                    # Determine binding based on PASS-SPECIFIC access
                    is_read = i in reads_set
                    is_write = i in writes_set
                    
                    if is_read and not is_write:
                        # Read-only in this pass: use sampler for texture()
                        shader_info.sampler(i, sampler_type, uniform_name)
                    else:
                        # Write or read-write: use image for imageStore/imageLoad
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
                        shader_info.image(i, fmt, image_type, uniform_name, qualifiers=qualifiers)
            
            # Detect if any USED resource is 3D to choose appropriate workgroup size
            has_3d = False
            if resources:
                used_indices = reads_set | writes_set
                for idx in used_indices:
                    if idx < len(resources):
                        res = resources[idx]
                        if isinstance(res, ImageDesc) and getattr(res, 'dimensions', 2) == 3:
                            has_3d = True
                            break
            
            # Push constants for Position normalization
            shader_info.push_constant('INT', 'u_dispatch_width')
            shader_info.push_constant('INT', 'u_dispatch_height')
            shader_info.push_constant('INT', 'u_dispatch_depth')
            
            # Dynamic local group size based on dimension type
            # 2D: 16x16x1 (256 threads), 3D: 8x8x8 (512 threads)
            if has_3d:
                shader_info.local_group_size(8, 8, 8)
            else:
                shader_info.local_group_size(16, 16, 1)
            
            # Add compute source AFTER push constants and local_group_size
            shader_info.compute_source(source)
            
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
