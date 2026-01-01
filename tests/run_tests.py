
import unittest
import sys
import os

# Add the addon directory to path so we can import modules if needed
# (Though usually Blender adds the addon path if installed, or we are running from source)
addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if addon_dir not in sys.path:
    sys.path.append(addon_dir)

def run_all_tests():
    print("========================================")
    print("Running Compute Nodes Tests in Blender")
    print("========================================")
    
    # Discover tests in the 'tests' directory
    loader = unittest.TestLoader()
    start_dir = os.path.join(addon_dir, 'tests')
    
    # We want to run:
    # 1. test_codegen.py
    # 2. test_graph_extraction.py
    # 3. test_edge_cases.py
    # 4. test_runtime.py (if compatible)
    
    suite = loader.discover(start_dir, pattern='test_*.py')
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        sys.exit(1)
    
    print("All tests passed!")

if __name__ == "__main__":
    run_all_tests()
