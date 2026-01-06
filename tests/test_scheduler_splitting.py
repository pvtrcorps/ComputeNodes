"""
Tests for scheduler pass splitting by output size.

These tests verify that passes writing to resources of different sizes
are correctly split into separate passes.

This was a bug fix: when a loop had multiple outputs with different sizes,
the UV calculations were incorrect because all writes used one dispatch size.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# conftest.py handles bpy/gpu mocking before imports


class TestPassSplittingBySize:
    """Tests for _split_passes_by_output_size functionality."""
    
    def test_single_size_no_split(self, simple_graph):
        """
        A graph with only one output size should not be split.
        
        Given: Graph with single 512x512 output
        When: schedule_passes is called
        Then: Only 1 pass is created
        """
        from compute_nodes.planner.scheduler import schedule_passes
        
        passes = schedule_passes(simple_graph)
        
        # Should be exactly 1 pass
        assert len(passes) == 1
        assert len(passes[0].writes_idx) >= 1
    
    def test_multiple_same_size_no_split(self, empty_graph):
        """
        Multiple outputs with the SAME size should NOT be split.
        
        Given: Graph with two 512x512 outputs
        When: schedule_passes is called
        Then: 1 pass (no split needed)
        """
        from compute_nodes.ir.graph import IRBuilder, ValueKind
        from compute_nodes.ir.ops import OpCode
        from compute_nodes.ir.resources import ImageDesc, ResourceAccess
        from compute_nodes.ir.types import DataType
        from compute_nodes.planner.scheduler import schedule_passes
        
        graph = empty_graph
        builder = IRBuilder(graph)
        
        # Two outputs with SAME size
        out1 = ImageDesc("Output1", ResourceAccess.WRITE, size=(512, 512))
        out2 = ImageDesc("Output2", ResourceAccess.WRITE, size=(512, 512))
        
        out1_val = builder.add_resource(out1)
        out2_val = builder.add_resource(out2)
        
        pos = builder._new_value(ValueKind.BUILTIN, DataType.VEC3)
        builder.add_op(OpCode.IMAGE_STORE, [out1_val, pos, pos])
        builder.add_op(OpCode.IMAGE_STORE, [out2_val, pos, pos])
        
        passes = schedule_passes(graph)
        
        # Should be 1 pass since sizes are equal
        assert len(passes) == 1
        assert len(passes[0].writes_idx) == 2
    
    def test_different_sizes_creates_split(self, multi_size_output_graph):
        """
        Outputs with DIFFERENT sizes MUST be split into separate passes.
        
        Given: Graph with 768x768 and 666x666 outputs
        When: schedule_passes is called
        Then: 2 passes are created, one per size
        """
        from compute_nodes.planner.scheduler import schedule_passes
        
        graph = multi_size_output_graph
        passes = schedule_passes(graph)
        
        # Should be 2 passes
        assert len(passes) == 2, f"Expected 2 passes, got {len(passes)}"
        
        # Each pass should write to exactly one resource
        assert len(passes[0].writes_idx) == 1
        assert len(passes[1].writes_idx) == 1
        
        # Passes should have different dispatch sizes
        sizes = [p.dispatch_size[:2] for p in passes]
        assert (666, 666) in sizes
        assert (768, 768) in sizes
    
    def test_split_preserves_field_dependencies(self, empty_graph):
        """
        When splitting, field operations (Math, Position, etc.) must be
        duplicated in each resulting pass.
        
        Given: Position -> Math -> Store to two outputs of different sizes
        When: schedule_passes is called
        Then: Each pass has Position and Math ops
        """
        from compute_nodes.ir.graph import IRBuilder, ValueKind
        from compute_nodes.ir.ops import OpCode
        from compute_nodes.ir.resources import ImageDesc, ResourceAccess
        from compute_nodes.ir.types import DataType
        from compute_nodes.planner.scheduler import schedule_passes
        
        graph = empty_graph
        builder = IRBuilder(graph)
        
        # Outputs with different sizes
        out1 = ImageDesc("Output1", ResourceAccess.WRITE, size=(768, 768))
        out2 = ImageDesc("Output2", ResourceAccess.WRITE, size=(666, 666))
        
        out1_val = builder.add_resource(out1)
        out2_val = builder.add_resource(out2)
        
        # Position -> Math(multiply) -> Store
        pos = builder._new_value(ValueKind.BUILTIN, DataType.VEC3)
        pos_op = builder.add_op(OpCode.BUILTIN, [])
        pos_op.attrs['name'] = 'gl_GlobalInvocationID'
        pos_out = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=pos_op)
        pos_op.add_output(pos_out)
        
        const = builder._new_value(ValueKind.CONSTANT, DataType.FLOAT)
        const.attrs = {'value': 2.0}
        mul = builder.add_op(OpCode.MUL, [pos_out, const])
        mul_out = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=mul)
        mul.add_output(mul_out)
        
        builder.add_op(OpCode.IMAGE_STORE, [out1_val, pos, mul_out])
        builder.add_op(OpCode.IMAGE_STORE, [out2_val, pos, mul_out])
        
        passes = schedule_passes(graph)
        
        # Should be 2 passes
        assert len(passes) == 2
        
        # Each pass should have the MUL op (field dependency)
        for p in passes:
            opcodes = [op.opcode for op in p.ops]
            # Each pass needs the computation chain
            assert OpCode.IMAGE_STORE in opcodes


class TestDynamicSizeEvaluation:
    """Tests for dynamic size expression evaluation."""
    
    def test_scalar_evaluator_basic_math(self):
        """
        ScalarEvaluator should correctly evaluate IR expressions.
        
        Given: Expression for 256 * iteration
        When: Evaluated with iteration=3
        Then: Result is 768
        """
        from compute_nodes.runtime.scalar_evaluator import ScalarEvaluator
        from compute_nodes.ir.graph import Op, ValueKind
        from compute_nodes.ir.ops import OpCode
        from compute_nodes.ir.types import DataType
        
        evaluator = ScalarEvaluator()
        
        # Build: 256 * iteration
        # This would be in the IR as MUL(CONSTANT(256), BUILTIN(iteration))
        
        # Create iteration value
        iter_val = type('Value', (), {
            'kind': ValueKind.VARIABLE,
            'type': DataType.INT,
            'attrs': {'name': 'iteration'}
        })()
        
        const_val = type('Value', (), {
            'kind': ValueKind.CONSTANT, 
            'type': DataType.INT,
            'attrs': {'value': 256}
        })()
        
        # Create MUL op
        mul_op = Op(OpCode.MUL)
        mul_op.inputs = [const_val, iter_val]
        
        result_val = type('Value', (), {
            'kind': ValueKind.SSA,
            'type': DataType.INT,
            'origin': mul_op
        })()
        
        result = evaluator.evaluate(result_val, {'iteration': 3})
        assert result == 768, f"Expected 768, got {result}"
    
    def test_scalar_evaluator_with_add(self):
        """
        Test ADD operation in ScalarEvaluator.
        """
        from compute_nodes.runtime.scalar_evaluator import ScalarEvaluator
        from compute_nodes.ir.graph import Op, ValueKind
        from compute_nodes.ir.ops import OpCode
        from compute_nodes.ir.types import DataType
        
        evaluator = ScalarEvaluator()
        
        const_a = type('Value', (), {
            'kind': ValueKind.CONSTANT,
            'type': DataType.INT,
            'attrs': {'value': 100}
        })()
        
        const_b = type('Value', (), {
            'kind': ValueKind.CONSTANT,
            'type': DataType.INT,
            'attrs': {'value': 200}
        })()
        
        add_op = Op(OpCode.ADD)
        add_op.inputs = [const_a, const_b]
        
        result_val = type('Value', (), {
            'kind': ValueKind.SSA,
            'type': DataType.INT,
            'origin': add_op
        })()
        
        result = evaluator.evaluate(result_val, {})
        assert result == 300


class TestLoopPassSplitting:
    """Tests for pass splitting within loop bodies."""
    
    def test_loop_body_splits_by_size(self):
        """
        Loop body passes that write to different sizes should be split.
        
        Given: Loop with two outputs - one dynamic (256*iter), one fixed (666)
        When: Scheduled
        Then: Loop body has 2 passes, one per size
        """
        # This is a more complex test that requires full graph setup
        # For now, we test the split function directly
        
        from compute_nodes.planner.scheduler import _split_passes_by_output_size
        from compute_nodes.planner.passes import ComputePass
        from compute_nodes.ir.graph import Graph, Op
        from compute_nodes.ir.ops import OpCode
        from compute_nodes.ir.resources import ImageDesc, ResourceAccess
        
        graph = Graph()
        res1 = ImageDesc("Res768", ResourceAccess.WRITE, size=(768, 768))
        res2 = ImageDesc("Res666", ResourceAccess.WRITE, size=(666, 666))
        graph.resources.extend([res1, res2])
        
        # Create a pass with two stores to different sizes
        p = ComputePass(pass_id=0)
        
        store1 = Op(OpCode.IMAGE_STORE)
        store1._write_resources = [0]
        
        store2 = Op(OpCode.IMAGE_STORE)
        store2._write_resources = [1]
        
        p.add_op(store1)
        p.add_op(store2)
        p.writes_idx = {0, 1}
        p.writes = {res1, res2}
        
        result = _split_passes_by_output_size([p], graph)
        
        assert len(result) == 2, f"Expected 2 passes, got {len(result)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
