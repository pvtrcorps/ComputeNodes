import bpy
import gpu
from gpu_extras.batch import batch_for_shader
import numpy as np

class Rasterizer:
    """
    Handles offscreen rendering for:
    1. Mesh Attribute Transfer (Mesh -> Texture via UV)
    2. Scene Capture (Scene -> Texture via Camera)
    """
    
    def __init__(self):
        self._offscreen = None
        self._width = 0
        self._height = 0
        
        # Shader Cache
        self._shaders = {}

    def _ensure_offscreen(self, width: int, height: int):
        """Ensure offscreen buffer exists and has correct size."""
        if (self._offscreen and 
            self._width == width and 
            self._height == height):
            return

        # Free old if exists 
        self._offscreen = None 
        
        try:
            self._offscreen = gpu.types.GPUOffScreen(width, height)
            self._width = width
            self._height = height
        except Exception as e:
            print(f"Rasterizer: Failed to create offscreen {width}x{height}: {e}")
            raise

    # -------------------------------------------------------------------------
    # MESH ATTRIBUTE RASTERIZATION (Mesh -> Texture via UV)
    # -------------------------------------------------------------------------
    
    def get_mesh_attribute_shader(self):
        """
        Returns a shader that draws mesh in UV space (0..1)
        and outputs an attribute as color.
        """
        if "MESH_ATTR" in self._shaders:
            return self._shaders["MESH_ATTR"]

        vert_out = gpu.types.GPUStageInterfaceInfo("mesh_attr_interface")
        vert_out.smooth('VEC4', "v_color")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, 'VEC3', "position")
        shader_info.vertex_in(1, 'VEC2', "uv")
        shader_info.vertex_in(2, 'VEC4', "color") # Attribute data passed as color
        
        shader_info.vertex_out(vert_out)
        
        # Vertex Shader: 
        # Position is UV coordinates mapped to NDC (-1..1)
        # Z is flattened to 0
        shader_info.vertex_source(
            """
            void main() {
                // Map UV (0..1) to NDC (-1..1)
                vec2 pos = uv * 2.0 - 1.0;
                gl_Position = vec4(pos, 0.0, 1.0);
                v_color = color;
            }
            """
        )
        
        # Fragment Shader: Just output the interpolated color
        shader_info.fragment_out(0, 'VEC4', "FragColor")
        shader_info.fragment_source(
            """
            void main() {
                FragColor = v_color;
            }
            """
        )
        
        shader = gpu.shader.create_from_info(shader_info)
        self._shaders["MESH_ATTR"] = shader
        return shader

    def rasterize_mesh_attribute(self, 
                               mesh: bpy.types.Mesh, 
                               attribute_name: str, 
                               uv_map_name: str = "",
                               width: int = 512, 
                               height: int = 512) -> gpu.types.GPUTexture:
        """
        Rasterize a mesh attribute into a texture using UV unwrap.
        """
        self._ensure_offscreen(width, height)
        
        # 1. Get UV Layer
        if not mesh.loop_triangles:
             mesh.calc_loop_triangles()
             
        if uv_map_name and uv_map_name in mesh.uv_layers:
            uv_layer = mesh.uv_layers[uv_map_name]
        else:
            uv_layer = mesh.uv_layers.active
            
        if not uv_layer:
            print("Rasterizer: No UV map found.")
            return None 

        # 2. Get Attribute
        attr = None
        if attribute_name in mesh.attributes:
            attr = mesh.attributes[attribute_name]
        elif attribute_name in mesh.vertex_colors:
             attr = mesh.vertex_colors[attribute_name]
        
        if not attr:
             # Fallback: Check if it's a special attribute like "position" logic handled by shader?
             # For now return None
             print(f"Rasterizer: Attribute {attribute_name} not found.")
             return None

        # 3. Extract Data
        # We need per-corner data because UVs are per-corner.
        count = len(mesh.loops)
        
        # -- UVs --
        uvs = np.empty(count * 2, dtype=np.float32)
        uv_layer.data.foreach_get("uv", uvs)
        uvs.shape = (count, 2)
        
        # -- Colors --
        # We need to map whatever attribute type to VEC4 for the generic shader.
        colors = np.zeros(count * 4, dtype=np.float32)
        
        # Domain Mapping logic (Simplified)
        if attr.domain == 'CORNER':
            if attr.data_type == 'FLOAT_COLOR':
                attr.data.foreach_get("color", colors)
            elif attr.data_type == 'FLOAT_VECTOR':
                # Vector is 3 floats, we need 4.
                # Numpy trick: read to auxiliary, copy to columns 0,1,2, set alpha 1
                vecs = np.zeros(count * 3, dtype=np.float32)
                attr.data.foreach_get("vector", vecs)
                vecs.shape = (count, 3)
                
                colors_view = colors.reshape((count, 4))
                colors_view[:, :3] = vecs
                colors_view[:, 3] = 1.0
                
        elif attr.domain == 'POINT':
            # Map Point -> Corner
            # We need loop vertex indices
            loop_v_ertex_indices = np.empty(count, dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", loop_v_ertex_indices)
            
            if attr.data_type == 'FLOAT_COLOR':
                point_data = np.zeros(len(mesh.vertices) * 4, dtype=np.float32)
                attr.data.foreach_get("color", point_data)
                point_data.shape = (-1, 4)
                # Map
                colors = point_data[loop_v_ertex_indices].flatten()
                
            elif attr.data_type == 'FLOAT_VECTOR':
                 point_data = np.zeros(len(mesh.vertices) * 3, dtype=np.float32)
                 attr.data.foreach_get("vector", point_data)
                 point_data.shape = (-1, 3)
                 
                 mapped_vecs = point_data[loop_v_ertex_indices]
                 colors_view = colors.reshape((count, 4))
                 colors_view[:, :3] = mapped_vecs
                 colors_view[:, 3] = 1.0

        # Create Batch (Naive: re-create every time)
        # We assume triangle list for now, but loop_triangles are indexed.
        
        # Need indices for loop_triangles
        # loop_triangles.vertices are vertex indices. But our data (uvs, colors) is per LOOP/CORNER.
        # So we need loop indices.
        # loop_triangles.loops contains the 3 loop indices for the triangle.
        
        loop_indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("loops", loop_indices)
        
        # Since uvs and colors are already per-loop arrays, we can use loop_indices directly into them?
        # No, batch_for_shader expects "pos", "uv", etc to be per-vertex of the batch.
        # If we use indices, the attributes must correspond to the indexed elements.
        # Here, our "elements" are Loops (Corners), not Vertices.
        # So we treat each Loop as a unique vertex for rasterization purposes (split vertices).
        # This is correct for UV seams.
        
        # We treat UV/Color arrays as the vertex buffers. 
        # The indices simply point to them.
        
        shader = self.get_mesh_attribute_shader()
        
        # Position is irrelevant? No, shader uses 'uv' to calculate gl_Position. 
        # But shader expects 'position' input? We can bind anything to it or remove it.
        # Let's verify shader input. It asks for 'position' (0). We must provide it or remove it.
        # Actually our shader uses 'uv' for position. But GPUBatch might insist on 'pos'?
        # Let's bind 'uv' to 'position' input slot index if possible?
        # Or just provide dummy positions.
        
        batch = batch_for_shader(shader, 'TRIS', 
                                 {"uv": uvs, "color": colors, "position": uvs}, # Dummy pos
                                 indices=loop_indices)
        
        with self._offscreen.bind():
            # No Depth Test for UV flat map
            gpu.state.depth_test_set('NONE')
            gpu.state.blend_set('NONE') # Overwrite
            
            # Clear?
            # self.clear_color(0,0,0,0) # Missing API?
            # Simply draw a fullscreen quad? Or assume background is black?
            
            batch.draw(shader)
            
        return self._offscreen.texture_color

    # -------------------------------------------------------------------------
    # SCENE CAPTURE (Scene -> Texture via Camera)
    # -------------------------------------------------------------------------

    def get_capture_shader(self, mode="DEPTH"):
        """
        Returns a shader for scene capture (Depth or Normal).
        """
        if mode in self._shaders:
            return self._shaders[mode]
            
        vert_out = gpu.types.GPUStageInterfaceInfo(f"{mode}_interface")
        
        if mode == "NORMAL":
             vert_out.smooth('VEC3', "v_normal")

        shader_info = gpu.types.GPUShaderCreateInfo()
        shader_info.vertex_in(0, 'VEC3', "position")
        
        if mode == "NORMAL":
            shader_info.vertex_in(1, 'VEC3', "normal")
            
        shader_info.push_constant('MAT4', "viewProjectionMatrix")
        shader_info.push_constant('MAT4', "modelMatrix")
        
        shader_info.vertex_out(vert_out)
        
        # Shader Source
        if mode == "DEPTH":
            # Render Z (linearized or raw) to color
            shader_info.vertex_source(
                """
                void main() {
                    gl_Position = viewProjectionMatrix * modelMatrix * vec4(position, 1.0);
                }
                """
            )
            shader_info.fragment_out(0, 'VEC4', "FragColor")
            shader_info.fragment_source(
                """
                void main() {
                    // Simple Linear Depth output (0..1 in view range)
                    // gl_FragCoord.z is non-linear depth [0..1]
                    // We output it directly for now.
                    float d = gl_FragCoord.z;
                    FragColor = vec4(d, d, d, 1.0);
                }
                """
            )
            
        elif mode == "NORMAL":
            shader_info.vertex_source(
                """
                void main() {
                    gl_Position = viewProjectionMatrix * modelMatrix * vec4(position, 1.0);
                    // Transform normal to world space (simplified)
                    // Valid only for uniform scaling. InverseTranspose needed for non-uniform.
                    v_normal = mat3(modelMatrix) * normal;
                }
                """
            )
            shader_info.fragment_out(0, 'VEC4', "FragColor")
            shader_info.fragment_source(
                """
                void main() {
                    vec3 n = normalize(v_normal);
                    // Map -1..1 to 0..1
                    FragColor = vec4(n * 0.5 + 0.5, 1.0);
                }
                """
            )

        shader = gpu.shader.create_from_info(shader_info)
        self._shaders[mode] = shader
        return shader

    def capture_scene(self, 
                      collection: bpy.types.Collection, 
                      camera: bpy.types.Object, 
                      mode: str = "DEPTH",
                      width: int = 512, 
                      height: int = 512) -> gpu.types.GPUTexture:
        """
        Capture a collection from a camera viewpoint.
        """
        self._ensure_offscreen(width, height)
        
        if not camera or camera.type != 'CAMERA':
            print("Rasterizer: Invalid camera.")
            return None
            
        # 1. Calc Matrices
        # Camera Matrix
        view_matrix = camera.matrix_world.inverted()
        # calc_matrix_camera returns projection
        projection_matrix = camera.calc_matrix_camera(
            bpy.context.evaluated_depsgraph_get(), 
            x=width, y=height
        )
        view_proj = projection_matrix @ view_matrix
        
        shader = self.get_capture_shader(mode)
        
        with self._offscreen.bind():
            # Clear
            gpu.state.depth_test_set('LESS_EQUAL')
            gpu.state.depth_mask_set(True)
            gpu.state.blend_set('NONE')
            
            # --- Draw Objects ---
            for obj in collection.objects:
                if obj.type != 'MESH': 
                    continue
                    
                mesh = obj.data
                if not mesh.loop_triangles:
                    mesh.calc_loop_triangles()
                
                # Extract Geometry (Simple extraction)
                # Optimization: Cache logic would go here
                
                verts = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
                mesh.vertices.foreach_get("co", verts)
                verts.shape = (-1, 3)
                
                indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int32)
                mesh.loop_triangles.foreach_get("vertices", indices)
                
                fmt = {"position": verts}
                
                if mode == "NORMAL":
                    norms = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
                    mesh.vertices.foreach_get("normal", norms)
                    norms.shape = (-1, 3)
                    fmt["normal"] = norms
                    
                # We use vertices as batch elements here (rendering 3D mesh)
                batch = batch_for_shader(shader, 'TRIS', fmt, indices=indices)
                
                # Draw
                shader.bind()
                shader.uniform_float("viewProjectionMatrix", view_proj)
                shader.uniform_float("modelMatrix", obj.matrix_world)
                
                batch.draw(shader)
                
        return self._offscreen.texture_color

    def destroy(self):
        self._offscreen = None
