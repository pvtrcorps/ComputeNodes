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
        # Proceeding anyway as it might be partial

    from compute_nodes.graph_extract import extract_graph
    from compute_nodes.planner.scheduler import schedule_passes
    from compute_nodes.codegen.glsl import ShaderGenerator
    from compute_nodes.runtime.shaders import ShaderManager
    
    # Return modules/classes needed
    return extract_graph, schedule_passes, ShaderGenerator, ShaderManager

# Execute Setup ONCE
extract_graph, schedule_passes, ShaderGenerator, ShaderManager = setup_addon()

def test_config(node_type, props):
    # Setup clean state
    bpy.ops.wm.read_homefile(use_empty=True)
    tree = bpy.data.node_groups.new("Test", "ComputeNodeTree")
    node = tree.nodes.new(node_type)
    
    # Set properties
    name_parts = [node_type]
    for k, v in props.items():
        setattr(node, k, v)
        name_parts.append(f"{k}={v}")
    
    name_str = ", ".join(name_parts)
    print(f"Testing: {name_str}...")
    
    try:
        # Setup graph topology
        out = tree.nodes.new("ComputeNodeOutput")
        
        # Pick a valid output to connect (usually 'Color' or 'Fac' or 'Distance')
        # Voronoi: Distance, Color. Noise: Fac, Color. WhiteNoise: Value, Color.
        out_sock = node.outputs[0] # Default to first output
        if 'Color' in node.outputs:
             out_sock = node.outputs['Color']
        
        tree.links.new(out_sock, out.inputs[0])
        
        # Create Dummy Image for Output
        if "TestImg" not in bpy.data.images:
            bpy.data.images.new("TestImg", 64, 64)
        out.target = bpy.data.images["TestImg"]
        
        # Determine output socket type for validation (not strictly needed for glsl gen check but good for graph extract)
        # out.inputs[0].type is ignored by Blender usually, it adapts.
        
        # 1. Extract
        graph = extract_graph(tree)
        
        # 2. Schedule
        passes = schedule_passes(graph)
        
        if not passes:
             print(f"SKIP: {name_str} (No passes generated)")
             return

        # 3. Generate & Compile
        gen = ShaderGenerator(tree)
        shader_mgr = ShaderManager()
        
        for p in passes:
             src = gen.generate(p)
             try:
                 # Compile check
                 shader_mgr.get_shader(src, graph.resources)
             except Exception as e:
                 fails.append(f"{name_str} [GLSL]: {e}")
                 print(f"FAIL [GLSL]: {name_str}")
                 # print(src) # Uncomment to debug source
        
    except Exception as e:
        fails.append(f"{name_str} [PYTHON]: {e}")
        print(f"FAIL [PYTHON]: {name_str} - {e}")
        import traceback
        traceback.print_exc()

# --- RUN CONFIGURATIONS ---

# 1. Voronoi Texture
dims = ['1D', '2D', '3D', '4D']
feats = ['F1', 'F2', 'SMOOTH_F1', 'DISTANCE_TO_EDGE', 'N_SPHERE_RADIUS']
# Metrics only relevant for F1/F2/Smooth? DistanceToEdge might use it? Check node.
# We test all, shader logic should handle valid combinations.
metrics = ['EUCLIDEAN', 'MANHATTAN', 'CHEBYCHEV', 'MINKOWSKI']

for d in dims:
    for f in feats:
        for m in metrics:
            # Skip invalid combos if known? No, test strictness.
            test_config('ComputeNodeVoronoiTexture', {'dimensions': d, 'feature': f, 'metric': m})

# 2. Noise Texture
for d in dims:
    test_config('ComputeNodeNoiseTexture', {'dimensions': d, 'normalize': True})
    test_config('ComputeNodeNoiseTexture', {'dimensions': d, 'normalize': False})

# 3. White Noise
for d in dims:
    test_config('ComputeNodeWhiteNoise', {'dimensions': d})

# 4. Math Node
math_ops = [
    'ADD', 'SUB', 'MUL', 'DIV', 'MULTIPLY_ADD', 
    'SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN', 'ATAN2', 
    'SINH', 'COSH', 'TANH', 
    'POW', 'LOG', 'SQRT', 'INVERSE_SQRT', 'EXP', 
    'MIN', 'MAX', 'LESS_THAN', 'GREATER_THAN', 'SIGN', 'COMPARE', 
    'SMOOTH_MIN', 'SMOOTH_MAX', 
    'ROUND', 'FLOOR', 'CEIL', 'TRUNC', 'FRACT', 
    'MODULO', 'WRAP', 'SNAP', 'PINGPONG', 'ABS', 'RADIANS', 'DEGREES'
]
for op in math_ops:
    test_config('ComputeNodeMath', {'operation': op})

# 5. Vector Math Node
vec_ops = [
    'ADD', 'SUB', 'MUL', 'DIV', 'MULTIPLY_ADD', 
    'CROSS', 'PROJECT', 'REFLECT', 'REFRACT', 'FACEFORWARD', 
    'DOT', 'DISTANCE', 'LENGTH', 'SCALE', 'NORMALIZE', 
    'ABS', 'MIN', 'MAX', 'FLOOR', 'CEIL', 'FRACT', 'MODULO', 
    'WRAP', 'SNAP', 'SINE', 'COSINE', 'TANGENT'
]
for op in vec_ops:
    test_config('ComputeNodeVectorMath', {'operation': op})

# 6. Converter Nodes
# Separate/Combine XYZ
test_config('ComputeNodeSeparateXYZ', {})
test_config('ComputeNodeCombineXYZ', {})

# Separate/Combine Color (all modes)
for mode in ['RGB', 'HSV', 'HSL']:
    test_config('ComputeNodeSeparateColor', {'mode': mode})
    test_config('ComputeNodeCombineColor', {'mode': mode})

# Map Range (all interpolation types and data types)
for dtype in ['FLOAT', 'FLOAT_VECTOR']:
    for interp in ['LINEAR', 'STEPPED', 'SMOOTHSTEP', 'SMOOTHERSTEP']:
        test_config('ComputeNodeMapRange', {'data_type': dtype, 'interpolation_type': interp})

# Clamp (all modes)
for mode in ['MINMAX', 'RANGE']:
    test_config('ComputeNodeClamp', {'clamp_type': mode})

# --- REPORT ---
print("\n" + "="*40)
print(f"STRESS TEST COMPLETE. Failures: {len(fails)}")
for f in fails:
    print(f" - {f}")
print("="*40 + "\n")
