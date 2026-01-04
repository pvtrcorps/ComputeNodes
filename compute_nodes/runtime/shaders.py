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

    def get_shader(self, source: str, resources=None, reads_idx=None, writes_idx=None, dispatch_size=None):
        """
        Compile or return a cached compute shader.
        
        Args:
            source (str): GLSL compute shader source code.
            resources (List[ResourceDesc]): List of resources to define interface.
            reads_idx (set): Resource indices that are READ in this pass (use sampler)
            writes_idx (set): Resource indices that are WRITTEN in this pass (use image)
            dispatch_size (tuple): (w, h, d) dispatch dimensions to determine workgroup size
            
        Returns:
            gpu.types.GPUShader: The compiled shader.
        """
        # OPTIMIZED: Use hash(source) as primary cache key for O(1) lookup
        # The built-in hash() is much faster than SHA256
        cache_key = hash(source)
        
        if cache_key in self._shader_cache:
            logger.debug(f"Shader cache HIT")
            return self._shader_cache[cache_key]
        
        # Cache miss - need to compile
        logger.debug(f"Shader cache MISS - compiling new shader")
        
        # Compile new shader
        try:
            shader_info = gpu.types.GPUShaderCreateInfo()
            
            # Define Interface from Resources
            reads_set = reads_idx or set()
            writes_set = writes_idx or set()
            
            if resources:
                from ..ir.resources import ImageDesc, ResourceType
                
                # Only bind resources used in this pass
                used_indices = reads_set | writes_set
                
                # Create resource index -> sequential binding slot mapping
                # GPU has max 8 binding slots (0-7), so we remap sparse indices
                sorted_indices = sorted(used_indices)
                binding_map = {res_idx: slot for slot, res_idx in enumerate(sorted_indices)}
                
                for res_idx in sorted_indices:
                    res = resources[res_idx]
                    
                    # Use sequential binding slot to stay within GPU limit
                    binding_slot = binding_map[res_idx]
                    uniform_name = f"img_{binding_slot}"  # Match GLSL codegen
                    
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
                    is_read = res_idx in reads_set
                    is_write = res_idx in writes_set
                    
                    if is_read and not is_write:
                        # Read-only in this pass: use sampler for texture()
                        shader_info.sampler(binding_slot, sampler_type, uniform_name)
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
                        shader_info.image(binding_slot, fmt, image_type, uniform_name, qualifiers=qualifiers)
            
            # Push constants for Position normalization
            shader_info.push_constant('INT', 'u_dispatch_width')
            shader_info.push_constant('INT', 'u_dispatch_height')
            shader_info.push_constant('INT', 'u_dispatch_depth')
            
            # Push constant for multi-pass loop iteration index and buffer dimensions
            shader_info.push_constant('INT', 'u_loop_iteration')
            shader_info.push_constant('INT', 'u_loop_read_width')
            shader_info.push_constant('INT', 'u_loop_read_height')
            shader_info.push_constant('INT', 'u_loop_write_width')
            shader_info.push_constant('INT', 'u_loop_write_height')
            
            # Workgroup size based on dispatch dimensions, not resources
            # This prevents mismatch when sampling 3D from a 2D dispatch
            dispatch_d = dispatch_size[2] if dispatch_size else 1
            if dispatch_d > 1:
                # True 3D dispatch - use 3D workgroups
                shader_info.local_group_size(8, 8, 8)
            else:
                # 2D dispatch (even if reading from 3D textures)
                shader_info.local_group_size(16, 16, 1)
            
            # Add compute source AFTER push constants and local_group_size
            shader_info.compute_source(source)
            
            shader = gpu.shader.create_from_info(shader_info)
            self._shader_cache[cache_key] = shader
            logger.debug(f"Compiled and cached new shader")
            return shader
            
        except Exception as e:
            print(f"Shader compile error: {e}")
            # Log source for debugging
            print("--- SHADER SOURCE ---")
            lines = source.split('\n')
            for i, line in enumerate(lines):
                print(f"{i+1:03d}: {line}")
            print("---------------------")
            raise

    def clear(self):
        """Clear the shader cache."""
        self._shader_cache.clear()
        logger.debug("Shader cache cleared")
