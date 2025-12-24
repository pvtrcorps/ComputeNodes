import unittest
from unittest.mock import MagicMock, patch
import sys
import types

# 1. Mock bpy and gpu BEFORE importing addon modules
# 1. Mock bpy and gpu BEFORE importing addon modules
mock_bpy = MagicMock()
mock_gpu = MagicMock()

# Essential: Mock submodules directly in sys.modules so "from bpy.types import X" works
sys.modules['bpy'] = mock_bpy
sys.modules['bpy.types'] = mock_bpy.types
sys.modules['bpy.props'] = mock_bpy.props
sys.modules['bpy.utils'] = mock_bpy.utils
# Mock nodeitems_utils classes to support inheritance
class MockNodeCategory:
    def __init__(self, id, label, items=None):
        self.id = id
        self.label = label
        self.items = items or []
    def poll(self, context):
        return True

class MockNodeItem:
    def __init__(self, nodetype):
        self.nodetype = nodetype

mock_nodeitems_utils = MagicMock()
mock_nodeitems_utils.NodeCategory = MockNodeCategory
mock_nodeitems_utils.NodeItem = MockNodeItem
sys.modules['nodeitems_utils'] = mock_nodeitems_utils

sys.modules['gpu'] = mock_gpu
sys.modules['gpu.types'] = mock_gpu.types
sys.modules['gpu.shader'] = mock_gpu.shader
sys.modules['gpu.compute'] = mock_gpu.compute
sys.modules['gpu.texture'] = mock_gpu.texture

# Setup gpu.types class mocks (used as base classes or constructors)
mock_gpu.types.GPUShader = MagicMock()
mock_gpu.types.GPUTexture = MagicMock()
mock_gpu.types.GPUShaderCreateInfo = MagicMock()

# Setup gpu.shader and gpu.compute function mocks
mock_shader_instance = MagicMock()
mock_gpu.shader.create_from_info = MagicMock(return_value=mock_shader_instance)
mock_gpu.compute.dispatch = MagicMock()
mock_gpu.texture.from_image = MagicMock(return_value=MagicMock(name="SharedGPUTexture"))
mock_bpy.data.images.get.return_value = None

# Import runtime modules
try:
    from compute_nodes.runtime.textures import TextureManager
    from compute_nodes.runtime.shaders import ShaderManager
    from compute_nodes.runtime.executor import ComputeExecutor
    from compute_nodes.ir.resources import ImageDesc
    from compute_nodes.planner.passes import ComputePass
    from compute_nodes.ir.graph import Graph
except ImportError:
    # Fallback for running directly where package might not be resolved
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from compute_nodes.runtime.textures import TextureManager
    from compute_nodes.runtime.shaders import ShaderManager
    from compute_nodes.runtime.executor import ComputeExecutor
    from compute_nodes.ir.resources import ImageDesc
    from compute_nodes.planner.passes import ComputePass
    from compute_nodes.ir.graph import Graph

class TestRuntime(unittest.TestCase):
    def setUp(self):
        self.tex_mgr = TextureManager()
        self.shader_mgr = ShaderManager()
        self.executor = ComputeExecutor(self.tex_mgr, self.shader_mgr)
        
        # Reset mocks
        mock_gpu.shader.create_from_info.reset_mock()
        mock_gpu.compute.dispatch.reset_mock()
        mock_gpu.types.GPUTexture.reset_mock()
        self.tex_mgr._internal_textures.clear()
        self.tex_mgr._input_textures.clear()
        self.shader_mgr._shader_cache.clear()

    def test_texture_manager_input(self):
        mock_image = MagicMock()
        mock_image.name = "TestInput"
        
        tex = self.tex_mgr.get_texture_from_image(mock_image)
        
        mock_gpu.texture.from_image.assert_called_with(mock_image)
        self.assertIsNotNone(tex)

    def test_texture_manager_internal(self):
        desc = ImageDesc(name="Internal", format="RGBA32F", size=(256, 256))
        
        tex = self.tex_mgr.ensure_internal_texture("Internal", desc)
        
        # Should create a new texture via GPUTexture constructor (mocked)
        self.assertTrue(mock_gpu.types.GPUTexture.called)
        args, kwargs = mock_gpu.types.GPUTexture.call_args
        self.assertEqual(args[0], (256, 256))
        self.assertEqual(kwargs['format'], 'RGBA32F')

    def test_shader_manager_cache(self):
        src = "void main() {}"
        
        # First call
        s1 = self.shader_mgr.get_shader(src)
        self.assertEqual(mock_gpu.shader.create_from_info.call_count, 1)
        
        # Second call (should cache)
        s2 = self.shader_mgr.get_shader(src)
        self.assertEqual(mock_gpu.shader.create_from_info.call_count, 1)
        self.assertEqual(s1, s2)

    def test_executor_flow(self):
        # Setup Graph and Pass
        graph = Graph()
        # Add one image resource
        desc = ImageDesc(name="Result", format="RGBA32F", size=(512, 512))
        graph.resources.append(desc)
        
        # Setup Pass
        # Pass writes to resource 0
        p = ComputePass(pass_id=0)
        p.source = "void main() { ... }"
        p.writes_idx.add(0)
        
        # Run
        passes = [p]
        self.executor.execute_graph(graph, passes)
        
        # Verification
        # 1. Shader compiled
        mock_gpu.shader.create_from_info.assert_called()
        
        # 2. Texture created (since no blender image with that name in mock)
        mock_gpu.types.GPUTexture.assert_called()
        
        # 3. Shader bound
        mock_shader_instance.bind.assert_called()
        
        # 4. Image bound to shader
        # Expect: shader.image("Image_0", texture)
        mock_shader_instance.image.assert_called()
        call_args = mock_shader_instance.image.call_args
        self.assertEqual(call_args[0][0], "Image_0")
        
        # 5. Dispatch
        # Default 512x512 with 8x8 group size -> 64x64 groups
        mock_gpu.compute.dispatch.assert_called_with(mock_shader_instance, 64, 64, 1)

if __name__ == '__main__':
    unittest.main()
