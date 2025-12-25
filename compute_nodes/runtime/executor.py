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

        # Phase 3: Readback results
        self._readback_results(graph, texture_map)

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
            
        # Calculate work groups
        local_x, local_y, local_z = 16, 16, 1
        group_x = math.ceil(dispatch_w / local_x)
        group_y = math.ceil(dispatch_h / local_y)
        group_z = math.ceil(dispatch_d / local_z)
        
        logger.debug(f"Pass {compute_pass.id}: dispatch({dispatch_w}x{dispatch_h}x{dispatch_d}) -> groups({group_x}x{group_y}x{group_z})")
        
        # Set dispatch size uniforms for Position normalization
        try:
            shader.uniform_int("u_dispatch_width", dispatch_w)
            shader.uniform_int("u_dispatch_height", dispatch_h)
        except Exception as e:
            logger.debug(f"Could not set dispatch uniforms: {e}")
        
        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Dispatch failed: {e}")

    def _readback_results(self, graph, texture_map):
        """Readback writable textures to their associated Blender Images."""
        for idx, (tex, image) in self._resource_textures.items():
            if image is None:
                continue
                
            res_desc = graph.resources[idx]
            if res_desc.access.name not in {'WRITE', 'READ_WRITE'}:
                continue
            
            self.texture_mgr.readback_to_image(tex, image)
