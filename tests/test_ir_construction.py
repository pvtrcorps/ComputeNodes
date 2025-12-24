
import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import MagicMock
mock_bpy = MagicMock()
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

sys.modules['gpu'] = MagicMock() # Mock gpu for runtime import check

from compute_nodes.ir.types import DataType
from compute_nodes.ir.resources import ImageDesc, ResourceAccess, ResourceType
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.graph import Graph, IRBuilder, ValueKind

def test_ir_construction():
    print("Testing IR Construction (Refined)...")
    
    # 1. Init Graph
    graph = Graph("test_kernel")
    builder = IRBuilder(graph)
    
    # 2. Add Resources
    img_in_desc = ImageDesc("img_in", access=ResourceAccess.READ)
    img_out_desc = ImageDesc("img_out", access=ResourceAccess.WRITE)
    
    val_img_in = builder.add_resource(img_in_desc)
    val_img_out = builder.add_resource(img_out_desc)
    
    # Verify linking
    assert val_img_in.kind == ValueKind.ARGUMENT
    assert val_img_in.resource_index is not None
    assert graph.resources[val_img_in.resource_index] == img_in_desc
    
    # Verify Hash Stability (Binding shouldn't affect hash)
    h1 = hash(img_in_desc)
    img_in_desc.binding = 5
    h2 = hash(img_in_desc)
    assert h1 == h2, "Hash changed after binding update!"
    
    # 3. Add Coordinate & Load
    val_coord = builder._new_value(ValueKind.SSA, DataType.IVEC2, name_hint="coord")
    
    # Manual Op creation for image_load
    op_load = builder.add_op(OpCode.IMAGE_LOAD, [val_img_in, val_coord])
    val_pixel = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op_load, name_hint="pixel")
    op_load.add_output(val_pixel)
    
    # Verify Hazard Tracking
    assert op_load.reads_resources() == [val_img_in.resource_index]
    assert op_load.writes_resources() == []
    
    # 4. Math (Add)
    val_doubled = builder.add(val_pixel, val_pixel)
    
    # 5. Image Store
    op_store = builder.add_op(OpCode.IMAGE_STORE, [val_img_out, val_coord, val_doubled])
    
    # Verify Hazard Tracking
    assert op_store.writes_resources() == [val_img_out.resource_index]
    
    # 6. Constants
    val_const = builder.constant(1.0, DataType.FLOAT)
    assert val_const.kind == ValueKind.CONSTANT
    assert val_const.origin.opcode == OpCode.CONSTANT
    assert val_const.origin.attrs['value'] == 1.0

    print("Graph constructed successfully.")
    print(f"Blocks: {len(graph.blocks)}")
    print(f"Resources: {len(graph.resources)}")
    
    for i, op in enumerate(graph.blocks[0].ops):
        print(f"  {i}: {op} -> Writes: {op.writes_resources()}")

if __name__ == "__main__":
    try:
        test_ir_construction()
        print("\nPASS")
    except Exception as e:
        print(f"\nFAIL: {e}")
        import traceback
        traceback.print_exc()
