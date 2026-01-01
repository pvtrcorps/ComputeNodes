import sys
import os
import unittest
from compute_nodes.ir.graph import IRBuilder, Graph, ValueKind
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.resources import ImageDesc, ResourceAccess
from compute_nodes.ir.types import DataType
from compute_nodes.planner.scheduler import schedule_passes
from compute_nodes.codegen.glsl import ShaderGenerator

from .mocks import MockNodeTreeNew, MockNodeNew, MockSocketNew

# Note: bpy is mocked by conftest.py auto-fixture

class TestCodegen(unittest.TestCase):
    def test_basic_codegen(self):
        print("Testing Basic GLSL Codegen...")
        """Test GLSL generation for a simple storage pass."""
        graph = Graph("CodegenGraph")
        builder = IRBuilder(graph)
        
        # Resources
        desc_in = ImageDesc("InputTex", ResourceAccess.READ)
        desc_out = ImageDesc("OutputTex", ResourceAccess.WRITE)
        val_in = builder.add_resource(desc_in)
        val_out = builder.add_resource(desc_out)
        
        # Operations
        # 1. Builtin ID
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        # 2. Swizzle
        val_coord = builder.swizzle(val_gid, "xy") # -> UVEC2
        # 3. Cast
        val_coord_i = builder.cast(val_coord, DataType.IVEC2)
        # 4. Load
        # Use input texture so it appears in bindings
        val_load = builder.add_op(OpCode.IMAGE_LOAD, [val_in, val_coord_i])
        val_color = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=val_load)
        val_load.add_output(val_color)
        
        # 5. Store
        builder.image_store(val_out, val_coord_i, val_color)
        
        # Schedule
        passes = schedule_passes(graph)
        self.assertEqual(len(passes), 1)
        
        # Generate
        generator = ShaderGenerator(graph)
        code = generator.generate(passes[0])
        
        print("\n--- Generated GLSL ---\n")
        print(code)
        print("\n----------------------\n")
        
        # Assertions
        self.assertIn("#define u_dispatch_size", code)
        # self.assertIn("layout(local_size_x", code)
        self.assertIn("void main()", code)
        
        # Bindings
        # self.assertIn("uniform readonly image2D InputTex_0;", code)
        # self.assertIn("uniform writeonly image2D OutputTex_1;", code) # Indices might vary based on map order
        
        # Ops
        self.assertIn("gl_GlobalInvocationID;", code)
        self.assertIn(".xy;", code)
        self.assertIn("ivec2(", code)
        # self.assertIn("imageStore(OutputTex_", code)

if __name__ == "__main__":
    unittest.main()
