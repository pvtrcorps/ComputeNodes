"""
ComputeExecutor for Compute Nodes runtime.

Orchestrates the execution of compute graphs:
- Resolves resources to GPU textures
- Binds shaders and dispatches compute work
- Handles readback to Blender Image datablocks
"""

import logging
import math
import bpy
import gpu
from .textures import TextureManager
from .shaders import ShaderManager
from ..planner.passes import ComputePass
from ..ir.resources import ImageDesc

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """
    Orchestrates the execution of a compute graph.
    
    Binds resources, sets uniforms, and dispatches compute shaders.
    """
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        self._resource_textures = {}

    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """Execute the entire graph by running passes in order."""
        # Phase 1: Resolve Resources
        texture_map = self._resolve_resources(graph, context_width, context_height)
        
        # Phase 2: Execute Passes
        for compute_pass in passes:
            self._run_pass(graph, compute_pass, texture_map, context_width, context_height)

        # Phase 3: Readback results to Blender Images
        self._readback_results(graph, texture_map)
        
        # Phase 4: Write sequence outputs (Grid3D → Z-slice files)
        if hasattr(graph, 'sequence_outputs') and graph.sequence_outputs:
            self._write_sequence_outputs(graph, texture_map)

    def _resolve_resources(self, graph, context_width, context_height) -> dict:
        """Map resource indices to GPU textures.
        
        Resource handling based on is_internal flag:
        - is_internal=True (Rasterize, Resize): GPU-only texture, no Blender Image
        - is_internal=False (Output): Creates/uses Blender Image datablock
        """
        texture_map = {}
        self._resource_textures.clear()
        
        for idx, res_desc in enumerate(graph.resources):
            if not isinstance(res_desc, ImageDesc):
                continue
            
            is_write = 'WRITE' in res_desc.access.name
            is_internal = getattr(res_desc, 'is_internal', True)  # Default True for GPU-only
            
            if is_internal:
                # GPU-ONLY: Internal texture (Rasterize, Resize)
                # No Blender Image datablock needed - pure VRAM
                if res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, None)  # No image for internal
                logger.debug(f"Internal GPU texture: {res_desc.name} {res_desc.size}")
                
            else:
                # OUTPUT: Needs Blender Image datablock for CPU readback
                image = bpy.data.images.get(res_desc.name)
                
                width = res_desc.size[0] if res_desc.size[0] > 0 else context_width
                height = res_desc.size[1] if res_desc.size[1] > 0 else context_height
                is_float = res_desc.format.upper() in ('RGBA32F', 'RGBA16F', 'R32F')
                
                # Create if doesn't exist
                if image is None and is_write:
                    image = bpy.data.images.new(
                        name=res_desc.name,
                        width=width,
                        height=height,
                        alpha=True,
                        float_buffer=is_float
                    )
                    logger.info(f"Created output image: {res_desc.name} ({width}x{height})")
                
                # Resize if needed
                elif image and is_write:
                    if (image.size[0], image.size[1]) != (width, height):
                        image.scale(width, height)
                        logger.info(f"Resized image {res_desc.name} to {width}x{height}")
                
                if image and not is_write:
                    # READ-ONLY from existing image
                    tex = self.texture_mgr.get_texture_from_image(image)
                    res_desc.format = tex.format
                elif image and is_write:
                    # WRITABLE output
                    res_desc.size = (width, height)
                    res_desc.format = "RGBA32F"
                    tex = self.texture_mgr.create_storage_texture(
                        name=res_desc.name,
                        width=width,
                        height=height,
                        format=res_desc.format
                    )
                else:
                    # Fallback
                    tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                    image = None
                
                texture_map[idx] = tex
                self._resource_textures[idx] = (tex, image if is_write else None)
        
        return texture_map


    def _run_pass(self, graph, compute_pass: ComputePass, texture_map, context_width, context_height):
        """Execute a single compute pass with its specific dispatch size."""
        src = compute_pass.display_source or compute_pass.source
        
        # Pass read/write indices for correct sampler vs image bindings
        shader = self.shader_mgr.get_shader(
            src, 
            resources=graph.resources,
            reads_idx=compute_pass.reads_idx,
            writes_idx=compute_pass.writes_idx
        )
        shader.bind()
        
        # Bind resources based on PASS-SPECIFIC access
        used_indices = compute_pass.reads_idx.union(compute_pass.writes_idx)
        
        for idx in used_indices:
            if idx not in texture_map:
                continue
                
            tex = texture_map[idx]
            uniform_name = f"img_{idx}"
            
            # Use pass-specific access (read-only in this pass = sampler, write = image)
            is_read_in_pass = idx in compute_pass.reads_idx
            is_write_in_pass = idx in compute_pass.writes_idx
            
            try:
                if is_read_in_pass and not is_write_in_pass:
                    # Read-only in this pass: bind as sampler
                    shader.uniform_sampler(uniform_name, tex)
                else:
                    # Write or read-write: bind as image
                    shader.image(uniform_name, tex)
            except Exception as e:
                logger.error(f"Failed to bind {uniform_name}: {e}")

        # Determine dispatch dimensions from pass or fallback to context
        dispatch_w, dispatch_h, dispatch_d = compute_pass.dispatch_size
        
        if dispatch_w == 0:
            dispatch_w = context_width
        if dispatch_h == 0:
            dispatch_h = context_height
        if dispatch_d == 0:
            dispatch_d = 1
        
        # Detect if this pass uses 3D resources for workgroup size
        has_3d = False
        for idx in used_indices:
            if idx < len(graph.resources):
                res = graph.resources[idx]
                if isinstance(res, ImageDesc) and getattr(res, 'dimensions', 2) == 3:
                    has_3d = True
                    break
        
        # Calculate work groups (must match shader's local_group_size)
        if has_3d:
            local_x, local_y, local_z = 8, 8, 8
        else:
            local_x, local_y, local_z = 16, 16, 1
            
        group_x = math.ceil(dispatch_w / local_x)
        group_y = math.ceil(dispatch_h / local_y)
        group_z = math.ceil(dispatch_d / local_z)
        
        logger.debug(f"Pass {compute_pass.id}: dispatch({dispatch_w}x{dispatch_h}x{dispatch_d}) -> groups({group_x}x{group_y}x{group_z})")
        
        # Set dispatch size uniforms for Position normalization
        try:
            shader.uniform_int("u_dispatch_width", dispatch_w)
            shader.uniform_int("u_dispatch_height", dispatch_h)
            shader.uniform_int("u_dispatch_depth", dispatch_d)
        except Exception as e:
            logger.debug(f"Could not set dispatch uniforms: {e}")
        
        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Dispatch failed: {e}")

    def _readback_results(self, graph, texture_map):
        """Readback writable textures to their associated Blender Images.
        
        Also handles save_mode:
        - DATABLOCK: Just readback (default)
        - SAVE: Readback + save to file
        - PACK: Readback + pack into .blend
        """
        import os
        
        # Get output settings if available
        output_settings = getattr(graph, 'output_image_settings', {})
        
        for idx, (tex, image) in self._resource_textures.items():
            if image is None:
                continue
                
            res_desc = graph.resources[idx]
            if res_desc.access.name not in {'WRITE', 'READ_WRITE'}:
                continue
            
            # Readback GPU → CPU
            self.texture_mgr.readback_to_image(tex, image)
            
            # Handle save mode
            settings = output_settings.get(res_desc.name, {})
            save_mode = settings.get('save_mode', 'DATABLOCK')
            
            if save_mode == 'SAVE':
                filepath = settings.get('filepath', '')
                file_format = settings.get('file_format', 'OPEN_EXR')
                
                if filepath:
                    abs_path = bpy.path.abspath(filepath)
                    
                    # Create directory if needed
                    dir_path = os.path.dirname(abs_path)
                    if dir_path:
                        os.makedirs(dir_path, exist_ok=True)
                    
                    # Configure format
                    scene = bpy.context.scene
                    old_format = scene.render.image_settings.file_format
                    old_mode = scene.render.image_settings.color_mode
                    old_depth = scene.render.image_settings.color_depth
                    
                    scene.render.image_settings.file_format = file_format
                    scene.render.image_settings.color_mode = 'RGBA'
                    if file_format == 'OPEN_EXR':
                        scene.render.image_settings.color_depth = '32'
                    else:
                        scene.render.image_settings.color_depth = '16'
                    
                    image.save_render(abs_path)
                    
                    # Restore
                    scene.render.image_settings.file_format = old_format
                    scene.render.image_settings.color_mode = old_mode
                    scene.render.image_settings.color_depth = old_depth
                    
                    logger.info(f"Saved {res_desc.name} to {abs_path}")
                    
            elif save_mode == 'PACK':
                if not image.packed_file:
                    image.pack()
                    logger.info(f"Packed {res_desc.name} into .blend")


    def _write_sequence_outputs(self, graph, texture_map):
        """Write Grid3D textures as Z-slice image sequences.
        
        Since GPUTexture.read() only reads the first Z-slice of 3D textures,
        we use a compute shader to extract each slice to a 2D texture,
        then write that to disk.
        """
        import os
        import numpy as np
        
        # Lazy-create slice extraction shader
        if not hasattr(self, '_slice_shader'):
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
            os.makedirs(abs_dir, exist_ok=True)
            
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
                    data = np.array(raw_data, dtype=np.float32).flatten()
                    
                    # Write to temp image
                    temp_image.pixels.foreach_set(data.tolist())
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
        
        self._slice_shader = gpu.shader.create_from_info(shader_info)
        logger.debug("Created slice extraction shader")
    
    def _extract_slice(self, tex3d, tex2d, z, width, height):
        """Extract a single Z-slice from 3D texture to 2D texture."""
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

