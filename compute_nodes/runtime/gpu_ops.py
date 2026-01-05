
import logging
import math
import gpu
import platform
import ctypes

logger = logging.getLogger(__name__)

class GPUOps:
    """
    Handles low-level GPU operations for Compute Executor.
    
    - Texture Copying (Blit via Compute)
    - Memory Barriers (Synchronization)
    - Shader Caching for utility shaders
    """
    
    def __init__(self):
        self._copy_shader_cache = {}

    def copy_texture(self, src, dst, format='RGBA32F', dimensions=2):
        """Copy contents from one texture to another using a compute shader."""
        # Get dimensions
        width = src.width
        height = src.height
        depth = 1
        if dimensions == 3 and hasattr(src, 'depth'):
            depth = src.depth
        
        # Get specialized shader
        shader = self._get_copy_shader(format, dimensions)
        shader.bind()
        
        shader.image('src_tex', src)
        shader.image('dst_tex', dst)
        
        # Dispatch
        if dimensions == 3:
            # 3D Dispatch (8x8x8 local groups)
            group_x = math.ceil(width / 8)
            group_y = math.ceil(height / 8)
            group_z = math.ceil(depth / 8)
        else:
            # 2D Dispatch (16x16 local groups)
            group_x = math.ceil(width / 16)
            group_y = math.ceil(height / 16)
            group_z = 1
            
        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Copy dispatch failed: {e}")
        
        self.memory_barrier()
        logger.debug(f"Texture copy ({dimensions}D, {format}): {width}x{height}x{depth}")

    def _get_copy_shader(self, format, dimensions):
        """Get or create a cached copy shader for the given format/dimensions."""
        key = (format, dimensions)
        if key in self._copy_shader_cache:
            return self._copy_shader_cache[key]
        
        # Generate Shader
        is_3d = (dimensions == 3)
        img_type = 'FLOAT_3D' if is_3d else 'FLOAT_2D'
        coord_type = 'ivec3' if is_3d else 'ivec2'
        load_coord = 'ivec3(gl_GlobalInvocationID.xyz)' if is_3d else 'ivec2(gl_GlobalInvocationID.xy)'
        
        copy_src = f"""
        void main() {{
            {coord_type} coord = {load_coord};
            vec4 val = imageLoad(src_tex, coord);
            imageStore(dst_tex, coord, val);
        }}
        """
        
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.image(0, format, img_type, 'src_tex', qualifiers={'READ'})
        shader_info.image(1, format, img_type, 'dst_tex', qualifiers={'WRITE'})
        
        if is_3d:
            shader_info.local_group_size(8, 8, 8)
        else:
            shader_info.local_group_size(16, 16, 1)
            
        shader_info.compute_source(copy_src)
        
        try:
            shader = gpu.shader.create_from_info(shader_info)
            self._copy_shader_cache[key] = shader
            return shader
        except Exception as e:
            logger.error(f"Failed to compile copy shader ({format}, {dimensions}D): {e}")
            raise

    def memory_barrier(self):
        """
        Insert a memory barrier to synchronize texture operations between passes.
        """
        try:
            GL_ALL_BARRIER_BITS = 0xFFFFFFFF
            
            if platform.system() == 'Windows':
                opengl32 = ctypes.windll.opengl32
                glMemoryBarrier = opengl32.glMemoryBarrier
            else:
                # Linux/macOS: use libGL
                try:
                    libgl = ctypes.CDLL('libGL.so.1')
                except OSError:
                    try:
                        libgl = ctypes.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
                    except OSError:
                        return
                glMemoryBarrier = libgl.glMemoryBarrier
            
            glMemoryBarrier.argtypes = [ctypes.c_uint]
            glMemoryBarrier(GL_ALL_BARRIER_BITS)
        except Exception as e:
            # logger.debug(f"Memory barrier not available: {e}")
            pass

    def gl_finish(self):
        """Wait for all GPU commands to complete (for profiling)."""
        try:
            if platform.system() == 'Windows':
                opengl32 = ctypes.windll.opengl32
                glFinish = opengl32.glFinish
            else:
                try:
                    libgl = ctypes.CDLL('libGL.so.1')
                except OSError:
                    try:
                        libgl = ctypes.CDLL('/System/Library/Frameworks/OpenGL.framework/OpenGL')
                    except OSError:
                        return
                glFinish = libgl.glFinish
            
            glFinish()
        except Exception as e:
            pass
