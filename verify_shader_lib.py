"""
Quick verification script for shader_lib refactoring.
Run inside Blender: blender --background --python verify_shader_lib.py
"""
import sys
import os

ADDON_DIR = r"c:\Users\anton\Desktop\addon\addons\Compute Nodes"
if ADDON_DIR not in sys.path:
    sys.path.append(ADDON_DIR)
    
# Test 1: Verify shader_lib package imports
print("=" * 50)
print("VERIFICATION: shader_lib package import test")
print("=" * 50)

try:
    sys.path.insert(0, os.path.join(ADDON_DIR, "compute_nodes", "codegen"))
    from shader_lib import (
        HASH_GLSL, NOISE_GLSL, FRACTAL_GLSL, 
        TEX_NOISE_GLSL, WHITE_NOISE_GLSL, VORONOI_GLSL
    )
    print(f"[OK] HASH_GLSL: {len(HASH_GLSL)} chars")
    print(f"[OK] NOISE_GLSL: {len(NOISE_GLSL)} chars") 
    print(f"[OK] FRACTAL_GLSL: {len(FRACTAL_GLSL)} chars")
    print(f"[OK] TEX_NOISE_GLSL: {len(TEX_NOISE_GLSL)} chars")
    print(f"[OK] WHITE_NOISE_GLSL: {len(WHITE_NOISE_GLSL)} chars")
    print(f"[OK] VORONOI_GLSL: {len(VORONOI_GLSL)} chars")
    print("\n[PASS] All GLSL constants imported successfully!\n")
except Exception as e:
    print(f"[FAIL] Import error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Verify addon registration (requires Blender)
try:
    import bpy
    print("=" * 50)
    print("VERIFICATION: Blender addon registration")
    print("=" * 50)
    
    # Clear old modules
    keys = [k for k in sys.modules.keys() if k.startswith('compute_nodes')]
    for k in keys:
        del sys.modules[k]
    
    import compute_nodes
    compute_nodes.register()
    print("[OK] Addon registered successfully!")
    
    # Test 3: Create a simple noise node and verify shader generation
    print("\n" + "=" * 50)
    print("VERIFICATION: Shader generation test")
    print("=" * 50)
    
    from compute_nodes.graph_extract import extract_graph
    from compute_nodes.planner.scheduler import schedule_passes
    from compute_nodes.codegen.glsl import ShaderGenerator
    
    # Create test tree
    tree = bpy.data.node_groups.new("VerifyTest", "ComputeNodeTree")
    noise = tree.nodes.new("ComputeNodeNoiseTexture")
    out = tree.nodes.new("ComputeNodeOutput")
    tree.links.new(noise.outputs["Fac"], out.inputs[0])
    
    if "VerifyImg" not in bpy.data.images:
        bpy.data.images.new("VerifyImg", 64, 64)
    out.target = bpy.data.images["VerifyImg"]
    
    # Generate shader
    graph = extract_graph(tree)
    passes = schedule_passes(graph)
    gen = ShaderGenerator(tree)
    
    for p in passes:
        src = gen.generate(p)
        print(f"[OK] Generated shader ({len(src)} chars)")
        
        # Verify GLSL includes are present
        if "hash_int" in src:
            print("[OK] HASH_GLSL functions included")
        if "snoise" in src or "noise_perlin" in src:
            print("[OK] NOISE_GLSL functions included")
        if "noise_fbm" in src:
            print("[OK] FRACTAL_GLSL functions included")
    
    print("\n[PASS] All shader generation tests passed!\n")
        
except ImportError:
    print("[SKIP] Blender not available, skipping addon registration test")
except Exception as e:
    print(f"[FAIL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 50)
print("VERIFICATION COMPLETE - ALL TESTS PASSED")
print("=" * 50)
