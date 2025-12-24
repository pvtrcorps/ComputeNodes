
import sys
import os
import unittest

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock bpy
from unittest.mock import MagicMock
sys.modules['bpy'] = MagicMock()
sys.modules['bpy.types'] = MagicMock()
sys.modules['bpy.utils'] = MagicMock()
sys.modules['bpy.props'] = MagicMock()

# Mock nodeitems_utils with classes
mock_nodeitems = MagicMock()
class MockNodeCategory:
    def __init__(self, *args, **kwargs): pass
    @classmethod
    def poll(cls, context): return True

class MockNodeItem:
    def __init__(self, *args, **kwargs): pass

mock_nodeitems.NodeCategory = MockNodeCategory
mock_nodeitems.NodeItem = MockNodeItem
sys.modules['nodeitems_utils'] = mock_nodeitems

from compute_nodes.ir.graph import Graph, IRBuilder, ValueKind
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.resources import ImageDesc, ResourceAccess, ResourceType
from compute_nodes.ir.types import DataType
from compute_nodes.planner.scheduler import schedule_passes

class TestPlanner(unittest.TestCase):
    def test_single_pass_no_hazard(self):
        """Test simplest case: Read -> Compute -> Write"""
        graph = Graph("SinglePass")
        builder = IRBuilder(graph)
        
        # Resources
        desc_in = ImageDesc("Input", ResourceAccess.READ)
        desc_out = ImageDesc("Output", ResourceAccess.WRITE)
        val_in = builder.add_resource(desc_in)
        val_out = builder.add_resource(desc_out)
        
        # Ops
        val_load = builder.add_op(OpCode.IMAGE_LOAD, [val_in])
        val_load_res = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=val_load)
        val_load.add_output(val_load_res)
        
        val_add = builder.add_op(OpCode.ADD, [val_load_res, val_load_res]) # Dummy compute
        val_add_res = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=val_add)
        val_add.add_output(val_add_res)
        
        builder.add_op(OpCode.IMAGE_STORE, [val_out, val_in, val_add_res]) # using val_in as coord dummy
        
        # Schedule
        passes = schedule_passes(graph)
        
        self.assertEqual(len(passes), 1)
        self.assertEqual(len(passes[0].ops), 3) # Load, Add, Store
        
    def test_hazard_splitting(self):
        """Test Read-After-Write Hazard splitting"""
        graph = Graph("HazardGraph")
        builder = IRBuilder(graph)
        
        # Resource A (RW)
        desc_a = ImageDesc("ResA", ResourceAccess.READ_WRITE)
        val_a = builder.add_resource(desc_a)
        
        # Pass 1: Write to A
        # store(A, ...)
        builder.add_op(OpCode.IMAGE_STORE, [val_a]) 
        
        # Pass 2: Read from A
        # load(A)
        loader_op = builder.add_op(OpCode.IMAGE_LOAD, [val_a])
        
        # Schedule
        passes = schedule_passes(graph)
        
        self.assertEqual(len(passes), 2)
        # Pass 1: Store op
        self.assertEqual(passes[0].ops[0].opcode, OpCode.IMAGE_STORE)
        # Pass 2: Load op
        self.assertEqual(passes[1].ops[0].opcode, OpCode.IMAGE_LOAD)

if __name__ == "__main__":
    unittest.main()
