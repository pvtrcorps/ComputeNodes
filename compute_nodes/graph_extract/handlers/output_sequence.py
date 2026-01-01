# Output Sequence Handler - Grid3D to Z-slice sequence
# Handles: ComputeNodeOutputSequence

from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_output_sequence(node, ctx):
    """
    Handle ComputeNodeOutputSequence node.
    """
    builder = ctx.builder
    
    import logging
    logger = logging.getLogger(__name__)
    
    # Get properties from node
    base_name = node.base_name
    directory = node.directory
    format_type = node.format
    padding = node.padding
    start_index = node.start_index
    color_depth = node.color_depth
    
    # Get input data using NodeContext
    val_data = ctx.get_input(0)  # "Grid" socket
    
    if val_data is None:
        logger.warning(f"Output Sequence '{node.name}': No grid connected")
        return None
    
    # VALIDATE: Input must be a GRID (HANDLE)
    if val_data.type != DataType.HANDLE:
        raise TypeError(
            f"Output Sequence '{node.name}' requires a Grid input.\n"
            f"Got: {val_data.type.name} (Field)\n"
            f"Solution: Insert a Capture node before Output Sequence."
        )
    
    # Find source resource to get dimensions
    source_resource = None
    if val_data.resource_index is not None:
        source_resource = builder.graph.resources[val_data.resource_index]
    
    if source_resource is None:
        raise ValueError(f"Output Sequence '{node.name}': Could not find input resource")
    
    # VALIDATE: Must be 3D grid
    dims = getattr(source_resource, 'dimensions', 2)
    if dims != 3:
        raise TypeError(
            f"Output Sequence '{node.name}' requires a Grid3D input.\n"
            f"Got: Grid{dims}D\n"
            f"Solution: Use Capture with Dimensions='3D'."
        )
    
    # Get 3D dimensions
    grid_width = source_resource.size[0]
    grid_height = source_resource.size[1]
    grid_depth = source_resource.size[2]
    
    logger.info(f"Output Sequence: {grid_width}x{grid_height}x{grid_depth} -> {grid_depth} slices")
    
    # Build the filename pattern for executor
    ext_map = {'PNG': 'png', 'TIFF': 'tif', 'OPEN_EXR': 'exr'}
    ext = ext_map.get(format_type, 'exr')
    filename_pattern = f"{base_name}{{:0{padding}d}}.{ext}"
    
    # Store sequence info in the graph for executor to use
    sequence_info = {
        'type': 'sequence_output',
        'source_resource_idx': val_data.resource_index,
        'directory': directory,
        'filename_pattern': filename_pattern,
        'format': format_type,
        'depth': grid_depth,
        'width': grid_width,
        'height': grid_height,
        'start_index': start_index,
        'color_depth': color_depth,
    }
    
    # Store in graph metadata (we'll add this capability)
    if not hasattr(builder.graph, 'sequence_outputs'):
        builder.graph.sequence_outputs = []
    builder.graph.sequence_outputs.append(sequence_info)
    
    return val_data  # Return the input - nothing to generate in shader
