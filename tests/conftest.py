"""
Pytest configuration and shared fixtures for Compute Nodes tests.

This file provides:
1. Automatic bpy/gpu mocking before any imports
2. Shared fixtures for graphs, passes, etc.
3. Helper functions for common test patterns

Usage:
    pytest tests/ -v
"""

import pytest
import sys
from unittest.mock import MagicMock


# =============================================================================
# BPY/GPU MOCKING (must happen before any compute_nodes imports)
# =============================================================================

def _setup_blender_mocks():
    """Setup mock modules for bpy and gpu."""
    mock_bpy = MagicMock()
    mock_gpu = MagicMock()
    
    # bpy submodules
    sys.modules['bpy'] = mock_bpy
    sys.modules['bpy.types'] = mock_bpy.types
    sys.modules['bpy.props'] = mock_bpy.props
    sys.modules['bpy.utils'] = mock_bpy.utils
    sys.modules['bpy.app'] = mock_bpy.app
    mock_bpy.app.version = (4, 0, 0)
    
    # nodeitems_utils
    class MockNodeCategory:
        def __init__(self, id, label, items=None):
            self.id = id
            self.label = label
            self.items = items or []
        @classmethod
        def poll(cls, context):
            return True
    
    class MockNodeItem:
        def __init__(self, nodetype):
            self.nodetype = nodetype
    
    mock_nodeitems = MagicMock()
    mock_nodeitems.NodeCategory = MockNodeCategory
    mock_nodeitems.NodeItem = MockNodeItem
    sys.modules['nodeitems_utils'] = mock_nodeitems
    
    # gpu submodules
    sys.modules['gpu'] = mock_gpu
    sys.modules['gpu.types'] = mock_gpu.types
    sys.modules['gpu.shader'] = mock_gpu.shader
    sys.modules['gpu.compute'] = mock_gpu.compute
    sys.modules['gpu.texture'] = mock_gpu.texture
    
    # gpu.types mocks
    mock_gpu.types.GPUShader = MagicMock()
    mock_gpu.types.GPUTexture = MagicMock()
    mock_gpu.types.GPUShaderCreateInfo = MagicMock()
    
    # gpu function mocks
    mock_shader_instance = MagicMock()
    mock_gpu.shader.create_from_info = MagicMock(return_value=mock_shader_instance)
    mock_gpu.compute.dispatch = MagicMock()
    mock_gpu.texture.from_image = MagicMock(return_value=MagicMock(name="SharedGPUTexture"))
    
    return mock_bpy, mock_gpu, mock_shader_instance


# Setup mocks at module load time
_mock_bpy, _mock_gpu, _mock_shader = _setup_blender_mocks()


# =============================================================================
# PYTEST FIXTURES
# =============================================================================

@pytest.fixture
def mock_bpy():
    """Provides access to the bpy mock for test customization."""
    return _mock_bpy


@pytest.fixture
def mock_gpu():
    """Provides access to the gpu mock for test customization."""
    return _mock_gpu


@pytest.fixture
def mock_shader():
    """Provides access to the mock shader instance."""
    return _mock_shader


@pytest.fixture
def empty_graph():
    """
    Creates an empty Graph for testing.
    
    Example:
        def test_something(empty_graph):
            empty_graph.resources.append(...)
    """
    from compute_nodes.ir.graph import Graph
    return Graph(name="TestGraph")


@pytest.fixture
def simple_graph():
    """
    Creates a simple graph with Position -> Capture -> Output.
    
    Resources:
        0: Output (WRITE, 512x512)
    """
    from compute_nodes.ir.graph import Graph, IRBuilder, ValueKind
    from compute_nodes.ir.ops import OpCode
    from compute_nodes.ir.resources import ImageDesc, ResourceAccess
    from compute_nodes.ir.types import DataType
    
    graph = Graph(name="SimpleGraph")
    builder = IRBuilder(graph)
    
    # Output resource
    output_desc = ImageDesc(
        name="Output",
        access=ResourceAccess.WRITE,
        size=(512, 512),
        format='RGBA32F'
    )
    output_val = builder.add_resource(output_desc)
    
    # Position builtin
    pos_val = builder._new_value(ValueKind.BUILTIN, DataType.VEC3)
    
    # Store to output
    builder.add_op(OpCode.IMAGE_STORE, [output_val, pos_val, pos_val])
    
    return graph


@pytest.fixture
def loop_graph_single_state():
    """
    Creates a graph with a single-state Repeat Zone.
    
    Structure:
        Capture -> Repeat(3) -> Sample -> Process -> Capture -> Output
    
    Resources:
        0: capture_Capture (internal, initial state)
        1: loop_ping
        2: loop_pong  
        3: Output
    """
    from compute_nodes.ir.graph import Graph, IRBuilder, ValueKind
    from compute_nodes.ir.ops import OpCode
    from compute_nodes.ir.resources import ImageDesc, ResourceAccess
    from compute_nodes.ir.types import DataType
    
    graph = Graph(name="LoopGraph")
    builder = IRBuilder(graph)
    
    # Resources
    initial_desc = ImageDesc("capture_Capture", ResourceAccess.READ_WRITE, size=(512, 512))
    ping_desc = ImageDesc("loop_ping", ResourceAccess.READ_WRITE, size=(512, 512))
    pong_desc = ImageDesc("loop_pong", ResourceAccess.READ_WRITE, size=(512, 512))
    output_desc = ImageDesc("Output", ResourceAccess.WRITE, size=(512, 512))
    
    builder.add_resource(initial_desc)
    builder.add_resource(ping_desc)
    builder.add_resource(pong_desc)
    builder.add_resource(output_desc)
    
    # Initial capture
    pos = builder._new_value(ValueKind.BUILTIN, DataType.VEC3)
    builder.add_op(OpCode.IMAGE_STORE, [builder.graph.ops[0], pos, pos])
    
    # Loop begin
    loop_begin = builder.add_op(OpCode.PASS_LOOP_BEGIN, [])
    loop_begin.attrs['iterations'] = 3
    loop_begin.attrs['state_vars'] = [
        {'name': 'State', 'ping_idx': 1, 'pong_idx': 2, 'copy_from_resource': 0}
    ]
    
    # Loop body - sample and store
    ping_val = builder._new_value(ValueKind.ARGUMENT, DataType.VEC4)
    ping_val.resource_index = 1
    sample = builder.add_op(OpCode.SAMPLE, [ping_val, pos])
    sample_out = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=sample)
    sample.add_output(sample_out)
    
    pong_val = builder._new_value(ValueKind.ARGUMENT, DataType.VEC4)
    pong_val.resource_index = 2
    builder.add_op(OpCode.IMAGE_STORE, [pong_val, pos, sample_out])
    
    # Loop end
    builder.add_op(OpCode.PASS_LOOP_END, [])
    
    # Output
    output_val = builder._new_value(ValueKind.ARGUMENT, DataType.VEC4)
    output_val.resource_index = 3
    builder.add_op(OpCode.IMAGE_STORE, [output_val, pos, sample_out])
    
    return graph


@pytest.fixture  
def multi_size_output_graph():
    """
    Creates a graph where two outputs have different sizes.
    
    Used to test pass splitting by output size.
    
    Resources:
        0: Output_768 (768x768)
        1: Output_666 (666x666)
    """
    from compute_nodes.ir.graph import Graph, IRBuilder, ValueKind
    from compute_nodes.ir.ops import OpCode
    from compute_nodes.ir.resources import ImageDesc, ResourceAccess
    from compute_nodes.ir.types import DataType
    
    graph = Graph(name="MultiSizeGraph")
    builder = IRBuilder(graph)
    
    # Two outputs with different sizes
    out1_desc = ImageDesc("Output_768", ResourceAccess.WRITE, size=(768, 768))
    out2_desc = ImageDesc("Output_666", ResourceAccess.WRITE, size=(666, 666))
    
    out1_val = builder.add_resource(out1_desc)
    out2_val = builder.add_resource(out2_desc)
    
    pos = builder._new_value(ValueKind.BUILTIN, DataType.VEC3)
    
    # Store to both
    builder.add_op(OpCode.IMAGE_STORE, [out1_val, pos, pos])
    builder.add_op(OpCode.IMAGE_STORE, [out2_val, pos, pos])
    
    return graph


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def assert_pass_count(passes, expected_count, msg=""):
    """Assert that the number of passes matches expected."""
    from compute_nodes.planner.loops import PassLoop
    
    # Count non-loop passes
    count = sum(1 for p in passes if not isinstance(p, PassLoop))
    # Add loop body counts
    for p in passes:
        if isinstance(p, PassLoop):
            count += len(p.body_passes)
    
    assert count == expected_count, f"Expected {expected_count} passes, got {count}. {msg}"


def assert_pass_writes_size(compute_pass, graph, expected_size):
    """Assert that all write resources in the pass have the expected size."""
    for res_idx in compute_pass.writes_idx:
        res = graph.resources[res_idx]
        assert res.size == expected_size, \
            f"Resource {res.name} size {res.size} != expected {expected_size}"
