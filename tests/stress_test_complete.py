"""
Complete Comprehensive Stress Test Suite for Compute Nodes
===========================================================
Final corrected version with all 15 tests.

Tests:
1-3: Node Groups (simple, nested, with grid ops)
4-6: Repeat Zones (basic, with grids, nested)
7-9: Combined (group in repeat, repeat in group, mixed nesting)
10-12: Multi-resolution scenarios
13-15: Edge cases (deeply nested, 3D, zero iterations)
"""

import sys
import bpy

# Setup addon
ADDON_DIR = r"c:\Users\anton\Desktop\addon\addons\Compute Nodes"
if ADDON_DIR not in sys.path:
    sys.path.append(ADDON_DIR)

if 'compute_nodes' in sys.modules:
    try:
        sys.modules['compute_nodes'].unregister()
    except:
        pass

keys = [k for k in sys.modules.keys() if k.startswith('compute_nodes')]
for k in keys:
    del sys.modules[k]

import compute_nodes
try:
    compute_nodes.register()
except:
    pass

from compute_nodes.graph_extract import extract_graph
from compute_nodes.planner.scheduler import schedule_passes
from compute_nodes.codegen.glsl import ShaderGenerator
from compute_nodes.runtime.shaders import ShaderManager

# Global result tracking
fails = []
warnings = []
successes = []

def validate_tree(tree, test_name):
    """Validate a node tree through extraction, scheduling, and shader compilation."""
    print(f"\n[{test_name}]", end=' ')
    try:
        graph = extract_graph(tree)
        passes = schedule_passes(graph)
        
        if not passes:
            msg = f"{test_name}: No passes generated"
            warnings.append(msg)
            print("⚠ No passes")
            return True
        
        gen = ShaderGenerator(graph)
        shader_mgr = ShaderManager()
        
        # Flatten PassLoops to get all ComputePass objects
        def get_all_compute_passes(items):
            """Recursively extract ComputePass objects from mixed list."""
            result = []
            for item in items:
                # Check if it's a PassLoop by duck typing
                if hasattr(item, 'body_passes'):
                    # It's a PassLoop - recurse into body
                    result.extend(get_all_compute_passes(item.body_passes))
                else:
                    # It's a ComputePass - add it
                    result.append(item)
            return result
        
        compute_passes = get_all_compute_passes(passes)
        
        for i, p in enumerate(compute_passes):
            src = gen.generate(p)
            try:
                # CRITICAL FIX: Pass all required parameters like real executor does
                # This allows ShaderManager to properly declare image/sampler bindings
                shader_mgr.get_shader(
                    src,
                    resources=graph.resources,
                    reads_idx=p.reads_idx,
                    writes_idx=p.writes_idx,
                    dispatch_size=p.dispatch_size
                )
            except Exception as e:
                msg = f"{test_name} [Pass {i+1}/{len(compute_passes)}]: {str(e)[:70]}"
                fails.append(msg)
                print(f"✗ Pass {i+1} failed: {str(e)[:40]}")
                return False
        
        successes.append(test_name)
        print(f"✓ {len(compute_passes)} passes OK")
        return True
        
    except Exception as e:
        msg = f"{test_name}: {str(e)[:70]}"
        fails.append(msg)
        print(f"✗ Exception: {str(e)[:40]}")
        import traceback
        traceback.print_exc()
        return False

def mk_img():
    """Helper to create/get test image."""
    if "TestImg" not in bpy.data.images:
        bpy.data.images.new("TestImg", 64, 64)
    return bpy.data.images["TestImg"]

def pair_repeat_nodes(repeat_in, repeat_out):
    """Helper to pair Repeat Input and Output nodes.
    
    This is required before creating connections to repeat zones
    to avoid index errors when accessing repeat_items.
    """
    repeat_in.paired_output = repeat_out.name
    repeat_out.paired_input = repeat_in.name
    repeat_in._sync_paired_output()


# ============================================================================
# TEST DEFINITIONS
# ============================================================================

def test1_simple_nodegroup():
    """T1: Simple node group with field operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Group: x * 2
    group = bpy.data.node_groups.new("SimpleGroup", "ComputeNodeTree")
    gin = group.nodes.new("ComputeNodeGroupInput")
    gout = group.nodes.new("ComputeNodeGroupOutput")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 2.0
    group.links.new(gin.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], gout.inputs[0])
    
    # Main: Position.X → Group → Capture → Output
    tree = bpy.data.node_groups.new("Test1", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = group
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(sep.outputs['X'], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T1: Simple NodeGroup")

def test2_nested_nodegroups():
    """T2: Nested node groups (3 levels deep)"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Level 3: x + 1
    g3 = bpy.data.node_groups.new("L3", "ComputeNodeTree")
    gi3 = g3.nodes.new("ComputeNodeGroupInput")
    go3 = g3.nodes.new("ComputeNodeGroupOutput")
    m3 = g3.nodes.new("ComputeNodeMath")
    m3.operation = 'ADD'
    m3.inputs[1].default_value = 1.0
    g3.links.new(gi3.outputs[0], m3.inputs[0])
    g3.links.new(m3.outputs[0], go3.inputs[0])
    
    # Level 2: (x+1) * 2
    g2 = bpy.data.node_groups.new("L2", "ComputeNodeTree")
    gi2 = g2.nodes.new("ComputeNodeGroupInput")
    go2 = g2.nodes.new("ComputeNodeGroupOutput")
    gn2 = g2.nodes.new("ComputeNodeGroup")
    gn2.node_tree = g3
    m2 = g2.nodes.new("ComputeNodeMath")
    m2.operation = 'MUL'
    m2.inputs[1].default_value = 2.0
    g2.links.new(gi2.outputs[0], gn2.inputs[0])
    g2.links.new(gn2.outputs[0], m2.inputs[0])
    g2.links.new(m2.outputs[0], go2.inputs[0])
    
    # Level 1: ((x+1)*2) - 0.5
    g1 = bpy.data.node_groups.new("L1", "ComputeNodeTree")
    gi1 = g1.nodes.new("ComputeNodeGroupInput")
    go1 = g1.nodes.new("ComputeNodeGroupOutput")
    gn1 = g1.nodes.new("ComputeNodeGroup")
    gn1.node_tree = g2
    m1 = g1.nodes.new("ComputeNodeMath")
    m1.operation = 'SUB'
    m1.inputs[1].default_value = 0.5
    g1.links.new(gi1.outputs[0], gn1.inputs[0])
    g1.links.new(gn1.outputs[0], m1.inputs[0])
    g1.links.new(m1.outputs[0], go1.inputs[0])
    
    # Main
    tree = bpy.data.node_groups.new("Test2", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    gmain = tree.nodes.new("ComputeNodeGroup")
    gmain.node_tree = g1
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(sep.outputs['X'], gmain.inputs[0])
    tree.links.new(gmain.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T2: Nested Groups (3 levels)")

def test3_nodegroup_with_grid_ops():
    """T3: Node group containing Sample and Capture"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Group with grid operations
    group = bpy.data.node_groups.new("GridGroup", "ComputeNodeTree")
    gin = group.nodes.new("ComputeNodeGroupInput")
    gout = group.nodes.new("ComputeNodeGroupOutput")
    sample = group.nodes.new("ComputeNodeSample")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 0.5
    capture = group.nodes.new("ComputeNodeCapture")
    capture.width = capture.height = 32
    group.links.new(gin.outputs[0], sample.inputs['Grid'])
    group.links.new(sample.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], capture.inputs[0])
    group.links.new(capture.outputs[0], gout.inputs[0])
    
    # Main: White Noise → Capture → Group → Output
    tree = bpy.data.node_groups.new("Test3", "ComputeNodeTree")
    wnoise = tree.nodes.new("ComputeNodeWhiteNoise")
    cap1 = tree.nodes.new("ComputeNodeCapture")
    cap1.width = cap1.height = 64
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = group
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(wnoise.outputs['Value'], cap1.inputs[0])
    tree.links.new(cap1.outputs[0], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], out.inputs[0])
    return validate_tree(tree, "T3: Group w/ Grid Ops")

def test4_basic_repeat():
    """T4: Basic repeat zone with field operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test4", "ComputeNodeTree")
    
    # Repeat zone
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(repeat_in, repeat_out)  # Pair before connections
    repeat_in.iterations = 5
    
    # Before repeat: Position.X
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    
    # Connect to extension socket FIRST to create state item
    tree.links.new(sep.outputs['X'], repeat_in.inputs[-1])  # Extension socket
    
    # Inside repeat: +1
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 1.0
    tree.links.new(repeat_in.outputs[1], math.inputs[0])  # Current: State 1
    tree.links.new(math.outputs[0], repeat_out.inputs[0])  # Next: State 1
    
    # After repeat
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(repeat_out.outputs[0], cap.inputs[0])  # Final: State 1
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T4: Basic Repeat")

def test5_repeat_with_grid_ops():
    """T5: Repeat zone with Capture inside"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test5", "ComputeNodeTree")
    
    # Initial grid
    wnoise = tree.nodes.new("ComputeNodeWhiteNoise")
    cap_init = tree.nodes.new("ComputeNodeCapture")
    cap_init.width = cap_init.height = 64
    tree.links.new(wnoise.outputs['Value'], cap_init.inputs[0])
    
    # Repeat zone
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(repeat_in, repeat_out)  # Pair before connections
    repeat_in.iterations = 3
    tree.links.new(cap_init.outputs[0], repeat_in.inputs[0])
    
    # Inside repeat: Sample → Math → Capture
    sample = tree.nodes.new("ComputeNodeSample")
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 0.9
    cap_loop = tree.nodes.new("ComputeNodeCapture")
    cap_loop.width = cap_loop.height = 64
    tree.links.new(repeat_in.outputs[0], sample.inputs['Grid'])
    tree.links.new(sample.outputs[0], math.inputs[0])
    tree.links.new(math.outputs[0], cap_loop.inputs[0])
    tree.links.new(cap_loop.outputs[0], repeat_out.inputs[0])
    
    # Output
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(repeat_out.outputs[0], out.inputs[0])
    return validate_tree(tree, "T5: Repeat w/ Grids")

def test6_nested_repeats():
    """T6: Nested repeat zones"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test6", "ComputeNodeTree")
    
    # Outer repeat
    rep_outer_in = tree.nodes.new("ComputeNodeRepeatInput")
    rep_outer_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(rep_outer_in, rep_outer_out)  # Pair before connections
    rep_outer_in.iterations = 3
    
    # Inner repeat
    rep_inner_in = tree.nodes.new("ComputeNodeRepeatInput")
    rep_inner_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(rep_inner_in, rep_inner_out)  # Pair before connections
    rep_inner_in.iterations = 2
    
    # Math nodes
    math_inner = tree.nodes.new("ComputeNodeMath")
    math_inner.operation = 'ADD'
    math_inner.inputs[1].default_value = 0.1
    math_outer = tree.nodes.new("ComputeNodeMath")
    math_outer.operation = 'MUL'
    math_outer.inputs[1].default_value = 1.1
    
    # Connect
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    tree.links.new(sep.outputs['X'], rep_outer_in.inputs[0])
    tree.links.new(rep_outer_in.outputs[0], rep_inner_in.inputs[0])
    tree.links.new(rep_inner_in.outputs[0], math_inner.inputs[0])
    tree.links.new(math_inner.outputs[0], rep_inner_out.inputs[0])
    tree.links.new(rep_inner_out.outputs[0], math_outer.inputs[0])
    tree.links.new(math_outer.outputs[0], rep_outer_out.inputs[0])
    
    # Output
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(rep_outer_out.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T6: Nested Repeats")

def test7_group_inside_repeat():
    """T7: Node group used inside repeat zone"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Group: x * 2
    group = bpy.data.node_groups.new("MultiplyTwo", "ComputeNodeTree")
    gin = group.nodes.new("ComputeNodeGroupInput")
    gout = group.nodes.new("ComputeNodeGroupOutput")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    math.inputs[1].default_value = 2.0
    group.links.new(gin.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], gout.inputs[0])
    
    # Main with repeat
    tree = bpy.data.node_groups.new("Test7", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(repeat_in, repeat_out)  # Pair before connections
    repeat_in.iterations = 4
    
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = group
    
    tree.links.new(sep.outputs['X'], repeat_in.inputs[0])
    tree.links.new(repeat_in.outputs[0], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], repeat_out.inputs[0])
    
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(repeat_out.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T7: Group in Repeat")

def test8_repeat_inside_group():
    """T8: Repeat zone inside node group"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Group with repeat inside
    group = bpy.data.node_groups.new("GroupWithRepeat", "ComputeNodeTree")
    gin = group.nodes.new("ComputeNodeGroupInput")
    gout = group.nodes.new("ComputeNodeGroupOutput")
    repeat_in = group.nodes.new("ComputeNodeRepeatInput")
    repeat_out = group.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(repeat_in, repeat_out)  # Pair before connections
    repeat_in.iterations = 3
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 0.2
    group.links.new(gin.outputs[0], repeat_in.inputs[0])
    group.links.new(repeat_in.outputs[0], math.inputs[0])
    group.links.new(math.outputs[0], repeat_out.inputs[0])
    group.links.new(repeat_out.outputs[0], gout.inputs[0])
    
    # Main
    tree = bpy.data.node_groups.new("Test8", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = group
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(sep.outputs['X'], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T8: Repeat in Group")

def test9_repeat_group_repeat():
    """T9: Extreme nesting: Repeat → Group → Repeat"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Inner group with repeat
    inner_group = bpy.data.node_groups.new("InnerGroupRepeat", "ComputeNodeTree")
    ig_in = inner_group.nodes.new("ComputeNodeGroupInput")
    ig_out = inner_group.nodes.new("ComputeNodeGroupOutput")
    ig_rep_in = inner_group.nodes.new("ComputeNodeRepeatInput")
    ig_rep_out = inner_group.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(ig_rep_in, ig_rep_out)  # Pair before connections
    ig_rep_in.iterations = 2
    ig_math = inner_group.nodes.new("ComputeNodeMath")
    ig_math.operation = 'MUL'
    ig_math.inputs[1].default_value = 1.1
    inner_group.links.new(ig_in.outputs[0], ig_rep_in.inputs[0])
    inner_group.links.new(ig_rep_in.outputs[0], ig_math.inputs[0])
    inner_group.links.new(ig_math.outputs[0], ig_rep_out.inputs[0])
    inner_group.links.new(ig_rep_out.outputs[0], ig_out.inputs[0])
    
    # Main with outer repeat
    tree = bpy.data.node_groups.new("Test9", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    outer_rep_in = tree.nodes.new("ComputeNodeRepeatInput")
    outer_rep_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(outer_rep_in, outer_rep_out)  # Pair before connections
    outer_rep_in.iterations = 3
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = inner_group
    tree.links.new(sep.outputs['X'], outer_rep_in.inputs[0])
    tree.links.new(outer_rep_in.outputs[0], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], outer_rep_out.inputs[0])
    
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(outer_rep_out.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T9: Repeat→Group→Repeat")

def test10_multi_resolution():
    """T10: Multiple different grid resolutions in same tree"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test10", "ComputeNodeTree")
    
    # Create three different resolution grids
    wn1 = tree.nodes.new("ComputeNodeWhiteNoise")
    cap1 = tree.nodes.new("ComputeNodeCapture")
    cap1.width = cap1.height = 128
    tree.links.new(wn1.outputs['Value'], cap1.inputs[0])
    
    wn2 = tree.nodes.new("ComputeNodeWhiteNoise")
    cap2 = tree.nodes.new("ComputeNodeCapture")
    cap2.width = cap2.height = 64
    tree.links.new(wn2.outputs['Value'], cap2.inputs[0])
    
    wn3 = tree.nodes.new("ComputeNodeWhiteNoise")
    cap3 = tree.nodes.new("ComputeNodeCapture")
    cap3.width = cap3.height = 32
    tree.links.new(wn3.outputs['Value'], cap3.inputs[0])
    
    # Sample all three and mix
    samp1 = tree.nodes.new("ComputeNodeSample")
    samp2 = tree.nodes.new("ComputeNodeSample")
    samp3 = tree.nodes.new("ComputeNodeSample")
    tree.links.new(cap1.outputs[0], samp1.inputs['Grid'])
    tree.links.new(cap2.outputs[0], samp2.inputs['Grid'])
    tree.links.new(cap3.outputs[0], samp3.inputs['Grid'])
    
    mix1 = tree.nodes.new("ComputeNodeMix")
    mix1.data_type = 'FLOAT'
    mix1.inputs['Factor'].default_value = 0.5
    mix2 = tree.nodes.new("ComputeNodeMix")
    mix2.data_type = 'FLOAT'
    mix2.inputs['Factor'].default_value = 0.5
    tree.links.new(samp1.outputs[0], mix1.inputs['A'])
    tree.links.new(samp2.outputs[0], mix1.inputs['B'])
    tree.links.new(mix1.outputs['Result'], mix2.inputs['A'])
    tree.links.new(samp3.outputs[0], mix2.inputs['B'])
    
    cap_final = tree.nodes.new("ComputeNodeCapture")
    cap_final.width = cap_final.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(mix2.outputs['Result'], cap_final.inputs[0])
    tree.links.new(cap_final.outputs[0], out.inputs[0])
    return validate_tree(tree, "T10: Multi-Resolution")

def test11_resolution_cascade():
    """T11: Resolution cascade: high → low → high"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test11", "ComputeNodeTree")
    
    # High res
    wn = tree.nodes.new("ComputeNodeWhiteNoise")
    cap_high1 = tree.nodes.new("ComputeNodeCapture")
    cap_high1.width = cap_high1.height = 256
    tree.links.new(wn.outputs['Value'], cap_high1.inputs[0])
    
    # Downsample
    samp1 = tree.nodes.new("ComputeNodeSample")
    tree.links.new(cap_high1.outputs[0], samp1.inputs['Grid'])
    cap_low = tree.nodes.new("ComputeNodeCapture")
    cap_low.width = cap_low.height = 32
    tree.links.new(samp1.outputs[0], cap_low.inputs[0])
    
    # Upsample
    samp2 = tree.nodes.new("ComputeNodeSample")
    tree.links.new(cap_low.outputs[0], samp2.inputs['Grid'])
    cap_high2 = tree.nodes.new("ComputeNodeCapture")
    cap_high2.width = cap_high2.height = 128
    tree.links.new(samp2.outputs[0], cap_high2.inputs[0])
    
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(cap_high2.outputs[0], out.inputs[0])
    return validate_tree(tree, "T11: Res Cascade (256→32→128)")

def test12_deeply_nested_groups():
    """T12: 5+ levels of nested node groups"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Build 5 levels
    current_group = None
    for level in range(5, 0, -1):
        group = bpy.data.node_groups.new(f"Level{level}", "ComputeNodeTree")
        gin = group.nodes.new("ComputeNodeGroupInput")
        gout = group.nodes.new("ComputeNodeGroupOutput")
        
        if current_group:
            nested = group.nodes.new("ComputeNodeGroup")
            nested.node_tree = current_group
            group.links.new(gin.outputs[0], nested.inputs[0])
            math = group.nodes.new("ComputeNodeMath")
            math.operation = 'ADD'
            math.inputs[1].default_value = 0.1
            group.links.new(nested.outputs[0], math.inputs[0])
            group.links.new(math.outputs[0], gout.inputs[0])
        else:
            math = group.nodes.new("ComputeNodeMath")
            math.operation = 'MUL'
            math.inputs[1].default_value = 2.0
            group.links.new(gin.outputs[0], math.inputs[0])
            group.links.new(math.outputs[0], gout.inputs[0])
        
        current_group = group
    
    # Main tree
    tree = bpy.data.node_groups.new("Test12", "ComputeNodeTree")
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    gmain = tree.nodes.new("ComputeNodeGroup")
    gmain.node_tree = current_group
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(sep.outputs['X'], gmain.inputs[0])
    tree.links.new(gmain.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T12: Deep Nesting (5 levels)")

def test13_3d_grid():
    """T13: 3D grid operations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test13", "ComputeNodeTree")
    
    # 3D white noise → 3D capture
    wn = tree.nodes.new("ComputeNodeWhiteNoise")
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = cap.depth = 32
    
    # Sample and output (will output 2D slice)
    samp = tree.nodes.new("ComputeNodeSample")
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    
    tree.links.new(wn.outputs['Value'], cap.inputs[0])
    tree.links.new(cap.outputs[0], samp.inputs['Grid'])
    tree.links.new(samp.outputs[0], out.inputs[0])
    return validate_tree(tree, "T13: 3D Grid")

def test14_zero_iterations():
    """T14: Edge case - Repeat with zero iterations"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    tree = bpy.data.node_groups.new("Test14", "ComputeNodeTree")
    
    pos = tree.nodes.new("ComputeNodePosition")
    sep = tree.nodes.new("ComputeNodeSeparateXYZ")
    tree.links.new(pos.outputs['Coordinate'], sep.inputs[0])
    
    repeat_in = tree.nodes.new("ComputeNodeRepeatInput")
    repeat_out = tree.nodes.new("ComputeNodeRepeatOutput")
    pair_repeat_nodes(repeat_in, repeat_out)  # Pair before connections
    repeat_in.iterations = 0  # Zero iterations!
    
    math = tree.nodes.new("ComputeNodeMath")
    math.operation = 'ADD'
    math.inputs[1].default_value = 1.0
    
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.width = cap.height = 64
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    
    tree.links.new(sep.outputs['X'], repeat_in.inputs[0])
    tree.links.new(repeat_in.outputs[0], math.inputs[0])
    tree.links.new(math.outputs[0], repeat_out.inputs[0])
    tree.links.new(repeat_out.outputs[0], cap.inputs[0])
    tree.links.new(cap.outputs[0], out.inputs[0])
    return validate_tree(tree, "T14: Zero Iterations")

def test15_group_multipass():
    """T15: Node group with multiple internal GPU passes"""
    bpy.ops.wm.read_homefile(use_empty=True)
    
    # Group with grid operations (creates passes)
    group = bpy.data.node_groups.new("MultiPassGroup", "ComputeNodeTree")
    gin = group.nodes.new("ComputeNodeGroupInput")
    gout = group.nodes.new("ComputeNodeGroupOutput")
    
    # Pass 1: WhiteNoise → Capture
    wn = group.nodes.new("ComputeNodeWhiteNoise")
    cap1 = group.nodes.new("ComputeNodeCapture")
    cap1.width = cap1.height = 64
    group.links.new(wn.outputs['Value'], cap1.inputs[0])
    
    # Pass 2: Sample → Math → Capture
    samp = group.nodes.new("ComputeNodeSample")
    math = group.nodes.new("ComputeNodeMath")
    math.operation = 'MUL'
    cap2 = group.nodes.new("ComputeNodeCapture")
    cap2.width = cap2.height = 64
    group.links.new(cap1.outputs[0], samp.inputs['Grid'])
    group.links.new(samp.outputs[0], math.inputs[0])
    group.links.new(gin.outputs[0], math.inputs[1])
    group.links.new(math.outputs[0], cap2.inputs[0])
    group.links.new(cap2.outputs[0], gout.inputs[0])
    
    # Main
    tree = bpy.data.node_groups.new("Test15", "ComputeNodeTree")
    val = tree.nodes.new("ComputeNodeValue")
    val.outputs[0].default_value = 0.5
    gnode = tree.nodes.new("ComputeNodeGroup")
    gnode.node_tree = group
    out = tree.nodes.new("ComputeNodeOutputImage")
    out.target = mk_img()
    tree.links.new(val.outputs[0], gnode.inputs[0])
    tree.links.new(gnode.outputs[0], out.inputs[0])
    return validate_tree(tree, "T15: Group Multi-Pass")

# ============================================================================
# TEST RUNNER
# ============================================================================

def run_all_tests():
    """Execute all  15 comprehensive stress tests."""
    tests = [
        test1_simple_nodegroup,
        test2_nested_nodegroups,
        test3_nodegroup_with_grid_ops,
        test4_basic_repeat,
        test5_repeat_with_grid_ops,
        test6_nested_repeats,
        test7_group_inside_repeat,
        test8_repeat_inside_group,
        test9_repeat_group_repeat,
        test10_multi_resolution,
        test11_resolution_cascade,
        test12_deeply_nested_groups,
        test13_3d_grid,
        test14_zero_iterations,
        test15_group_multipass,
    ]
    
    print("\n" + "█" * 60)
    print("COMPUTE NODES - COMPREHENSIVE STRESS TEST SUITE")
    print("█" * 60)
    print(f"Running {len(tests)} tests...")
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n✗ CRITICAL ERROR in {test_func.__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    # Final report
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Total Tests:  {len(tests)}")
    print(f"✓ Passed:     {len(successes)}")
    print(f"✗ Failed:     {len(fails)}")
    print(f"⚠ Warnings:   {len(warnings)}")
    
    if successes:
        print(f"\n✓ PASSED TESTS ({len(successes)}):")
        for s in successes:
            print(f"  • {s}")
    
    if fails:
        print(f"\n✗ FAILED TESTS ({len(fails)}):")
        for f in fails:
            print(f"  • {f}")
    
    if warnings:
        print(f"\n⚠ WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  • {w}")
    
    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_all_tests()
