# Compute Nodes Examples

This folder contains example scripts and node groups for the Compute Nodes addon.

## Contents

### erosion/

Advanced terrain erosion system that creates node groups for physically-based terrain simulation:

- **erosion_advanced.py** - Main erosion system with FD8/MFD multi-flow, thermal erosion, hydraulic erosion
- **setup_erosion_nodes.py** - Quick setup script for creating erosion node groups

## Usage

These scripts can be run from Blender's Text Editor to generate pre-built node groups:

```python
import importlib.util
spec = importlib.util.spec_from_file_location("erosion", "/path/to/erosion_advanced.py")
erosion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(erosion)
erosion.setup_all()
```

**Note**: These are example scripts, not part of the core addon. They depend on the Compute Nodes addon being installed and enabled.
