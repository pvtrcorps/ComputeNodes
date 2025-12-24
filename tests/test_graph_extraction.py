
import sys
import os
from unittest.mock import MagicMock

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock bpy structure complete
mock_bpy = MagicMock()
mock_bpy.types = MagicMock()
mock_bpy.props = MagicMock()
mock_bpy.utils = MagicMock()

sys.modules['bpy'] = mock_bpy
sys.modules['bpy.types'] = mock_bpy.types
sys.modules['bpy.props'] = mock_bpy.props
sys.modules['bpy.utils'] = mock_bpy.utils

# Mock nodeitems_utils
mock_nodeitems = MagicMock()
sys.modules['nodeitems_utils'] = mock_nodeitems

class MockNodeCategory:
    def __init__(self, *args, **kwargs): pass
    @classmethod
    def poll(cls, context): return True

class MockNodeItem:
    def __init__(self, *args, **kwargs): pass

mock_nodeitems.NodeCategory = MockNodeCategory
mock_nodeitems.NodeItem = MockNodeItem

import bpy
# Setup specific types if needed for inheritance (NodeTree, Node, NodeSocket)
# Since we are mocking, inheritance from MagicMock usually works, 
# but we might need to be careful if code checks issubclass.
mock_bpy.types.NodeTree = object
mock_bpy.types.Node = object
mock_bpy.types.NodeSocket = object

from compute_nodes.graph_extract import extract_graph
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.types import DataType

class MockSocket:
    def __init__(self, name="Socket", default_value=0.0):
        self.name = name
        self.default_value = default_value
        self.is_linked = False
        self.links = []
        self.node = None # Parent node

    def as_pointer(self):
        return id(self)

class MockLink:
    def __init__(self, from_socket, from_node, to_socket, to_node):
        self.from_socket = from_socket
        self.from_node = from_node
        self.to_socket = to_socket
        self.to_node = to_node

class MockNode:
    def __init__(self, bl_idname, name="Node"):
        self.bl_idname = bl_idname
        self.name = name
        self.inputs = []
        self.outputs = []
        self.operation = 'ADD' # For Math
        self.image = None # For Image Input

class MockNodeTree:
    def __init__(self, name="Tree"):
        self.name = name
        self.nodes = []

def test_extraction():
    print("Testing Graph Extraction...")
    
    # Construct a Mock NodeTree
    # Image Input -> Math(ADD) -> Output
    
    tree = MockNodeTree("TestTree")
    
    # 1. Image Input Node (Read)
    node_in = MockNode('ComputeNodeImageInput', "Image In")
    sock_img_out = MockSocket("Image")
    node_in.outputs.append(sock_img_out)
    
    mock_image = MagicMock()
    mock_image.name = "MyTexture"
    node_in.image = mock_image
    
    tree.nodes.append(node_in)
    
    # 1b. Image Write Node (Target)
    node_write = MockNode('ComputeNodeImageWrite', "Image Write")
    sock_write_out = MockSocket("Image")
    node_write.outputs.append(sock_write_out)
    node_write.image = mock_image # Same image or different
    tree.nodes.append(node_write)
    
    # 2. Math Node
    node_math = MockNode('ComputeNodeMath', "Math Add")
    sock_a = MockSocket("Value", default_value=0.5)
    sock_b = MockSocket("Value", default_value=0.5)
    sock_res = MockSocket("Value")
    node_math.inputs = [sock_a, sock_b]
    node_math.outputs = [sock_res]
    node_math.operation = 'ADD'
    
    tree.nodes.append(node_math)
    
    # 3. Output Node
    node_out = MockNode('ComputeNodeOutput', "Output")
    sock_target = MockSocket("Target Image")
    sock_data = MockSocket("Data")
    node_out.inputs = [sock_target, sock_data]
    
    tree.nodes.append(node_out)
    
    # Links
    # node_write.Image -> node_out.Target Image
    link1 = MockLink(sock_write_out, node_write, sock_target, node_out)
    sock_target.is_linked = True
    sock_target.links = [link1]
    
    # node_math.Value -> node_out.Data
    # Let's say we adding constant + constant in Math
    # Inputs of math are NOT linked, so they use default_value.
    
    link2 = MockLink(sock_res, node_math, sock_data, node_out)
    sock_data.is_linked = True
    sock_data.links = [link2]
    
    # Run Extraction
    graph = extract_graph(tree)
    
    # Assertions
    print(f"Graph Generated: {len(graph.blocks[0].ops)} ops")
    ops = graph.blocks[0].ops
    
    # Expected Ops:
    # 1. CONSTANT (from math input A - defaults)
    # 2. CONSTANT (from math input B - defaults)
    # 3. ADD (Math)
    # 4. BUILTIN (GlobalInvocationID) - injected by extractor
    # 5. SWIZZLE (xy)
    # 6. CAST (UVEC2 -> IVEC2)
    # 7. IMAGE_STORE (Output)
    
    input_ops = [op for op in ops if op.opcode == OpCode.CONSTANT]
    math_ops = [op for op in ops if op.opcode == OpCode.ADD]
    cast_ops = [op for op in ops if op.opcode == OpCode.CAST] # CAST Check
    store_ops = [op for op in ops if op.opcode == OpCode.IMAGE_STORE]
    
    assert len(math_ops) == 1, "Missing ADD op"
    assert len(store_ops) == 1, "Missing IMAGE_STORE op"
    assert len(cast_ops) == 1, "Missing CAST op"
    assert len(input_ops) >= 2, "Missing Constant inputs"
    
    # Verify CAST sequence: SWIZZLE -> CAST -> STORE
    # Store should use cast output
    store_op = store_ops[0]
    coord_input = store_op.inputs[1] # 2nd arg is coord
    assert coord_input.origin.opcode == OpCode.CAST, "Store coord must come from CAST"
    
    # Cast should come from Swizzle
    cast_op = coord_input.origin
    cast_input = cast_op.inputs[0]
    assert cast_input.origin.opcode == OpCode.SWIZZLE, "CAST must come from SWIZZLE"
    
    print("Ops sequence:")
    for i, op in enumerate(ops):
        print(f"  {i}: {op}")
        
    print("PASS")

if __name__ == "__main__":
    test_extraction()
