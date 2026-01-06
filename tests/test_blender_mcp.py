"""
Blender MCP Test Runner for Compute Nodes

This script runs tests directly in Blender via MCP, providing:
- Real GPU execution (no mocks)
- Accurate test results
- Validation of actual shader compilation

Usage:
    Run via MCP from IDE, or in Blender Python console:
    
    exec(open(r'c:\\path\\to\\tests\\test_blender_mcp.py').read())

If Blender/MCP is not available, the script will notify the user.
"""

import bpy
import sys
import importlib


def reload_modules():
    """Full reload of compute_nodes modules."""
    to_remove = [n for n in sys.modules if 'compute_nodes' in n.lower()]
    for n in sorted(to_remove, reverse=True):
        del sys.modules[n]


def get_modules():
    """Import all needed modules via Blender addon path."""
    reload_modules()
    
    mods = {}
    mods['graph'] = importlib.import_module('Compute Nodes.compute_nodes.ir.graph')
    mods['ops'] = importlib.import_module('Compute Nodes.compute_nodes.ir.ops')
    mods['res'] = importlib.import_module('Compute Nodes.compute_nodes.ir.resources')
    mods['types'] = importlib.import_module('Compute Nodes.compute_nodes.ir.types')
    mods['sched'] = importlib.import_module('Compute Nodes.compute_nodes.planner.scheduler')
    mods['operators'] = importlib.import_module('Compute Nodes.compute_nodes.operators')
    
    return mods


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_scheduler_single_pass(m):
    """A simple graph creates exactly 1 pass."""
    graph = m['graph'].Graph("Test1")
    builder = m['graph'].IRBuilder(graph)
    desc = m['res'].ImageDesc("Output", m['res'].ResourceAccess.WRITE, size=(512, 512))
    val = builder.add_resource(desc)
    pos = builder._new_value(m['graph'].ValueKind.BUILTIN, m['types'].DataType.VEC3)
    builder.add_op(m['ops'].OpCode.IMAGE_STORE, [val, pos, pos])
    passes = m['sched'].schedule_passes(graph)
    assert len(passes) == 1, f"Expected 1, got {len(passes)}"


def test_scheduler_hazard_split(m):
    """Read-after-write creates new pass (hazard detection)."""
    graph = m['graph'].Graph("Test2")
    builder = m['graph'].IRBuilder(graph)
    desc = m['res'].ImageDesc("ResA", m['res'].ResourceAccess.READ_WRITE, size=(512, 512))
    val_a = builder.add_resource(desc)
    pos = builder._new_value(m['graph'].ValueKind.BUILTIN, m['types'].DataType.VEC3)
    builder.add_op(m['ops'].OpCode.IMAGE_STORE, [val_a, pos, pos])
    builder.add_op(m['ops'].OpCode.IMAGE_LOAD, [val_a])
    passes = m['sched'].schedule_passes(graph)
    assert len(passes) == 2, f"Expected 2, got {len(passes)}"


def test_scheduler_size_split(m):
    """Different output sizes create separate passes."""
    graph = m['graph'].Graph("Test3")
    builder = m['graph'].IRBuilder(graph)
    desc1 = m['res'].ImageDesc("Out768", m['res'].ResourceAccess.WRITE, size=(768, 768))
    desc2 = m['res'].ImageDesc("Out666", m['res'].ResourceAccess.WRITE, size=(666, 666))
    val1 = builder.add_resource(desc1)
    val2 = builder.add_resource(desc2)
    pos = builder._new_value(m['graph'].ValueKind.BUILTIN, m['types'].DataType.VEC3)
    builder.add_op(m['ops'].OpCode.IMAGE_STORE, [val1, pos, pos])
    builder.add_op(m['ops'].OpCode.IMAGE_STORE, [val2, pos, pos])
    passes = m['sched'].schedule_passes(graph)
    assert len(passes) == 2, f"Expected 2, got {len(passes)}"


def test_loop_dynamic_size(m):
    """Test A with 3 iterations produces 768x768 output."""
    tree = bpy.data.node_groups.get("Test A")
    if not tree:
        raise AssertionError("Test A node tree not found")
    
    repeat_input = tree.nodes.get("Repeat Zone (Input).001")
    if repeat_input:
        repeat_input.inputs["Iterations"].default_value = 3
    
    m['operators'].ExecutionContext._instance = None
    m['operators'].execute_compute_tree(tree, bpy.context)
    
    img = bpy.data.images.get("Test A")
    assert img is not None, "Output image not created"
    assert img.size[0] == 768, f"Expected 768, got {img.size[0]}"


def test_position_values(m):
    """Position values correctly normalized (center≈0.5, top-right≈1.0)."""
    img = bpy.data.images.get("Test A")
    if not img or img.size[0] == 0:
        raise AssertionError("Test A image not available")
    
    w, h = img.size[0], img.size[1]
    pixels = img.pixels[:]
    
    center_idx = ((h // 2) * w + (w // 2)) * 4
    tr_idx = ((h - 1) * w + (w - 1)) * 4
    
    assert abs(pixels[center_idx] - 0.5) < 0.1, f"Center R: {pixels[center_idx]}"
    assert abs(pixels[tr_idx] - 1.0) < 0.1, f"TopRight R: {pixels[tr_idx]}"


def test_multi_grid(m):
    """Test B with multi-grid produces correct sizes."""
    tree = bpy.data.node_groups.get("Test B")
    if not tree:
        raise AssertionError("Test B node tree not found")
    
    repeat_input = tree.nodes.get("Repeat Zone (Input).001")
    if repeat_input:
        repeat_input.inputs["Iterations"].default_value = 3
    
    m['operators'].ExecutionContext._instance = None
    m['operators'].execute_compute_tree(tree, bpy.context)
    
    img1 = bpy.data.images.get("Test B 1")
    img2 = bpy.data.images.get("Test B 2")
    
    assert img1 is not None, "Test B 1 not created"
    assert img2 is not None, "Test B 2 not created"
    assert img1.size[0] == 768, f"B1 expected 768, got {img1.size[0]}"
    assert img2.size[0] == 666, f"B2 expected 666, got {img2.size[0]}"


def test_multi_grid_uv(m):
    """Test B 2 has correct UV values (top-right≈1.0)."""
    img2 = bpy.data.images.get("Test B 2")
    if not img2 or img2.size[0] == 0:
        raise AssertionError("Test B 2 image not available")
    
    w, h = img2.size[0], img2.size[1]
    pixels = img2.pixels[:]
    tr_idx = ((h - 1) * w + (w - 1)) * 4
    
    assert abs(pixels[tr_idx] - 1.0) < 0.1, f"B2 TopRight: {pixels[tr_idx]}"


# =============================================================================
# MAIN
# =============================================================================

def run_all_tests():
    """Run all tests and print results."""
    m = get_modules()
    
    tests = [
        ("test_scheduler_single_pass", test_scheduler_single_pass),
        ("test_scheduler_hazard_split", test_scheduler_hazard_split),
        ("test_scheduler_size_split", test_scheduler_size_split),
        ("test_loop_dynamic_size", test_loop_dynamic_size),
        ("test_position_values", test_position_values),
        ("test_multi_grid", test_multi_grid),
        ("test_multi_grid_uv", test_multi_grid_uv),
    ]
    
    print("\n" + "=" * 60)
    print("COMPUTE NODES TEST SUITE (MCP)")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for name, func in tests:
        try:
            func(m)
            print(f"  ✓ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗ {name}: ERROR - {e}")
            failed += 1
    
    print("\n" + "-" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60 + "\n")
    
    return passed, failed


# Run when executed
if __name__ == "__main__" or True:  # Always run when exec()'d
    try:
        import bpy
        run_all_tests()
    except ImportError:
        print("""
╔════════════════════════════════════════════════════════════╗
║  BLENDER NOT AVAILABLE                                     ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  To run tests, please:                                     ║
║                                                            ║
║  1. Open Blender with MCP addon enabled                    ║
║  2. Run this script via MCP from your IDE                  ║
║                                                            ║
║  Or in Blender Python console:                             ║
║  exec(open(r'path/to/test_blender_mcp.py').read())         ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""")
