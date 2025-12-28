import bpy
import sys
import os

# Add addon root to path to import setup script
addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

import setup_erosion_nodes

def test_generation():
    print("=== Testing Erosion Node Generation ===")
    
    # Run generation
    setup_erosion_nodes.main()
    
    # Assertions
    expected_groups = [
        "Compute Texel Size",
        "Compute Gradient",
        "Compute Advection",
        "Compute Flow Velocity",
        "Compute Erosion Deposition"
    ]
    
    for name in expected_groups:
        if name not in bpy.data.node_groups:
            print(f"FAILED: Group '{name}' not found!")
            return False
            
        group = bpy.data.node_groups[name]
        print(f"PASSED: Group '{name}' created with {len(group.nodes)} nodes.")
        
        # Validation of interface
        if len(group.interface.items_tree) == 0:
             print(f"WARNING: Group '{name}' has no interface items!")
             
    print("=== All Tests Passed ===")
    return True

if __name__ == "__main__":
    success = test_generation()
    sys.exit(0 if success else 1)
