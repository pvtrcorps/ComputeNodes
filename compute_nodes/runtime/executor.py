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
        """Map resource indices to GPU textures."""
        texture_map = {}
        self._resource_textures.clear()
        
        for idx, res_desc in enumerate(graph.resources):
            if not isinstance(res_desc, ImageDesc):
                continue
            
            is_write = 'WRITE' in res_desc.access.name
            image = bpy.data.images.get(res_desc.name)
            
            # AUTO-CREATE: If image doesn't exist and we need to write, create it
            if image is None and is_write:
                # Map format string to Blender settings
                is_float = res_desc.format in ('RGBA32F', 'RGBA16F', 'R32F')
                
                width = res_desc.size[0] if res_desc.size[0] > 0 else context_width
                height = res_desc.size[1] if res_desc.size[1] > 0 else context_height
                
                image = bpy.data.images.new(
                    name=res_desc.name,
                    width=width,
                    height=height,
                    alpha=True,
                    float_buffer=is_float
                )
                logger.info(f"Created output image: {res_desc.name} ({width}x{height}, float={is_float})")
            
            # RESIZE: If image exists but size differs, resize it
            elif image and is_write and res_desc.size != (0, 0):
                if (image.size[0], image.size[1]) != res_desc.size:
                    image.scale(res_desc.size[0], res_desc.size[1])
                    logger.info(f"Resized image {res_desc.name} to {res_desc.size}")
                
            if image and not is_write:
                # READ-ONLY: Use sampler path
                tex = self.texture_mgr.get_texture_from_image(image)
                res_desc.format = tex.format
                
            elif image and is_write:
                # WRITABLE: Create dedicated storage texture
                if res_desc.size == (0, 0):
                    res_desc.size = (image.size[0], image.size[1])
                
                res_desc.format = "RGBA32F"
                tex = self.texture_mgr.create_storage_texture(
                    name=res_desc.name,
                    width=res_desc.size[0],
                    height=res_desc.size[1],
                    format=res_desc.format
                )
                
            else:
                if res_desc.size == (0, 0):
                    res_desc.size = (context_width, context_height)
                tex = self.texture_mgr.ensure_internal_texture(res_desc.name, res_desc)
                image = None
            
            texture_map[idx] = tex
            self._resource_textures[idx] = (tex, image if is_write else None)
        
        return texture_map


    def _run_pass(self, graph, compute_pass: ComputePass, texture_map, width, height):
        """Execute a single compute pass."""
        src = compute_pass.display_source or compute_pass.source
        shader = self.shader_mgr.get_shader(src, resources=graph.resources)
        shader.bind()
        
        # Bind resources
        used_indices = compute_pass.reads_idx.union(compute_pass.writes_idx)
        
        for idx in used_indices:
            if idx not in texture_map:
                continue
                
            tex = texture_map[idx]
            uniform_name = f"img_{idx}"
            res_desc = graph.resources[idx]
            is_read_only = (res_desc.access.name == 'READ')
            
            try:
                if is_read_only:
                    shader.uniform_sampler(uniform_name, tex)
                else:
                    shader.image(uniform_name, tex)
            except Exception as e:
                logger.error(f"Failed to bind {uniform_name}: {e}")

        # Dispatch
        local_x, local_y = 16, 16
        group_x = math.ceil(width / local_x)
        group_y = math.ceil(height / local_y)
        
        try:
            gpu.compute.dispatch(shader, group_x, group_y, 1)
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
