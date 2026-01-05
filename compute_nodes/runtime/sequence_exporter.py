
import logging
import os
import math
import numpy as np
import bpy
import gpu

logger = logging.getLogger(__name__)

class SequenceExporter:
    """
    Handles exporting Grid3D textures as image sequences (Z-slices).
    
    Uses a compute shader to extract Z-slices to a 2D texture for saving.
    """
    
    def __init__(self):
        self._slice_shader = None

    def write_sequence_outputs(self, graph, texture_map):
        """Write Grid3D textures as Z-slice image sequences."""
        
        # Lazy-create slice extraction shader
        if not self._slice_shader:
            self._create_slice_shader()
        
        for seq_info in graph.sequence_outputs:
            src_idx = seq_info['source_resource_idx']
            directory = seq_info['directory']
            pattern = seq_info['filename_pattern']
            format_type = seq_info['format']
            width = seq_info['width']
            height = seq_info['height']
            depth = seq_info['depth']
            start_index = seq_info['start_index']
            color_depth = seq_info.get('color_depth', '16')
            
            # Get the GPU texture
            if src_idx not in texture_map:
                logger.warning(f"Sequence output: source texture {src_idx} not found")
                continue
                
            tex3d = texture_map[src_idx]
            
            # Resolve directory path
            abs_dir = bpy.path.abspath(directory)
            try:
                os.makedirs(abs_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Failed to create directory {abs_dir}: {e}")
                continue
            
            logger.info(f"Writing sequence: {depth} slices to {abs_dir}")
            
            # Create 2D target texture for slice extraction
            tex2d = gpu.types.GPUTexture((width, height), format='RGBA32F')
            
            # Create Blender Image for writing
            temp_img_name = f"__seq_temp_{src_idx}"
            temp_image = bpy.data.images.new(
                name=temp_img_name,
                width=width,
                height=height,
                alpha=True,
                float_buffer=True
            )
            
            # Configure format settings
            scene = bpy.context.scene
            old_format = scene.render.image_settings.file_format
            old_mode = scene.render.image_settings.color_mode
            old_depth = scene.render.image_settings.color_depth
            
            if format_type == 'PNG':
                scene.render.image_settings.file_format = 'PNG'
                scene.render.image_settings.color_depth = color_depth
            elif format_type == 'TIFF':
                scene.render.image_settings.file_format = 'TIFF'
                scene.render.image_settings.color_depth = color_depth
            else:
                scene.render.image_settings.file_format = 'OPEN_EXR'
                scene.render.image_settings.color_depth = '32'
            scene.render.image_settings.color_mode = 'RGBA'
            
            try:
                for z in range(depth):
                    # Extract slice using compute shader
                    self._extract_slice(tex3d, tex2d, z, width, height)
                    
                    # Read 2D texture to CPU
                    raw_data = tex2d.read()
                    
                    # Safe Buffer to numpy/list handling
                    # gpu.types.Buffer to list or numpy
                    # Assuming raw_data is Buffer
                    data_list = raw_data.to_list()
                    # Flatten if nested (Buffer 2D list)
                    # For image.pixels we need flat list
                    if isinstance(data_list[0], list):
                        # Flatten list of lists [[r,g,b,a], ...] or rows
                        # 2D Buffer to_list gives [[pixel, pixel], [pixel, pixel]]
                        # Pixel is [r,g,b,a]
                        flat_data = [
                            c 
                            for row in data_list 
                            for pixel in row 
                            for c in pixel
                        ]
                    else:
                        flat_data = data_list
                    
                    # Write to temp image
                    temp_image.pixels.foreach_set(flat_data)
                    temp_image.update()
                    
                    # Save to file
                    filename = pattern.format(start_index + z)
                    filepath = os.path.join(abs_dir, filename)
                    temp_image.save_render(filepath)
                    
                    if z == 0 or z == depth - 1:
                        logger.debug(f"  Wrote: {filename}")
                
                logger.info(f"Sequence complete: {depth} slices written")
                
            except Exception as e:
                logger.error(f"Failed to write sequence: {e}")
                import traceback
                traceback.print_exc()
            finally:
                # Cleanup
                bpy.data.images.remove(temp_image)
                scene.render.image_settings.file_format = old_format
                scene.render.image_settings.color_mode = old_mode
                scene.render.image_settings.color_depth = old_depth
    
    def _create_slice_shader(self):
        """Create compute shader for extracting Z-slices from 3D textures."""
        slice_src = """
        void main() {
            ivec2 coord = ivec2(gl_GlobalInvocationID.xy);
            ivec3 coord3d = ivec3(coord.x, coord.y, u_slice_z);
            vec4 val = imageLoad(src_3d, coord3d);
            imageStore(dst_2d, coord, val);
        }
        """
        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.image(0, 'RGBA32F', 'FLOAT_3D', 'src_3d', qualifiers={'READ'})
        shader_info.image(1, 'RGBA32F', 'FLOAT_2D', 'dst_2d', qualifiers={'WRITE'})
        shader_info.push_constant('INT', 'u_slice_z')
        shader_info.local_group_size(16, 16, 1)
        shader_info.compute_source(slice_src)
        
        try:
            self._slice_shader = gpu.shader.create_from_info(shader_info)
            logger.debug("Created slice extraction shader")
        except Exception as e:
            logger.error(f"Failed to compile slice shader: {e}")

    def _extract_slice(self, tex3d, tex2d, z, width, height):
        """Extract a single Z-slice from 3D texture to 2D texture."""
        if not self._slice_shader:
            return
            
        shader = self._slice_shader
        shader.bind()
        
        # Bind textures as images
        shader.image('src_3d', tex3d)
        shader.image('dst_2d', tex2d)
        shader.uniform_int('u_slice_z', z)
        
        # Dispatch
        group_x = math.ceil(width / 16)
        group_y = math.ceil(height / 16)
        gpu.compute.dispatch(shader, group_x, group_y, 1)
