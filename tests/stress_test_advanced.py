"""
Advanced Stress Tests for Compute Nodes
========================================
Tests complex scenarios:
- Node groups (nested, complex)
- Repeat zones (nested, within groups)
- Multi-resolution
- Edge cases and extreme combinations
"""

import sys
import os
import bpy
import gpu

# Ensure we can import the local package
ADDON_DIR = r"c:\Users\anton\Desktop\addon\addons\Compute Nodes"
if ADDON_DIR not in sys.path:
    sys.path.append(ADDON_DIR)

# Track failures
fails = []
warnings = []

# --- SETUP & RELOAD ---
def setup_addon():
    # 1. Unregister existing if present
    if 'compute_nodes' in sys.modules:
        try:
            print("Unregistering old compute_nodes...")
            sys.modules['compute_nodes'].unregister()
        except Exception as e:
            print(f"Error unregistering: {e}")

    # 2. Clear sys.modules to force reload
    keys = [k for k in sys.modules.keys() if k.startswith('compute_nodes')]
    for k in keys:
        del sys.modules[k]

    # 3. Import and Register
    print("Importing compute_nodes...")
    import compute_nodes
    try:
        compute_nodes.register()
        print("Registered compute_nodes.")
    except Exception as e:
        print(f"Error registering: {e}")

    from compute_nodes.graph_extract import extract_graph
    from compute_nodes.planner.scheduler import schedule_passes
    from compute_nodes.codegen.glsl import ShaderGenerator
    from compute_nodes.runtime.shaders import ShaderManager
    
    return extract_graph, schedule_passes, ShaderGenerator, ShaderManager

# Execute Setup ONCE
extract_graph, schedule_passes, ShaderGenerator, ShaderManager = setup_addon()

def validate_tree(tree, test_name):
    """
    Validate a node tree by extracting, scheduling, and compiling shaders.
    Returns True if successful, False otherwise.
    """
    print(f"\n{'='*60}")
    print(f"Testing: {test_name}")
    print(f"{'='*60}")
    
    try:
        # 1. Extract
        print("  [1/3] Extracting graph...")
        graph = extract_graph(tree)
        
        # 2. Schedule
        print("  [2/3] Scheduling passes...")
        passes = schedule_passes(graph)
        
        if not passes:
            msg = f"{test_name}: No passes generated"
            warnings.append(msg)
            print(f"  WARN: {msg}")
            return True  # Not necessarily a failure
        
        print(f"  Generated {len(passes)} passes")
        
        # 3. Generate & Compile
        print("  [3/3] Generating and compiling shaders...")
        gen = ShaderGenerator(tree)
        shader_mgr = ShaderManager()
        
        for i, p in enumerate(passes):
            print(f"    Pass {i+1}/{len(passes)}...", end='')
            src = gen.generate(p)
            try:
                shader_mgr.get_shader(src, graph.resources)
                print(" ✓")
            except Exception as e:
                msg = f"{test_name} [Pass {i+1} GLSL]: {e}"
                fails.append(msg)
                print(f" ✗\n      {e}")
                # Optionally print shader source
                # print(src)
                return False
        
        print(f"  ✓ SUCCESS: {test_name}")
        return True
        
    except Exception as e:
        msg = f"{test_name} [PYTHON]: {e}"
        fails.append(msg)
        print(f"  ✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================================================
# TEST CASE GENERATORS
# =============================================================================

def test_simple_nodegroup():
    """Test 1: Simple node group with field operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Create node group
    group = bpy.data.node_groups.new("SimpleGroup", "ComputeNodeTree")
    group_in = group.nodes.new("ComputeNodeGroupInput")
    group_out = group.nodes.new("ComputeNodeGroupOutput")
    
    # Add math inside group: Input * 2
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    
    group.links.new(group_in.outputs[0], math.inputs[0])
    math.inputs[1].default_value = 2.0
    group.links.new(math.outputs[0], group_out.inputs[0])
    
    # Main tree: Position → Group → Capture → Output
    tree = bpy.data.node_groups.new("Test_SimpleGroup", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = group
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    # Create output image
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    # Link: Position.X → Group → Capture → Output
    tree.links.new(pos.outputs['X'], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Simple Node Group")


def test_nested_nodegroups():
    """Test 2: Nested node groups (3 levels)"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Level 3 (innermost): x + 1
    group_l3 = bpy.data.node_groups.new("Level3", "ComputeNodeTree")
    in3 = group_l3.nodes.new("ComputeNodeGroupInput")
    out3 = group_l3.nodes.new("ComputeNodeGroupOutput")
    math3 = group_l3.nodes.new("ComputeNodeMath")
    math3.operation = 'ADD'
    math3.inputs[1].default_value = 1.0
    group_l3.links.new(in3.outputs[0], math3.inputs[0])
    group_l3.links.new(math3.outputs[0], out3.inputs[0])
    
    # Level 2: (x + 1) * 2
    group_l2 = bpy.data.node_groups.new("Level2", "ComputeNodeTree")
    in2 = group_l2.nodes.new("ComputeNodeGroupInput")
    out2 = group_l2.nodes.new("ComputeNodeGroupOutput")
    group2 = group_l2.nodes.new("ComputeNodeGroup")
    group2.node_tree = group_l3
    math2 = group_l2.nodes.new("ComputeNodeMath")
    math2.operation = 'MUL'
    math2.inputs[1].default_value = 2.0
    group_l2.links.new(in2.outputs[0], group2.inputs[0])
    group_l2.links.new(group2.outputs[0], math2.inputs[0])
    group_l2.links.new(math2.outputs[0], out2.inputs[0])
    
    # Level 1: ((x + 1) * 2) - 0.5
    group_l1 = bpy.data.node_groups.new("Level1", "ComputeNodeTree")
    in1 = group_l1.nodes.new("ComputeNodeGroupInput")
    out1 = group_l1.nodes.new("ComputeNodeGroupOutput")
    group1 = group_l1.nodes.new("ComputeNodeGroup")
    group1.node_tree = group_l2
    math1 = group_l1.nodes.new("ComputeNodeMath")
    math1.operation = 'SUB'
    math1.inputs[1].default_value = 0.5
    group_l1.links.new(in1.outputs[0], group1.inputs[0])
    group_l1.links.new(group1.outputs[0], math1.inputs[0])
    group_l1.links.new(math1.outputs[0], out1.inputs[0])
    
    # Main tree
    tree = bpy.data.node_groups.new("Test_NestedGroups", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    group_main = tree.nodes.new("ComputeNodeGroup")
    group_main.node_tree = group_l1
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(pos.outputs['X'], group_main.inputs[0])
    tree.links.new(group_main.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Nested Node Groups (3 levels)")


def test_nodegroup_with_grid_ops():
    """Test 3: Node group containing Sample and Capture"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Create node group with grid operations
    group = bpy.data.node_groups.new("GridGroup", "ComputeNodeTree")
    group_in = group.nodes.new("ComputeNodeGroupInput")
    group_out = group.nodes.new("ComputeNodeGroupOutput")
    
    # Inside group: Input Grid → Sample → Math → Capture → Output Grid
    sample = group.nodes.new("ComputeNodeSample")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 0.5
    capture = group.nodes.new("ComputeNodeCapture")
    capture.width = 32
    capture.height = 32
    
    group.links.new(group_in.outputs[0], sample.inputs['Grid'])
    group.links.new(sample.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], capture.inputs[0])
    group.links.new(capture.outputs[0], group_out.inputs[0])
    
    # Main tree: Noise → Capture → Group → Output
    tree = bpy.data.node_groups.new("Test_GroupGridOps", "ComputeNodeTree")
    noise = tree.nodes.new("ComputeNodeNoiseTexture")
    noise.dimensions = '2D'
    capture1 = tree.nodes.new("ComputeNodeCapture")
    capture1.width = 64
    capture1.height = 64
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = group
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 32, 32)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(noise.outputs['Fac'], capture1.inputs[0])
    tree.links.new(capture1.outputs[0], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Node Group with Grid Operations")


def test_basic_repeat():
    """Test 4: Basic repeat zone with field operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_BasicRepeat", "ComputeNodeTree")
    
    # Create repeat pair
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_in.iterations = 5
    
    # Inside repeat: value → Math +1 → output
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 1.0
    
    tree.links.new(repeat_in.outputs[0], math.inputs[0])
    tree.links.new(math.outputs[0], repeat_out.inputs[0])
    
    # Before loop: Position.X → Repeat Input
    pos = tree.nodes.new("ComputeNodePosition")
    tree.links.new(pos.outputs['X'], repeat_in.inputs[0])
    
    # After loop: Repeat Output → Capture → Output
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(repeat_out.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Basic Repeat Zone")


def test_repeat_with_grid_ops():
    """Test 5: Repeat zone with Capture inside (changing grid each iteration)"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_RepeatGridOps", "ComputeNodeTree")
    
    # Initial grid: Noise → Capture
    noise = tree.nodes.new("ComputeNodeNoiseTexture")
    noise.dimensions = '2D'
    capture_initial = tree.nodes.new("ComputeNodeCapture")
    capture_initial.width = 64
    capture_initial.height = 64
    
    tree.links.new(noise.outputs['Fac'], capture_initial.inputs[0])
    
    # Repeat zone
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_in.iterations = 3
    
    tree.links.new(capture_initial.outputs[0], repeat_in.inputs[0])
    
    # Inside repeat: Sample → Math → Capture
    sample = tree.nodes.new("ComputeNodeSample")
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 0.9  # Darken each iteration
    capture_loop = tree.nodes.new("ComputeNodeCapture")
    capture_loop.width = 64
    capture_loop.height = 64
    
    tree.links.new(repeat_in.outputs[0], sample.inputs['Grid'])
    tree.links.new(sample.outputs[0], math.inputs[0])
    tree.links.new(math.outputs[0], capture_loop.inputs[0])
    tree.links.new(capture_loop.outputs[0], repeat_out.inputs[0])
    
    # Output
    out = tree.nodes.new("ComputeNodeOutput")
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(repeat_out.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Repeat with Grid Operations")


def test_nested_repeats():
    """Test 6: Nested repeat zones (repeat inside repeat)"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_NestedRepeats", "ComputeNodeTree")
    
    # Outer repeat
    repeat_outer_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_outer_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_outer_in.iterations = 3
    
    # Inner repeat
    repeat_inner_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_inner_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_inner_in.iterations = 2
    
    # Math in inner loop
    math_inner = tree.nodes.new("ComputeNodeMath")
    math_inner.operation = 'ADD'
    math_inner.inputs[1].default_value = 0.1
    
    # Math in outer loop (after inner)
    math_outer = tree.nodes.new("ComputeNodeMath")
    math_outer.operation = 'MUL'
    math_outer.inputs[1].default_value = 1.1
    
    # Initial value
    pos = tree.nodes.new("ComputeNodePosition")
    tree.links.new(pos.outputs['X'], repeat_outer_in.inputs[0])
    
    # Outer → Inner
    tree.links.new(repeat_outer_in.outputs[0], repeat_inner_in.inputs[0])
    
    # Inner loop
    tree.links.new(repeat_inner_in.outputs[0], math_inner.inputs[0])
    tree.links.new(math_inner.outputs[0], repeat_inner_out.inputs[0])
    
    # Inner → Outer
    tree.links.new(repeat_inner_out.outputs[0], math_outer.inputs[0])
    tree.links.new(math_outer.outputs[0], repeat_outer_out.inputs[0])
    
    # Output
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(repeat_outer_out.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Nested Repeat Zones")


def test_group_inside_repeat():
    """Test 7: Node group used inside repeat zone"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Create simple group: x * 2
    group = bpy.data.node_groups.new("MultiplyTwo", "ComputeNodeTree")
    group_in = group.nodes.new("ComputeNodeGroupInput")
    group_out = group.nodes.new("ComputeNodeGroupOutput")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 2.0
    group.links.new(group_in.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], group_out.inputs[0])
    
    # Main tree with repeat
    tree = bpy.data.node_groups.new("Test_GroupInRepeat", "ComputeNodeTree")
    
    pos = tree.nodes.new("ComputeNodePosition")
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_in.iterations = 4
    
    # Group inside repeat
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = group
    
    tree.links.new(pos.outputs['X'], repeat_in.inputs[0])
    tree.links.new(repeat_in.outputs[0], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], repeat_out.inputs[0])
    
    # Output
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(repeat_out.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Node Group Inside Repeat")


def test_repeat_inside_group():
    """Test 8: Repeat zone inside node group"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Create group with repeat inside
    group = bpy.data.node_groups.new("GroupWithRepeat", "ComputeNodeTree")
    group_in = group.nodes.new("ComputeNodeGroupInput")
    group_out = group.nodes.new("ComputeNodeGroupOutput")
    
    # Repeat inside group
    repeat_in = group.nodes.new("ComputeNodeRepeatInput")
    repeat_out = group.nodes.new("ComputeNodeRepeatOutput")
    repeat_in.iterations = 3
    
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 0.2
    
    group.links.new(group_in.outputs[0], repeat_in.inputs[0])
    group.links.new(repeat_in.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], repeat_out.inputs[0])
    group.links.new(repeat_out.outputs[0], group_out.inputs[0])
    
    # Main tree
    tree = bpy.data.node_groups.new("Test_RepeatInGroup", "ComputeNodeTree")
    
    pos = tree.nodes.new("ComputeNodePosition")
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = group
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(pos.outputs['X'], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Repeat Inside Node Group")


def test_repeat_group_repeat():
    """Test 9: Extreme nesting: Repeat → Group → Repeat"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Inner group with repeat
    inner_group = bpy.data.node_groups.new("InnerGroupRepeat", "ComputeNodeTree")
    ig_in = inner_group.nodes.new("ComputeNodeGroupInput")
    ig_out = inner_group.nodes.new("ComputeNodeGroupOutput")
    
    ig_repeat_in = inner_group.nodes.new("ComputeNodeRepeatInput")
    ig_repeat_out = inner_group.nodes.new("ComputeNodeRepeatOutput")
    ig_repeat_in.iterations = 2
    
    ig_math = inner_group.nodes.new("ComputeNodeMath")
    ig_math.operation = 'MUL'
    ig_math.inputs[1].default_value = 1.1
    
    inner_group.links.new(ig_in.outputs[0], ig_repeat_in.inputs[0])
    inner_group.links.new(ig_repeat_in.outputs[0], ig_math.inputs[0])
    inner_group.links.new(ig_math.outputs[0], ig_repeat_out.inputs[0])
    inner_group.links.new(ig_repeat_out.outputs[0], ig_out.inputs[0])
    
    # Main tree with outer repeat
    tree = bpy.data.node_groups.new("Test_RepeatGroupRepeat", "ComputeNodeTree")
    
    pos = tree.nodes.new("ComputeNodePosition")
    
    outer_repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    outer_repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    outer_repeat_in.iterations = 3
    
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = inner_group
    
    tree.links.new(pos.outputs['X'], outer_repeat_in.inputs[0])
    tree.links.new(outer_repeat_in.outputs[0], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], outer_repeat_out.inputs[0])
    
    # Output
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(outer_repeat_out.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Repeat → Group (with Repeat) → Repeat")


def test_multi_resolution():
    """Test 10: Multiple different grid resolutions in same tree"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_MultiResolution", "ComputeNodeTree")
    
    # Create three different resolution grids
    noise1 = tree.nodes.new("ComputeNodeNoiseTexture")
    noise1.dimensions = '2D'
    capture1 = tree.nodes.new("ComputeNodeCapture")
    capture1.width = 128
    capture1.height = 128
    tree.links.new(noise1.outputs['Fac'], capture1.inputs[0])
    
    noise2 = tree.nodes.new("ComputeNodeNoiseTexture")
    noise2.dimensions = '2D'
    capture2 = tree.nodes.new("ComputeNodeCapture")
    capture2.width = 64
    capture2.height = 64
    tree.links.new(noise2.outputs['Fac'], capture2.inputs[0])
    
    noise3 = tree.nodes.new("ComputeNodeNoiseTexture")
    noise3.dimensions = '2D'
    capture3 = tree.nodes.new("ComputeNodeCapture")
    capture3.width = 32
    capture3.height = 32
    tree.links.new(noise3.outputs['Fac'], capture3.inputs[0])
    
    # Sample all three and combine
    sample1 = tree.nodes.new("ComputeNodeSample")
    sample2 = tree.nodes.new("ComputeNodeSample")
    sample3 = tree.nodes.new("ComputeNodeSample")
    
    tree.links.new(capture1.outputs[0], sample1.inputs['Grid'])
    tree.links.new(capture2.outputs[0], sample2.inputs['Grid'])
    tree.links.new(capture3.outputs[0], sample3.inputs['Grid'])
    
    # Mix them
    mix1 = tree.nodes.new("ComputeNodeMix")
    mix1.data_type = 'FLOAT'
    mix1.inputs['Factor'].default_value = 0.5
    
    mix2 = tree.nodes.new("ComputeNodeMix")
    mix2.data_type = 'FLOAT'
    mix2.inputs['Factor'].default_value = 0.5
    
    tree.links.new(sample1.outputs[0], mix1.inputs['A'])
    tree.links.new(sample2.outputs[0], mix1.inputs['B'])
    tree.links.new(mix1.outputs['Result'], mix2.inputs['A'])
    tree.links.new(sample3.outputs[0], mix2.inputs['B'])
    
    # Final capture and output
    capture_final = tree.nodes.new("ComputeNodeCapture")
    capture_final.width = 64
    capture_final.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(mix2.outputs['Result'], capture_final.inputs[0])
    tree.links.new(capture_final.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Multi-Resolution (128x128, 64x64, 32x32)")


def test_resolution_cascade():
    """Test 11: Resolution cascade: high → low → high"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_ResolutionCascade", "ComputeNodeTree")
    
    # Start with high res
    noise = tree.nodes.new("ComputeNodeNoiseTexture")
    noise.dimensions = '2D'
    capture_high1 = tree.nodes.new("ComputeNodeCapture")
    capture_high1.width = 256
    capture_high1.height = 256
    tree.links.new(noise.outputs['Fac'], capture_high1.inputs[0])
    
    # Downsample to low res
    sample1 = tree.nodes.new("ComputeNodeSample")
    tree.links.new(capture_high1.outputs[0], sample1.inputs['Grid'])
    
    capture_low = tree.nodes.new("ComputeNodeCapture")
    capture_low.width = 32
    capture_low.height = 32
    tree.links.new(sample1.outputs[0], capture_low.inputs[0])
    
    # Upsample back to high res
    sample2 = tree.nodes.new("ComputeNodeSample")
    tree.links.new(capture_low.outputs[0], sample2.inputs['Grid'])
    
    capture_high2 = tree.nodes.new("ComputeNodeCapture")
    capture_high2.width = 128
    capture_high2.height = 128
    tree.links.new(sample2.outputs[0], capture_high2.inputs[0])
    
    # Output
    out = tree.nodes.new("ComputeNodeOutput")
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 128, 128)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(capture_high2.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Resolution Cascade (256→32→128)")


def test_deeply_nested_groups():
    """Test 12: 5+ levels of nested node groups"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Build 5 levels of groups, each adding 0.1
    current_group = None
    for level in range(5, 0, -1):
        group = bpy.data.node_groups.new(f"Level{level}", "ComputeNodeTree")
        group_in = group.nodes.new("ComputeNodeGroupInput")
        group_out = group.nodes.new("ComputeNodeGroupOutput")
        
        if current_group:
            # Use nested group
            nested = group.nodes.new("ComputeNodeGroup")
            nested.node_tree = current_group
            group.links.new(group_in.outputs[0], nested.inputs[0])
            
            math = group.nodes.new("ComputeNodeMath")
            math.operation = 'ADD'
            math.inputs[1].default_value = 0.1
            group.links.new(nested.outputs[0], math.inputs[0])
            group.links.new(math.outputs[0], group_out.inputs[0])
        else:
            # Innermost level
            math = group.nodes.new("ComputeNodeMath")
            math.operation = 'MUL'
            math.inputs[1].default_value = 2.0
            group.links.new(group_in.outputs[0], math.inputs[0])
            group.links.new(math.outputs[0], group_out.inputs[0])
        
        current_group = group
    
    # Main tree
    tree = bpy.data.node_groups.new("Test_Deeply_Nested", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    group_main = tree.nodes.new("ComputeNodeGroup")
    group_main.node_tree = current_group
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(pos.outputs['X'], group_main.inputs[0])
    tree.links.new(group_main.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Deeply Nested Groups (5 levels)")


def test_group_with_multiple_passes():
    """Test 13: Node group that internally creates multiple GPU passes"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Create group with grid operations (creates passes)
    group = bpy.data.node_groups.new("MultiPassGroup", "ComputeNodeTree")
    group_in = group.nodes.new("ComputeNodeGroupInput")
    group_out = group.nodes.new("ComputeNodeGroupOutput")
    
    # Pass 1: Noise → Capture
    noise = group.nodes.new("ComputeNodeNoiseTexture")
    noise.dimensions = '2D'
    capture1 = group.nodes.new("ComputeNodeCapture")
    capture1.width = 64
    capture1.height = 64
    group.links.new(noise.outputs['Fac'], capture1.inputs[0])
    
    # Pass 2: Sample → Math → Capture
    sample = group.nodes.new("ComputeNodeSample")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    capture2 = group.nodes.new("ComputeNodeCapture")
    capture2.width = 64
    capture2.height = 64
    
    group.links.new(capture1.outputs[0], sample.inputs['Grid'])
    group.links.new(sample.outputs[0], math.inputs[0])
    group.links.new(group_in.outputs[0], math.inputs[1])  # Use input as multiplier
    group.links.new(math.outputs[0], capture2.inputs[0])
    group.links.new(capture2.outputs[0], group_out.inputs[0])
    
    # Main tree
    tree = bpy.data.node_groups.new("Test_GroupMultiPass", "ComputeNodeTree")
    value = tree.nodes.new("ComputeNodeValue")
    value.outputs[0].default_value = 0.5
    
    group_node = tree.nodes.new("ComputeNodeGroup")
    group_node.node_tree = group
    
    out = tree.nodes.new("ComputeNodeOutput")
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(value.outputs[0], group_node.inputs[0])
    tree.links.new(group_node.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Node Group with Multiple Internal Passes")


def test_3d_grid_operations():
    """Test 14: 3D grid operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_3D_Grid", "ComputeNodeTree")
    
    # 3D noise
    noise = tree.nodes.new("ComputeNodeNoiseTexture")
    noise.dimensions = '3D'
    
    # 3D capture
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 32
    capture.height = 32
    capture.depth = 32
    
    # Sample and output
    sample = tree.nodes.new("ComputeNodeSample")
    
    out = tree.nodes.new("ComputeNodeOutput")
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 32, 32)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(noise.outputs['Fac'], capture.inputs[0])
    tree.links.new(capture.outputs[0], sample.inputs['Grid'])
    tree.links.new(sample.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "3D Grid Operations")


def test_empty_repeat():
    """Test 15: Edge case - Repeat with zero iterations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test_EmptyRepeat", "ComputeNodeTree")
    
    pos = tree.nodes.new("ComputeNodePosition")
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    repeat_in.iterations = 0  # Zero iterations!
    
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 1.0
    
    capture = tree.nodes.new("ComputeNodeCapture")
    capture.width = 64
    capture.height = 64
    out = tree.nodes.new("ComputeNodeOutput")
    
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    out.target = bpy.data.images["TestImg"]
    
    tree.links.new(pos.outputs['X'], repeat_in.inputs[0])
    tree.links.new(repeat_in.outputs[0], math.inputs[0])
    tree.links.new(math.outputs[0], repeat_out.inputs[0])
    tree.links.new(repeat_out.outputs[0], capture.inputs[0])
    tree.links.new(capture.outputs[0], out.inputs[0])
    
    return validate_tree(tree, "Empty Repeat (0 iterations)")


# =============================================================================
# MAIN TEST RUNNER
# =============================================================================

def run_all_tests():
    """Run all stress tests"""
    tests = [
        test_simple_nodegroup,
        test_nested_nodegroups,
        test_nodegroup_with_grid_ops,
        test_basic_repeat,
        test_repeat_with_grid_ops,
        test_nested_repeats,
        test_group_inside_repeat,
        test_repeat_inside_group,
        test_repeat_group_repeat,
        test_multi_resolution,
        test_resolution_cascade,
        test_deeply_nested_groups,
        test_group_with_multiple_passes,
        test_3d_grid_operations,
        test_empty_repeat,
    ]
    
    print("\n" + "="*60)
    print("STARTING ADVANCED STRESS TESTS")
    print("="*60)
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ EXCEPTION in {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    # Final report
    print("\n" + "="*60)
    print("STRESS TEST SUMMARY")
    print("="*60)
    print(f"Total Tests: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"\nFailures: {len(fails)}")
    for f in fails:
        print(f"  ✗ {f}")
    print(f"\nWarnings: {len(warnings)}")
    for w in warnings:
        print(f"  ⚠ {w}")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_all_tests()
