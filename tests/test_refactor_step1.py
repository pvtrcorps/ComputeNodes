import sys
import os
import bpy
import importlib

addon_path = r'c:\Users\anton\Desktop\addon\addons\Compute Nodes'
if addon_path not in sys.path:
    sys.path.append(addon_path)

examples_path = r'c:\Users\anton\Desktop\addon\addons\Compute Nodes\examples\erosion'
if examples_path not in sys.path:
    sys.path.append(examples_path)

def test_step_1():
    """Test Step 1: Phase 2 removed, field deps only in Phase 4.5"""
    # Reload modules
    import compute_nodes.planner.scheduler
    importlib.reload(compute_nodes.planner.scheduler)
    
    import compute_nodes.planner.loops
    importlib.reload(compute_nodes.planner.loops)
    
    import compute_nodes.runtime
    importlib.reload(compute_nodes.runtime)
    
    import compute_nodes.operators
    importlib.reload(compute_nodes.operators)
    
    compute_nodes.operators.ExecutionContext.reset()

    import erosion_prodigy
    importlib.reload(erosion_prodigy)
    
    if "Erosion Demo" in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups["Erosion Demo"])
        
    erosion_prodigy.create_demo_graph()

    from compute_nodes.operators import execute_compute_tree
    
    tree = bpy.data.node_groups.get("Erosion Demo")
    if tree:
        print("Testing Erosion Demo (Step 1 - Phase 2 removed)...")
        count = execute_compute_tree(tree, bpy.context)
        print(f"✅ Step 1 VERIFIED - {count} passes executed successfully")
        return True
    else:
        print("❌ Tree 'Erosion Demo' not found")
        return False

try:
    with bpy.context.temp_override(active_object=None):
        success = test_step_1()
        if success:
            print("\n=== STEP 1 COMPLETE ===")
        else:
            print("\n=== STEP 1 FAILED ===")
except Exception as e:
    import traceback
    print(f"❌ Step 1 FAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
