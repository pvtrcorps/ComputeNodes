
import unittest
import bpy
from compute_nodes.graph_extract import extract_graph
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.types import DataType

# Note: bpy is mocked by conftest.py auto-fixture

from .mocks import MockSocketNew, MockLinkNew, MockNodeNew, MockNodeTreeNew

class TestGraphExtraction(unittest.TestCase):
    def test_extraction(self):
        print("Testing Graph Extraction...")
        
        # Construct a Mock NodeTree
        # Image Input -> Math(ADD) -> Output
        
        tree = MockNodeTreeNew("TestTree")
        
        # 1. Image Input Node (Read)
        node_in = MockNodeNew('ComputeNodeImageInput', "Image In")
        sock_img_out = MockSocketNew("Image")
        node_in.outputs.append(sock_img_out)
        
        mock_image = self._create_mock_image("MyTexture")
        node_in.image = mock_image
        
        tree.nodes.append(node_in)
        
        # 2. Math Node
        node_math = MockNodeNew('ComputeNodeMath', "Math Add")
        sock_a = MockSocketNew("Value", default_value=0.5)
        sock_b = MockSocketNew("Value", default_value=0.5)
        sock_res = MockSocketNew("Value")
        
        # Inputs need to be indexed by name (or index)
        # Usually Math inputs are [0], [1].
        # But if handlers use names, we need names.
        # handle_math uses indices: node.inputs[0], node.inputs[1].
        # So appending order matters.
        node_math.inputs.append(sock_a)
        node_math.inputs.append(sock_b)
        node_math.outputs.append(sock_res)
        node_math.operation = 'ADD'
        
        tree.nodes.append(node_math)
        
        # 3. Output Node (This writes the result)
        node_out = MockNodeNew('ComputeNodeOutputImage', "Output")
        sock_grid_in = MockSocketNew("Grid", type='GRID')
        node_out.inputs.append(sock_grid_in)
        
        tree.nodes.append(node_out)
        
        # Capture Node (Materializes the Loop Result)
        node_capture = MockNodeNew('ComputeNodeCapture', "Capture")
        # handle_capture uses node.inputs['Field']
        sock_field_in = MockSocketNew("Field") 
        sock_width = MockSocketNew("Width", default_value=512)
        sock_height = MockSocketNew("Height", default_value=512)
        
        # Important: Add 'Field' socket so it can be found by name
        node_capture.inputs.append(sock_field_in)
        node_capture.inputs.append(sock_width)
        node_capture.inputs.append(sock_height)
        
        sock_grid_out = MockSocketNew("Grid", type='GRID')
        node_capture.outputs.append(sock_grid_out)
        tree.nodes.append(node_capture)
        
        # Links
        # Link: Image In (Grid) -> Math Input A (Value/Field)
        link1 = MockLinkNew(sock_img_out, node_in, sock_a, node_math)
        sock_img_out.is_linked = True; sock_img_out.links = [link1]
        sock_a.is_linked = True; sock_a.links = [link1]
        
        # Link: Math -> Capture
        link2 = MockLinkNew(sock_res, node_math, sock_field_in, node_capture)
        sock_res.is_linked = True; sock_res.links = [link2]
        sock_field_in.is_linked = True; sock_field_in.links = [link2]

        # Link: Capture -> Output
        link3 = MockLinkNew(sock_grid_out, node_capture, sock_grid_in, node_out)
        sock_grid_out.is_linked = True; sock_grid_out.links = [link3]
        sock_grid_in.is_linked = True; sock_grid_in.links = [link3]
        
        # Run Extraction
        graph = extract_graph(tree)
        
        # Assertions
        print(f"Graph Generated: {len(graph.blocks[0].ops)} ops")
        ops = graph.blocks[0].ops
        
        # Expected Ops:
        # 1. CONSTANT (from Math input B)
        # 2. IMAGE_INPUT (from Image Input) -> produces Handle
        # 3. SAMPLE (Auto-injected because Image(Grid) -> Math(Field))
        # 4. ADD (Math)
        # 5. CAPTURE (Capture node)
        # 6. IMAGE_STORE (Output Image - implicit or explicit if we map it)
        # Actually ComputeNodeOutputImage handler generates nothing? 
        # Check output.py handler.
        # But Capture generates STORE if it's the end of field chain.
        # Wait, Capture writes to a Grid. 
        # Output Image reads that Grid.
        # IR Graph usually ends at Capture (Store to Temp) or Output (Store to Final).
        # ComputeNodeOutputImage handler (handle_output_image) usually creates a COPY pass or simply marks the resource.
        
        # Let's inspect generated ops
        input_ops = [op for op in ops if op.opcode == OpCode.CONSTANT] # Math B
        math_ops = [op for op in ops if op.opcode == OpCode.ADD]
        sample_ops = [op for op in ops if op.opcode == OpCode.SAMPLE]
        capture_ops = [op for op in ops if op.opcode == OpCode.IMAGE_STORE] # Capture emits IMAGE_STORE
        # Note: Capture node usually compiles to a STORE op in the extraction? 
        # Or does it produce a WRITE to a texture?
        
        # Handle Output Image handler usually might NOT generate an Op if it just defines the output resource?
        # Let's trust inspection.
        
        self.assertEqual(len(math_ops), 1, "Missing ADD op")
        self.assertGreaterEqual(len(sample_ops), 1, "Missing Auto-SAMPLE op")
        # self.assertEqual(len(capture_ops), 1, "Missing Capture op") # Depends on implementation of handle_capture
        self.assertGreaterEqual(len(input_ops), 1, "Missing Constant inputs") # Only Math B is constant
        
        # Verify the sequence of operations
        # We expect: IMAGE_INPUT -> SAMPLE -> ADD -> CAPTURE -> IMAGE_STORE (or similar for output)
        
        # Find the ADD op
        add_op = math_ops[0]
        
        # Check inputs directly or through CAST
        sample_op_input = []
        for inp in add_op.inputs:
            if inp.origin:
                if inp.origin.opcode == OpCode.SAMPLE:
                    sample_op_input.append(inp)
                elif inp.origin.opcode == OpCode.CAST:
                    # Trace through CAST
                    cast_inp = inp.origin.inputs[0]
                    if cast_inp.origin and cast_inp.origin.opcode == OpCode.SAMPLE:
                        sample_op_input.append(cast_inp)
                        
        self.assertEqual(len(sample_op_input), 1, "ADD op should have one input from SAMPLE (possibly via CAST)")
        
        # The other input to ADD should be a CONSTANT
        constant_op_input = [inp for inp in add_op.inputs if inp.origin and inp.origin.opcode == OpCode.CONSTANT]
        self.assertEqual(len(constant_op_input), 1, "ADD op should have one input from CONSTANT")
        
        # The output of ADD should go to CAPTURE (possibly via CAST)
        capture_op_from_add = []
        for op in ops:
            if op.opcode == OpCode.IMAGE_STORE:
                for inp in op.inputs:
                    if inp.origin:
                        if inp.origin == add_op.outputs[0]:
                            capture_op_from_add.append(op)
                        elif inp.origin.opcode == OpCode.CAST:
                            if inp.origin.inputs[0].origin == add_op:
                                capture_op_from_add.append(op)

        self.assertGreaterEqual(len(capture_op_from_add), 1, "CAPTURE op (IMAGE_STORE) should take input from ADD (possibly via CAST)")
        
        # The output of CAPTURE should go to IMAGE_STORE (or similar final output)
        # This part is tricky as the final output might be handled differently.
        # For now, let's just check for the presence of CAPTURE and SAMPLE.
        self.assertGreaterEqual(len(capture_ops), 1, "Missing CAPTURE op")
        
        print("Ops sequence:")
        for i, op in enumerate(ops):
            print(f"  {i}: {op}")
            
        print("PASS")

    def _create_mock_image(self, name):
        # Helper to create a more robust mock image if needed
        # Since we use bpy.types.Image in real code, but here heavily mocked inputs
        # We rely on MockNode structure.
        # But 'image' attribute on node is expected to be an object with .name
        class Img:
            pass
        img = Img()
        img.name = name
        img.is_float = True # Assume float for testing
        return img

if __name__ == "__main__":
    unittest.main()

