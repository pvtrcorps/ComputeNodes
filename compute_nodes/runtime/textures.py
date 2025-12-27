"""
TextureManager for Compute Nodes runtime.

Manages GPU textures for compute graph execution.
"""

import logging
import bpy
import gpu

from ..ir.resources import ImageDesc

logger = logging.getLogger(__name__)


class TextureManager:
    """Manages GPU textures for the compute graph runtime."""
    
    def __init__(self):
        self._internal_textures = {}
        self._input_textures = {}
    
    def get_texture_from_image(self, image: bpy.types.Image) -> gpu.types.GPUTexture:
        """Get a READ-ONLY GPU texture from a Blender Image."""
        if not image:
            raise ValueError("TextureManager: Received None image for input.")
        
        try:
            texture = gpu.texture.from_image(image)
            return texture
        except Exception as e:
            logger.error(f"Failed to create texture from image {image.name}: {e}")
            raise

    def create_storage_texture(self, name: str, width: int, height: int, 
                               format: str = "RGBA32F") -> gpu.types.GPUTexture:
        """Create a writable storage texture for compute shader output."""
        if name in self._internal_textures:
            existing = self._internal_textures[name]
            if existing.width == width and existing.height == height:
                return existing
        
        fmt = format.upper()
        
        try:
            texture = gpu.types.GPUTexture((width, height), format=fmt)
            self._internal_textures[name] = texture
            return texture
        except Exception as e:
            logger.error(f"Failed to create storage texture {name}: {e}")
            raise

    def ensure_internal_texture(self, name: str, desc: ImageDesc) -> gpu.types.GPUTexture:
        """Get or create an internal GPU texture based on the descriptor.
        
        Supports 1D, 2D, and 3D textures based on desc.dimensions.
        """
        fmt = desc.format.upper() if desc.format else "RGBA32F"
        dims = getattr(desc, 'dimensions', 2)
        
        # Determine size tuple based on dimensions
        if dims == 1:
            size = (desc.width,)
        elif dims == 3:
            size = (desc.width, desc.height, desc.depth)
        else:
            size = (desc.width, desc.height)
        
        # Check cache
        if name in self._internal_textures:
            existing = self._internal_textures[name]
            # Verify dimensions match
            if dims == 1:
                if existing.width == size[0]:
                    return existing
            elif dims == 3:
                # GPUTexture may not expose depth, compare what we can
                if existing.width == size[0] and existing.height == size[1]:
                    return existing
            else:
                if existing.width == size[0] and existing.height == size[1]:
                    return existing
        
        try:
            # For 3D textures, Blender requires initial data
            if dims == 3:
                import numpy as np
                total_elements = size[0] * size[1] * size[2] * 4  # RGBA
                data = np.zeros(total_elements, dtype=np.float32)
                buffer = gpu.types.Buffer('FLOAT', total_elements, data.tolist())
                texture = gpu.types.GPUTexture(size, layers=0, is_cubemap=False, 
                                                format=fmt, data=buffer)
            else:
                texture = gpu.types.GPUTexture(size, format=fmt)
            
            self._internal_textures[name] = texture
            logger.debug(f"Created {dims}D texture '{name}': {size}, format={fmt}")
            return texture
        except Exception as e:
            logger.error(f"Failed to create {dims}D texture {name}: {e}")
            raise

    def readback_to_image(self, texture: gpu.types.GPUTexture, 
                          image: bpy.types.Image) -> bool:
        """
        Read texture data back to a Blender Image datablock.
        
        Uses GPUFrameBuffer.read_color() - the Buffer is a nested structure
        where len(buffer) = height and each row has width*4 elements.
        """
        if not texture or not image:
            return False
            
        try:
            width = texture.width
            height = texture.height
            
            # Ensure image dimensions match texture
            if width != image.size[0] or height != image.size[1]:
                image.scale(width, height)
            
            # Optimized readback avoiding Python loops
            # texture.read() returns the raw data (Buffer)
            data = texture.read()
            
            # Create a flat float buffer wrapper for the data
            buffer_size = width * height * 4
            buffer = gpu.types.Buffer('FLOAT', buffer_size, data)
            
            # Direct transfer to image pixels
            image.pixels.foreach_set(buffer)
            image.update()
            
            return True
            
        except Exception as e:
            logger.error(f"Readback failed: {e}")
            return False

    def clear_texture(self, texture: gpu.types.GPUTexture, 
                      color: tuple = (0.0, 0.0, 0.0, 1.0)):
        """Clear a texture to a specific color."""
        if not texture:
            return
        try:
            fb = gpu.types.GPUFrameBuffer(color_slots=texture)
            with fb.bind():
                gpu.state.active_framebuffer_get().clear(color=color)
        except Exception as e:
            logger.error(f"Failed to clear texture: {e}")

    def clear(self):
        """Free all cached textures."""
        self._internal_textures.clear()
        self._input_textures.clear()

    def get_cached_texture(self, name: str) -> gpu.types.GPUTexture:
        """Get a cached internal texture by name."""
        return self._internal_textures.get(name)


class DynamicTexturePool:
    """
    Lazy-allocates textures on demand and caches them by size.
    
    Used for dynamic resolution scenarios where texture sizes aren't
    known until runtime (e.g., Resize inside loops with computed dimensions).
    
    Key difference from TextureManager:
    - TextureManager: caches by NAME (one texture per resource name)
    - DynamicTexturePool: caches by SIZE (reusable pool of textures)
    """
    
    def __init__(self):
        # Cache keyed by (size_tuple, format, dimensions)
        # Value is a list of available textures at that size
        self._pool: dict[tuple, list[gpu.types.GPUTexture]] = {}
        # Currently in-use textures (can't be reused until released)
        self._in_use: dict[int, tuple] = {}  # texture_id -> key
        self._logger = logging.getLogger(__name__)
    
    def get_or_create(self, size: tuple, format: str = 'RGBA32F', 
                      dims: int = 2) -> gpu.types.GPUTexture:
        """
        Get a texture of the specified size from pool, or create one.
        
        Args:
            size: (width,), (width, height), or (width, height, depth)
            format: Texture format (default RGBA32F)
            dims: 1, 2, or 3 dimensional
        
        Returns:
            A GPU texture of the requested size
        """
        key = (size, format.upper(), dims)
        
        # Check pool for available texture
        if key in self._pool and self._pool[key]:
            texture = self._pool[key].pop()
            self._in_use[id(texture)] = key
            self._logger.debug(f"DynamicPool: reusing texture {size}")
            return texture
        
        # Create new texture
        try:
            if dims == 3:
                import numpy as np
                total = size[0] * size[1] * size[2] * 4
                data = np.zeros(total, dtype=np.float32)
                buffer = gpu.types.Buffer('FLOAT', total, data.tolist())
                texture = gpu.types.GPUTexture(size, layers=0, is_cubemap=False,
                                               format=format.upper(), data=buffer)
            else:
                texture = gpu.types.GPUTexture(size, format=format.upper())
            
            self._in_use[id(texture)] = key
            self._logger.debug(f"DynamicPool: created new texture {size}")
            return texture
            
        except Exception as e:
            self._logger.error(f"DynamicPool: failed to create {dims}D texture {size}: {e}")
            raise
    
    def release(self, texture: gpu.types.GPUTexture) -> None:
        """Return a texture to the pool for reuse."""
        tex_id = id(texture)
        if tex_id in self._in_use:
            key = self._in_use.pop(tex_id)
            if key not in self._pool:
                self._pool[key] = []
            self._pool[key].append(texture)
            self._logger.debug(f"DynamicPool: released texture {key[0]}")
    
    def release_all(self) -> None:
        """Release all in-use textures back to pool."""
        for tex_id, key in list(self._in_use.items()):
            if key not in self._pool:
                self._pool[key] = []
            # Can't get texture from id, just clear the tracking
        self._in_use.clear()
    
    def clear(self) -> None:
        """Free all textures from pool."""
        self._pool.clear()
        self._in_use.clear()
    
    def stats(self) -> dict:
        """Get pool statistics."""
        available = sum(len(v) for v in self._pool.values())
        in_use = len(self._in_use)
        sizes = list(self._pool.keys())
        return {
            'available': available,
            'in_use': in_use,
            'sizes': sizes
        }

