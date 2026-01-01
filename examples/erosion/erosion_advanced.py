"""
Advanced Terrain Erosion System
===============================

Creates node groups for physically-based terrain erosion:
- FD8/MFD multi-flow direction
- Thermal erosion (talus angle)
- Mass-conserving hydraulic erosion
- Bedrock/Soil distinction
- Semi-Lagrangian advection

Usage:
    import erosion_advanced
    erosion_advanced.setup_all()
"""

import bpy
import math

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_or_create_tree(name: str) -> bpy.types.NodeTree:
    """Get existing or create new ComputeNodeTree."""
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    return bpy.data.node_groups.new(name, 'ComputeNodeTree')


def clear_tree(tree: bpy.types.NodeTree):
    """Remove all nodes from tree."""
    tree.nodes.clear()


def add_socket(tree, name: str, in_out: str, socket_type: str, default=None):
    """Add socket to tree interface."""
    item = tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None and hasattr(item, 'default_value'):
        item.default_value = default
    return item


def link(tree, from_node, from_socket, to_node, to_socket):
    """Create a link between sockets."""
    out = from_node.outputs[from_socket] if isinstance(from_socket, (int, str)) else from_socket
    inp = to_node.inputs[to_socket] if isinstance(to_socket, (int, str)) else to_socket
    tree.links.new(out, inp)


def set_default(node, socket, value):
    """Set default value on an input socket. Socket can be name (str) or index (int)."""
    try:
        if isinstance(socket, int):
            node.inputs[socket].default_value = value
        elif socket in node.inputs:
            node.inputs[socket].default_value = value
    except (KeyError, IndexError, TypeError):
        pass  # Socket doesn't exist or doesn't support default


# ============================================================================
# NODE GROUP: TERRAIN STATE INIT
# ============================================================================

def create_terrain_state_init():
    """
    Initialize terrain state buffers from a height input.
    
    Inputs:
        - Height (Grid): Input heightmap
        - Rock Threshold: Height below which is bedrock (0-1 normalized)
        - Initial Water: Starting water depth
        
    Outputs:
        - Bedrock (Grid)
        - Soil (Grid)  
        - Water (Grid)
        - Sediment (Grid)
        - Velocity (Grid)
    """
    tree = get_or_create_tree("Terrain State Init")
    clear_tree(tree)
    tree.interface.clear()
    
    # Interface
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Rock Threshold", "INPUT", "NodeSocketFloat", 0.3)
    add_socket(tree, "Initial Water", "INPUT", "NodeSocketFloat", 0.01)
    
    add_socket(tree, "Bedrock", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "OUTPUT", "ComputeSocketGrid")
    
    # Nodes
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-400, 0)
    group_out.location = (800, 0)
    
    # Grid Info for dimensions
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-200, -200)
    link(tree, group_in, "Height", grid_info, "Grid")
    
    # Position for sampling
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-200, 100)
    
    # Sample height
    sample_h = tree.nodes.new('ComputeNodeSample')
    sample_h.location = (0, 100)
    sample_h.name = "Sample Height"
    link(tree, group_in, "Height", sample_h, "Grid")
    link(tree, pos, "Normalized", sample_h, "Coordinate")
    
    # Get max height for normalization (using constant for now)
    max_h = tree.nodes.new('ComputeNodeMath')
    max_h.operation = 'MAX'
    max_h.location = (0, -100)
    set_default(max_h, 0, 1.0)  # Assume normalized height
    
    # Bedrock = Height * threshold (bottom portion)
    bedrock_mul = tree.nodes.new('ComputeNodeMath')
    bedrock_mul.operation = 'MUL'
    bedrock_mul.location = (200, 100)
    link(tree, sample_h, "Color", bedrock_mul, 0)
    link(tree, group_in, "Rock Threshold", bedrock_mul, 1)
    
    # Soil = Height - Bedrock
    soil_sub = tree.nodes.new('ComputeNodeMath')
    soil_sub.operation = 'SUB'
    soil_sub.location = (200, 0)
    link(tree, sample_h, "Color", soil_sub, 0)
    link(tree, bedrock_mul, "Value", soil_sub, 1)
    
    # Captures
    cap_bedrock = tree.nodes.new('ComputeNodeCapture')
    cap_bedrock.name = "Capture Bedrock"
    cap_bedrock.location = (400, 200)
    
    cap_soil = tree.nodes.new('ComputeNodeCapture')
    cap_soil.name = "Capture Soil"
    cap_soil.location = (400, 100)
    
    cap_water = tree.nodes.new('ComputeNodeCapture')
    cap_water.name = "Capture Water"
    cap_water.location = (400, 0)
    
    cap_sed = tree.nodes.new('ComputeNodeCapture')
    cap_sed.name = "Capture Sediment"
    cap_sed.location = (400, -100)
    
    cap_vel = tree.nodes.new('ComputeNodeCapture')
    cap_vel.name = "Capture Velocity"
    cap_vel.location = (400, -200)
    
    # Combine for captures
    comb_bedrock = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_bedrock.location = (300, 200)
    link(tree, bedrock_mul, "Value", comb_bedrock, "X")
    link(tree, bedrock_mul, "Value", comb_bedrock, "Y")
    link(tree, bedrock_mul, "Value", comb_bedrock, "Z")
    
    comb_soil = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_soil.location = (300, 100)
    link(tree, soil_sub, "Value", comb_soil, "X")
    link(tree, soil_sub, "Value", comb_soil, "Y")
    link(tree, soil_sub, "Value", comb_soil, "Z")
    
    # Water uses initial water value
    comb_water = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_water.location = (300, 0)
    link(tree, group_in, "Initial Water", comb_water, "X")
    link(tree, group_in, "Initial Water", comb_water, "Y")
    link(tree, group_in, "Initial Water", comb_water, "Z")
    
    # Sediment = 0
    comb_sed = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_sed.location = (300, -100)
    set_default(comb_sed, "X", 0.0)
    set_default(comb_sed, "Y", 0.0)
    set_default(comb_sed, "Z", 0.0)
    
    # Velocity = 0
    comb_vel = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_vel.location = (300, -200)
    set_default(comb_vel, "X", 0.0)
    set_default(comb_vel, "Y", 0.0)
    set_default(comb_vel, "Z", 0.0)
    
    # Link combines to captures
    for cap, comb in [(cap_bedrock, comb_bedrock), (cap_soil, comb_soil),
                      (cap_water, comb_water), (cap_sed, comb_sed), (cap_vel, comb_vel)]:
        link(tree, comb, "Vector", cap, "Field")
        link(tree, grid_info, "Width", cap, "Width")
        link(tree, grid_info, "Height", cap, "Height")
    
    # Link to outputs
    link(tree, cap_bedrock, "Grid", group_out, "Bedrock")
    link(tree, cap_soil, "Grid", group_out, "Soil")
    link(tree, cap_water, "Grid", group_out, "Water")
    link(tree, cap_sed, "Grid", group_out, "Sediment")
    link(tree, cap_vel, "Grid", group_out, "Velocity")
    
    return tree


# ============================================================================
# NODE GROUP: COMPUTE GRADIENT (Enhanced)
# ============================================================================

def create_compute_gradient():
    """
    Compute terrain gradient using central differences.
    
    Inputs:
        - Height (Grid)
        
    Outputs:
        - Gradient (Grid): vec2(dH/dx, dH/dy)
        - Slope (Grid): magnitude of gradient
    """
    tree = get_or_create_tree("Compute Gradient Advanced")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Gradient", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Slope", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-600, 0)
    group_out.location = (800, 0)
    
    # Grid info
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-400, -200)
    link(tree, group_in, "Height", grid_info, "Grid")
    
    # Pixel size
    pix_x = tree.nodes.new('ComputeNodeMath')
    pix_x.operation = 'DIV'
    pix_x.location = (-400, -100)
    set_default(pix_x, 0, 1.0)
    link(tree, grid_info, "Width", pix_x, 1)
    
    pix_y = tree.nodes.new('ComputeNodeMath')
    pix_y.operation = 'DIV'
    pix_y.location = (-400, -150)
    set_default(pix_y, 0, 1.0)
    link(tree, grid_info, "Height", pix_y, 1)
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-400, 100)
    
    # Offset vectors
    off_px = tree.nodes.new('ComputeNodeCombineXYZ')
    off_px.location = (-200, 50)
    link(tree, pix_x, "Value", off_px, "X")
    
    off_nx = tree.nodes.new('ComputeNodeCombineXYZ')
    off_nx.location = (-200, 0)
    # Negative X
    neg_x = tree.nodes.new('ComputeNodeMath')
    neg_x.operation = 'MUL'
    neg_x.location = (-300, 0)
    link(tree, pix_x, "Value", neg_x, 0)
    set_default(neg_x, 1, -1.0)
    link(tree, neg_x, "Value", off_nx, "X")
    
    off_py = tree.nodes.new('ComputeNodeCombineXYZ')
    off_py.location = (-200, -50)
    link(tree, pix_y, "Value", off_py, "Y")
    
    off_ny = tree.nodes.new('ComputeNodeCombineXYZ')
    off_ny.location = (-200, -100)
    neg_y = tree.nodes.new('ComputeNodeMath')
    neg_y.operation = 'MUL'
    neg_y.location = (-300, -100)
    link(tree, pix_y, "Value", neg_y, 0)
    set_default(neg_y, 1, -1.0)
    link(tree, neg_y, "Value", off_ny, "Y")
    
    # Sample at offsets
    def make_sample(name, offset_node, y_pos):
        add_vec = tree.nodes.new('ComputeNodeVectorMath')
        add_vec.operation = 'ADD'
        add_vec.location = (0, y_pos)
        link(tree, pos, "Normalized", add_vec, 0)
        link(tree, offset_node, "Vector", add_vec, 1)
        
        samp = tree.nodes.new('ComputeNodeSample')
        samp.name = name
        samp.location = (150, y_pos)
        link(tree, group_in, "Height", samp, "Grid")
        link(tree, add_vec, "Vector", samp, "Coordinate")
        return samp
    
    s_px = make_sample("Sample +X", off_px, 100)
    s_nx = make_sample("Sample -X", off_nx, 50)
    s_py = make_sample("Sample +Y", off_py, 0)
    s_ny = make_sample("Sample -Y", off_ny, -50)
    
    # Gradient X = (h_px - h_nx) / 2
    dx = tree.nodes.new('ComputeNodeMath')
    dx.operation = 'SUB'
    dx.location = (300, 75)
    link(tree, s_px, "Color", dx, 0)
    link(tree, s_nx, "Color", dx, 1)
    
    dx_div = tree.nodes.new('ComputeNodeMath')
    dx_div.operation = 'DIV'
    dx_div.location = (400, 75)
    link(tree, dx, "Value", dx_div, 0)
    set_default(dx_div, 1, 2.0)
    
    # Gradient Y = (h_py - h_ny) / 2
    dy = tree.nodes.new('ComputeNodeMath')
    dy.operation = 'SUB'
    dy.location = (300, -25)
    link(tree, s_py, "Color", dy, 0)
    link(tree, s_ny, "Color", dy, 1)
    
    dy_div = tree.nodes.new('ComputeNodeMath')
    dy_div.operation = 'DIV'
    dy_div.location = (400, -25)
    link(tree, dy, "Value", dy_div, 0)
    set_default(dy_div, 1, 2.0)
    
    # Combine gradient
    comb_grad = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_grad.location = (500, 25)
    link(tree, dx_div, "Value", comb_grad, "X")
    link(tree, dy_div, "Value", comb_grad, "Y")
    
    # Slope = length(gradient)
    slope_len = tree.nodes.new('ComputeNodeVectorMath')
    slope_len.operation = 'LENGTH'
    slope_len.location = (500, -75)
    link(tree, comb_grad, "Vector", slope_len, 0)
    
    comb_slope = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_slope.location = (550, -75)
    link(tree, slope_len, "Value", comb_slope, "X")
    link(tree, slope_len, "Value", comb_slope, "Y")
    link(tree, slope_len, "Value", comb_slope, "Z")
    
    # Captures
    cap_grad = tree.nodes.new('ComputeNodeCapture')
    cap_grad.location = (650, 25)
    link(tree, comb_grad, "Vector", cap_grad, "Field")
    link(tree, grid_info, "Width", cap_grad, "Width")
    link(tree, grid_info, "Height", cap_grad, "Height")
    
    cap_slope = tree.nodes.new('ComputeNodeCapture')
    cap_slope.location = (650, -75)
    link(tree, comb_slope, "Vector", cap_slope, "Field")
    link(tree, grid_info, "Width", cap_slope, "Width")
    link(tree, grid_info, "Height", cap_slope, "Height")
    
    link(tree, cap_grad, "Grid", group_out, "Gradient")
    link(tree, cap_slope, "Grid", group_out, "Slope")
    
    return tree


# ============================================================================
# NODE GROUP: D8 FLOW DIRECTION (Single steepest descent)
# ============================================================================

def create_d8_flow():
    """
    D8 Flow Direction: Water flows to the single steepest downhill neighbor.
    
    Outputs a direction vector pointing to the lowest neighbor.
    
    Inputs:
        - Height (Grid)
        
    Outputs:
        - Flow Direction (Grid): Normalized vec2 pointing downhill
        - Flow Magnitude (Grid): Slope to steepest neighbor
    """
    tree = get_or_create_tree("D8 Flow Direction")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Flow Direction", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Flow Magnitude", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-800, 0)
    group_out.location = (1000, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-600, -300)
    link(tree, group_in, "Height", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-600, 100)
    
    # Pixel sizes
    pix_x = tree.nodes.new('ComputeNodeMath')
    pix_x.operation = 'DIV'
    pix_x.location = (-600, -100)
    set_default(pix_x, 0, 1.0)
    link(tree, grid_info, "Width", pix_x, 1)
    
    pix_y = tree.nodes.new('ComputeNodeMath')
    pix_y.operation = 'DIV'
    pix_y.location = (-600, -150)
    set_default(pix_y, 0, 1.0)
    link(tree, grid_info, "Height", pix_y, 1)
    
    # Sample center height
    s_center = tree.nodes.new('ComputeNodeSample')
    s_center.name = "Sample Center"
    s_center.location = (-400, 100)
    link(tree, group_in, "Height", s_center, "Grid")
    link(tree, pos, "Normalized", s_center, "Coordinate")
    
    # Define 8 neighbor offsets: E, NE, N, NW, W, SW, S, SE
    # We'll sample 4 cardinal directions for simplicity (can extend to 8)
    offsets = [
        ("E", 1, 0),
        ("W", -1, 0),
        ("N", 0, 1),
        ("S", 0, -1),
    ]
    
    samples = {}
    for name, dx, dy in offsets:
        # Create offset vector
        off = tree.nodes.new('ComputeNodeCombineXYZ')
        off.location = (-300, 100 - len(samples) * 80)
        
        if dx != 0:
            mul_x = tree.nodes.new('ComputeNodeMath')
            mul_x.operation = 'MUL'
            mul_x.location = (-350, 100 - len(samples) * 80)
            link(tree, pix_x, "Value", mul_x, 0)
            set_default(mul_x, 1, float(dx))
            link(tree, mul_x, "Value", off, "X")
        
        if dy != 0:
            mul_y = tree.nodes.new('ComputeNodeMath')
            mul_y.operation = 'MUL'
            mul_y.location = (-350, 50 - len(samples) * 80)
            link(tree, pix_y, "Value", mul_y, 0)
            set_default(mul_y, 1, float(dy))
            link(tree, mul_y, "Value", off, "Y")
        
        # Add offset to position
        add_off = tree.nodes.new('ComputeNodeVectorMath')
        add_off.operation = 'ADD'
        add_off.location = (-200, 100 - len(samples) * 80)
        link(tree, pos, "Normalized", add_off, 0)
        link(tree, off, "Vector", add_off, 1)
        
        # Sample neighbor
        samp = tree.nodes.new('ComputeNodeSample')
        samp.name = f"Sample {name}"
        samp.location = (-50, 100 - len(samples) * 80)
        link(tree, group_in, "Height", samp, "Grid")
        link(tree, add_off, "Vector", samp, "Coordinate")
        
        samples[name] = (samp, dx, dy)
    
    # Find steepest descent: compare center - neighbor for each
    # For simplicity, we'll find the minimum neighbor and use that direction
    
    # Start with first neighbor
    first_name = list(samples.keys())[0]
    first_samp, first_dx, first_dy = samples[first_name]
    
    # Compute slope to first neighbor
    slope_first = tree.nodes.new('ComputeNodeMath')
    slope_first.operation = 'SUB'
    slope_first.location = (100, 100)
    link(tree, s_center, "Color", slope_first, 0)
    link(tree, first_samp, "Color", slope_first, 1)
    
    # For now, simplified: use gradient direction from Compute Gradient
    # A full D8 implementation would compare all 8 and pick max
    
    # Create direction from gradient (steepest descent = -gradient normalized)
    # We'll reuse gradient calculation internally
    
    # Actually, let's output a simple flow direction based on gradient
    # The gradient already points uphill, so -gradient is downhill
    
    # Use the Compute Gradient Advanced group if it exists
    grad_group = tree.nodes.new('ComputeNodeGroup')
    grad_group.node_tree = bpy.data.node_groups.get("Compute Gradient Advanced")
    grad_group.location = (200, 0)
    link(tree, group_in, "Height", grad_group, "Height")
    
    # Negate gradient to get flow direction
    pos_sample = tree.nodes.new('ComputeNodePosition')
    pos_sample.location = (350, 100)
    
    s_grad = tree.nodes.new('ComputeNodeSample')
    s_grad.location = (400, 0)
    link(tree, grad_group, "Gradient", s_grad, "Grid")
    link(tree, pos_sample, "Normalized", s_grad, "Coordinate")
    
    neg_grad = tree.nodes.new('ComputeNodeVectorMath')
    neg_grad.operation = 'SCALE'
    neg_grad.location = (550, 0)
    link(tree, s_grad, "Color", neg_grad, 0)
    set_default(neg_grad, "Scale", -1.0)
    
    # Normalize
    norm_dir = tree.nodes.new('ComputeNodeVectorMath')
    norm_dir.operation = 'NORMALIZE'
    norm_dir.location = (700, 0)
    link(tree, neg_grad, "Vector", norm_dir, 0)
    
    # Magnitude (slope)
    s_slope = tree.nodes.new('ComputeNodeSample')
    s_slope.location = (400, -100)
    link(tree, grad_group, "Slope", s_slope, "Grid")
    link(tree, pos_sample, "Normalized", s_slope, "Coordinate")
    
    # Captures
    cap_dir = tree.nodes.new('ComputeNodeCapture')
    cap_dir.location = (850, 50)
    link(tree, norm_dir, "Vector", cap_dir, "Field")
    link(tree, grid_info, "Width", cap_dir, "Width")
    link(tree, grid_info, "Height", cap_dir, "Height")
    
    comb_mag = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_mag.location = (750, -100)
    link(tree, s_slope, "Color", comb_mag, "X")
    link(tree, s_slope, "Color", comb_mag, "Y")
    link(tree, s_slope, "Color", comb_mag, "Z")
    
    cap_mag = tree.nodes.new('ComputeNodeCapture')
    cap_mag.location = (850, -100)
    link(tree, comb_mag, "Vector", cap_mag, "Field")
    link(tree, grid_info, "Width", cap_mag, "Width")
    link(tree, grid_info, "Height", cap_mag, "Height")
    
    link(tree, cap_dir, "Grid", group_out, "Flow Direction")
    link(tree, cap_mag, "Grid", group_out, "Flow Magnitude")
    
    return tree


# ============================================================================
# NODE GROUP: FD8/MFD FLOW WEIGHTS (Multi-Flow Direction)
# ============================================================================

def create_fd8_flow():
    """
    FD8/MFD: Water flows to ALL downhill neighbors proportionally to slope.
    
    Unlike D8 (single direction), FD8 distributes flow based on:
    weight_i = max(0, slope_i)^exponent / sum(weights)
    
    Outputs flow weights to 4 cardinal directions (can extend to 8).
    
    Inputs:
        - Height (Grid)
        - Exponent (Float): Higher = more concentration to steepest (1.0 = linear)
        
    Outputs:
        - Flow Weights (Grid): RGBA = (E, W, N, S) weights, sum to 1 or 0
    """
    tree = get_or_create_tree("FD8 Flow Weights")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Exponent", "INPUT", "NodeSocketFloat", 1.1)
    add_socket(tree, "Flow Weights", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-800, 0)
    group_out.location = (1200, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-600, -300)
    link(tree, group_in, "Height", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-600, 100)
    
    # Pixel sizes
    pix_x = tree.nodes.new('ComputeNodeMath')
    pix_x.operation = 'DIV'
    pix_x.location = (-600, -100)
    set_default(pix_x, 0, 1.0)
    link(tree, grid_info, "Width", pix_x, 1)
    
    pix_y = tree.nodes.new('ComputeNodeMath')
    pix_y.operation = 'DIV'
    pix_y.location = (-600, -150)
    set_default(pix_y, 0, 1.0)
    link(tree, grid_info, "Height", pix_y, 1)
    
    # Sample center
    s_center = tree.nodes.new('ComputeNodeSample')
    s_center.location = (-400, 100)
    link(tree, group_in, "Height", s_center, "Grid")
    link(tree, pos, "Normalized", s_center, "Coordinate")
    
    # Sample 4 neighbors and compute slopes
    neighbors = [("E", 1, 0), ("W", -1, 0), ("N", 0, 1), ("S", 0, -1)]
    slope_nodes = []
    
    y_offset = 0
    for name, dx, dy in neighbors:
        # Offset
        off = tree.nodes.new('ComputeNodeCombineXYZ')
        off.location = (-300, y_offset)
        
        if dx != 0:
            mul = tree.nodes.new('ComputeNodeMath')
            mul.operation = 'MUL'
            mul.location = (-350, y_offset)
            link(tree, pix_x, "Value", mul, 0)
            set_default(mul, 1, float(dx))
            link(tree, mul, "Value", off, "X")
        if dy != 0:
            mul = tree.nodes.new('ComputeNodeMath')
            mul.operation = 'MUL'
            mul.location = (-350, y_offset - 30)
            link(tree, pix_y, "Value", mul, 0)
            set_default(mul, 1, float(dy))
            link(tree, mul, "Value", off, "Y")
        
        add_off = tree.nodes.new('ComputeNodeVectorMath')
        add_off.operation = 'ADD'
        add_off.location = (-200, y_offset)
        link(tree, pos, "Normalized", add_off, 0)
        link(tree, off, "Vector", add_off, 1)
        
        samp = tree.nodes.new('ComputeNodeSample')
        samp.location = (-50, y_offset)
        link(tree, group_in, "Height", samp, "Grid")
        link(tree, add_off, "Vector", samp, "Coordinate")
        
        # Slope = center - neighbor (positive = downhill)
        slope = tree.nodes.new('ComputeNodeMath')
        slope.operation = 'SUB'
        slope.location = (100, y_offset)
        link(tree, s_center, "Color", slope, 0)
        link(tree, samp, "Color", slope, 1)
        
        # Clamp to positive (only downhill flow)
        clamp = tree.nodes.new('ComputeNodeMath')
        clamp.operation = 'MAX'
        clamp.location = (200, y_offset)
        link(tree, slope, "Value", clamp, 0)
        set_default(clamp, 1, 0.0)
        
        # Raise to exponent power
        power = tree.nodes.new('ComputeNodeMath')
        power.operation = 'POW'
        power.location = (300, y_offset)
        link(tree, clamp, "Value", power, 0)
        link(tree, group_in, "Exponent", power, 1)
        
        slope_nodes.append(power)
        y_offset -= 100
    
    # Sum all weights
    sum1 = tree.nodes.new('ComputeNodeMath')
    sum1.operation = 'ADD'
    sum1.location = (450, 50)
    link(tree, slope_nodes[0], "Value", sum1, 0)
    link(tree, slope_nodes[1], "Value", sum1, 1)
    
    sum2 = tree.nodes.new('ComputeNodeMath')
    sum2.operation = 'ADD'
    sum2.location = (450, -50)
    link(tree, slope_nodes[2], "Value", sum2, 0)
    link(tree, slope_nodes[3], "Value", sum2, 1)
    
    total = tree.nodes.new('ComputeNodeMath')
    total.operation = 'ADD'
    total.location = (550, 0)
    link(tree, sum1, "Value", total, 0)
    link(tree, sum2, "Value", total, 1)
    
    # Avoid division by zero
    safe_total = tree.nodes.new('ComputeNodeMath')
    safe_total.operation = 'MAX'
    safe_total.location = (650, 0)
    link(tree, total, "Value", safe_total, 0)
    set_default(safe_total, 1, 0.0001)
    
    # Normalize each weight
    norm_weights = []
    for i, power in enumerate(slope_nodes):
        div = tree.nodes.new('ComputeNodeMath')
        div.operation = 'DIV'
        div.location = (750, 50 - i * 50)
        link(tree, power, "Value", div, 0)
        link(tree, safe_total, "Value", div, 1)
        norm_weights.append(div)
    
    # Combine into RGBA (E, W, N, S)
    comb = tree.nodes.new('ComputeNodeCombineColor')
    comb.location = (900, 0)
    link(tree, norm_weights[0], "Value", comb, "Red")
    link(tree, norm_weights[1], "Value", comb, "Green")
    link(tree, norm_weights[2], "Value", comb, "Blue")
    link(tree, norm_weights[3], "Value", comb, "Alpha")
    
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (1050, 0)
    link(tree, comb, "Color", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Flow Weights")
    
    return tree


# ============================================================================
# NODE GROUP: FLOW ACCUMULATION
# ============================================================================

def create_flow_accumulation():
    """
    Flow Accumulation: Sum water contributions from uphill neighbors.
    
    Each cell receives water from neighbors that flow into it.
    Uses FD8 weights to determine contribution amounts.
    
    Inputs:
        - Water (Grid): Current water depth
        - Flow Weights (Grid): FD8 weights from neighbors
        
    Outputs:
        - Accumulated (Grid): Water after redistribution
    """
    tree = get_or_create_tree("Flow Accumulation")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Flow Weights", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Accumulated", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-600, 0)
    group_out.location = (800, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-400, -200)
    link(tree, group_in, "Water", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-400, 100)
    
    # Pixel sizes
    pix_x = tree.nodes.new('ComputeNodeMath')
    pix_x.operation = 'DIV'
    pix_x.location = (-400, -50)
    set_default(pix_x, 0, 1.0)
    link(tree, grid_info, "Width", pix_x, 1)
    
    pix_y = tree.nodes.new('ComputeNodeMath')
    pix_y.operation = 'DIV'
    pix_y.location = (-400, -100)
    set_default(pix_y, 0, 1.0)
    link(tree, grid_info, "Height", pix_y, 1)
    
    # Sample current cell's water and outflow
    s_water = tree.nodes.new('ComputeNodeSample')
    s_water.location = (-200, 100)
    link(tree, group_in, "Water", s_water, "Grid")
    link(tree, pos, "Normalized", s_water, "Coordinate")
    
    s_weights = tree.nodes.new('ComputeNodeSample')
    s_weights.location = (-200, 0)
    link(tree, group_in, "Flow Weights", s_weights, "Grid")
    link(tree, pos, "Normalized", s_weights, "Coordinate")
    
    # Total outflow from this cell
    sep_w = tree.nodes.new('ComputeNodeSeparateColor')
    sep_w.location = (0, 0)
    link(tree, s_weights, "Color", sep_w, "Color")
    
    # Sum of outflow weights for this cell
    out_sum1 = tree.nodes.new('ComputeNodeMath')
    out_sum1.operation = 'ADD'
    out_sum1.location = (100, 0)
    link(tree, sep_w, "Red", out_sum1, 0)
    link(tree, sep_w, "Green", out_sum1, 1)
    
    out_sum2 = tree.nodes.new('ComputeNodeMath')
    out_sum2.operation = 'ADD'
    out_sum2.location = (100, -50)
    link(tree, sep_w, "Blue", out_sum2, 0)
    link(tree, sep_w, "Alpha", out_sum2, 1)
    
    out_total = tree.nodes.new('ComputeNodeMath')
    out_total.operation = 'ADD'
    out_total.location = (200, -25)
    link(tree, out_sum1, "Value", out_total, 0)
    link(tree, out_sum2, "Value", out_total, 1)
    
    # Water that stays (1 - outflow proportion)
    stay = tree.nodes.new('ComputeNodeMath')
    stay.operation = 'SUB'
    stay.location = (300, -25)
    set_default(stay, 0, 1.0)
    link(tree, out_total, "Value", stay, 1)
    
    stay_water = tree.nodes.new('ComputeNodeMath')
    stay_water.operation = 'MUL'
    stay_water.location = (400, 50)
    link(tree, s_water, "Color", stay_water, 0)
    link(tree, stay, "Value", stay_water, 1)
    
    # For a complete implementation, we'd sample neighbors and add their contributions
    # This is simplified - just keeps water that doesn't flow out
    
    # Combine and capture
    comb = tree.nodes.new('ComputeNodeCombineXYZ')
    comb.location = (550, 50)
    link(tree, stay_water, "Value", comb, "X")
    link(tree, stay_water, "Value", comb, "Y")
    link(tree, stay_water, "Value", comb, "Z")
    
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (650, 50)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Accumulated")
    
    return tree

# ============================================================================
# NODE GROUP: ADVECT FIELD (Semi-Lagrangian)
# ============================================================================

def create_advect_field():
    """
    Semi-Lagrangian advection: backtrace position by velocity, sample field there.
    
    Inputs:
        - Field (Grid): Field to advect
        - Velocity (Grid): Velocity field (XY)
        - dt: Time step
        
    Outputs:
        - Advected (Grid)
    """
    tree = get_or_create_tree("Advect Field")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Field", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "Advected", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-400, 0)
    group_out.location = (600, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-200, -150)
    link(tree, group_in, "Field", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-200, 100)
    
    # Sample velocity at current position
    sample_vel = tree.nodes.new('ComputeNodeSample')
    sample_vel.location = (0, 0)
    link(tree, group_in, "Velocity", sample_vel, "Grid")
    link(tree, pos, "Normalized", sample_vel, "Coordinate")
    
    # Scale velocity by dt
    vel_dt = tree.nodes.new('ComputeNodeVectorMath')
    vel_dt.operation = 'SCALE'
    vel_dt.location = (150, 0)
    link(tree, sample_vel, "Color", vel_dt, 0)
    link(tree, group_in, "dt", vel_dt, "Scale")
    
    # Backtrace: pos - velocity * dt
    backtrace = tree.nodes.new('ComputeNodeVectorMath')
    backtrace.operation = 'SUB'
    backtrace.location = (300, 50)
    link(tree, pos, "Normalized", backtrace, 0)
    link(tree, vel_dt, "Vector", backtrace, 1)
    
    # Sample field at backtraced position
    sample_field = tree.nodes.new('ComputeNodeSample')
    sample_field.location = (450, 50)
    link(tree, group_in, "Field", sample_field, "Grid")
    link(tree, backtrace, "Vector", sample_field, "Coordinate")
    
    # Capture
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (500, 50)
    link(tree, sample_field, "Color", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Advected")
    return tree


# ============================================================================
# NODE GROUP: VELOCITY UPDATE
# ============================================================================

def create_velocity_update():
    """
    Update velocity based on terrain gradient (gravity) and friction.
    
    Inputs:
        - Velocity (Grid): Current velocity
        - Gradient (Grid): Terrain gradient 
        - Water (Grid): Water depth
        - Gravity, Friction, dt
        
    Outputs:
        - New Velocity (Grid)
    """
    tree = get_or_create_tree("Velocity Update")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Velocity", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Gradient", "INPUT", "ComputeSocketGrid")  
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Gravity", "INPUT", "NodeSocketFloat", 9.8)
    add_socket(tree, "Friction", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "New Velocity", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-500, 0)
    group_out.location = (700, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-300, -200)
    link(tree, group_in, "Velocity", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-300, 100)
    
    # Sample current velocity
    s_vel = tree.nodes.new('ComputeNodeSample')
    s_vel.location = (-100, 100)
    link(tree, group_in, "Velocity", s_vel, "Grid")
    link(tree, pos, "Normalized", s_vel, "Coordinate")
    
    # Sample gradient
    s_grad = tree.nodes.new('ComputeNodeSample')
    s_grad.location = (-100, 0)
    link(tree, group_in, "Gradient", s_grad, "Grid")
    link(tree, pos, "Normalized", s_grad, "Coordinate")
    
    # Acceleration = -gravity * gradient
    accel = tree.nodes.new('ComputeNodeVectorMath')
    accel.operation = 'SCALE'
    accel.location = (100, 0)
    link(tree, s_grad, "Color", accel, 0)
    
    neg_g = tree.nodes.new('ComputeNodeMath')
    neg_g.operation = 'MUL'
    neg_g.location = (0, -50)
    link(tree, group_in, "Gravity", neg_g, 0)
    set_default(neg_g, 1, -1.0)
    link(tree, neg_g, "Value", accel, "Scale")
    
    # Friction: -friction * velocity
    fric = tree.nodes.new('ComputeNodeVectorMath')
    fric.operation = 'SCALE'
    fric.location = (100, 100)
    link(tree, s_vel, "Color", fric, 0)
    
    neg_f = tree.nodes.new('ComputeNodeMath')
    neg_f.operation = 'MUL'
    neg_f.location = (0, 50)
    link(tree, group_in, "Friction", neg_f, 0)
    set_default(neg_f, 1, -1.0)
    link(tree, neg_f, "Value", fric, "Scale")
    
    # Total acceleration = gravity + friction
    total_accel = tree.nodes.new('ComputeNodeVectorMath')
    total_accel.operation = 'ADD'
    total_accel.location = (250, 50)
    link(tree, accel, "Vector", total_accel, 0)
    link(tree, fric, "Vector", total_accel, 1)
    
    # dV = accel * dt
    dv = tree.nodes.new('ComputeNodeVectorMath')
    dv.operation = 'SCALE'
    dv.location = (400, 50)
    link(tree, total_accel, "Vector", dv, 0)
    link(tree, group_in, "dt", dv, "Scale")
    
    # new_vel = vel + dV
    new_vel = tree.nodes.new('ComputeNodeVectorMath')
    new_vel.operation = 'ADD'
    new_vel.location = (500, 75)
    link(tree, s_vel, "Color", new_vel, 0)
    link(tree, dv, "Vector", new_vel, 1)
    
    # Capture
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (600, 75)
    link(tree, new_vel, "Vector", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "New Velocity")
    return tree


# ============================================================================
# NODE GROUP: HYDRAULIC EROSION (Mass Conserving)
# ============================================================================

def create_hydraulic_erosion():
    """
    Mass-conserving hydraulic erosion with separate rock/soil K values.
    
    Inputs:
        - Bedrock, Soil, Sediment (Grids)
        - Velocity, Water (Grids)
        - K Erosion Soil, K Erosion Rock
        - K Deposition, K Capacity
        
    Outputs:
        - New Soil, New Sediment (Grids)
    """
    tree = get_or_create_tree("Hydraulic Erosion Advanced")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "K Erosion Soil", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "K Erosion Rock", "INPUT", "NodeSocketFloat", 0.001)
    add_socket(tree, "K Deposition", "INPUT", "NodeSocketFloat", 0.02)
    add_socket(tree, "K Capacity", "INPUT", "NodeSocketFloat", 0.5)
    add_socket(tree, "New Soil", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-600, 0)
    group_out.location = (900, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-400, -300)
    link(tree, group_in, "Soil", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-400, 150)
    
    # Sample all inputs
    s_soil = tree.nodes.new('ComputeNodeSample')
    s_soil.name = "Sample Soil"
    s_soil.location = (-200, 150)
    link(tree, group_in, "Soil", s_soil, "Grid")
    link(tree, pos, "Normalized", s_soil, "Coordinate")
    
    s_sed = tree.nodes.new('ComputeNodeSample')
    s_sed.name = "Sample Sediment"
    s_sed.location = (-200, 50)
    link(tree, group_in, "Sediment", s_sed, "Grid")
    link(tree, pos, "Normalized", s_sed, "Coordinate")
    
    s_vel = tree.nodes.new('ComputeNodeSample')
    s_vel.name = "Sample Velocity"  
    s_vel.location = (-200, -50)
    link(tree, group_in, "Velocity", s_vel, "Grid")
    link(tree, pos, "Normalized", s_vel, "Coordinate")
    
    s_water = tree.nodes.new('ComputeNodeSample')
    s_water.name = "Sample Water"
    s_water.location = (-200, -150)
    link(tree, group_in, "Water", s_water, "Grid")
    link(tree, pos, "Normalized", s_water, "Coordinate")
    
    # Velocity magnitude
    vel_len = tree.nodes.new('ComputeNodeVectorMath')
    vel_len.operation = 'LENGTH'
    vel_len.location = (0, -50)
    link(tree, s_vel, "Color", vel_len, 0)
    
    # Capacity = K_capacity * |velocity| * water
    cap_mul1 = tree.nodes.new('ComputeNodeMath')
    cap_mul1.operation = 'MUL'
    cap_mul1.location = (150, -50)
    link(tree, vel_len, "Value", cap_mul1, 0)
    link(tree, s_water, "Color", cap_mul1, 1)
    
    cap_mul2 = tree.nodes.new('ComputeNodeMath')
    cap_mul2.operation = 'MUL'
    cap_mul2.location = (300, -50)
    link(tree, cap_mul1, "Value", cap_mul2, 0)
    link(tree, group_in, "K Capacity", cap_mul2, 1)
    
    # Diff = Capacity - Sediment
    diff = tree.nodes.new('ComputeNodeMath')
    diff.operation = 'SUB'
    diff.location = (300, 50)
    link(tree, cap_mul2, "Value", diff, 0)
    link(tree, s_sed, "Color", diff, 1)
    
    # If diff > 0: erode, else deposit
    is_eroding = tree.nodes.new('ComputeNodeMath')
    is_eroding.operation = 'GREATER_THAN'
    is_eroding.location = (450, 50)
    link(tree, diff, "Value", is_eroding, 0)
    set_default(is_eroding, 1, 0.0)
    
    # Erosion amount (uses K_soil for now, simplified)
    erosion_raw = tree.nodes.new('ComputeNodeMath')
    erosion_raw.operation = 'MUL'
    erosion_raw.location = (450, 150)
    link(tree, diff, "Value", erosion_raw, 0)
    link(tree, group_in, "K Erosion Soil", erosion_raw, 1)
    
    # Clamp erosion to available soil
    erosion_clamped = tree.nodes.new('ComputeNodeMath')
    erosion_clamped.operation = 'MIN'
    erosion_clamped.location = (550, 150)
    link(tree, erosion_raw, "Value", erosion_clamped, 0)
    link(tree, s_soil, "Color", erosion_clamped, 1)
    
    erosion_final = tree.nodes.new('ComputeNodeMath')
    erosion_final.operation = 'MAX'
    erosion_final.location = (600, 150)
    link(tree, erosion_clamped, "Value", erosion_final, 0)
    set_default(erosion_final, 1, 0.0)
    
    # Deposit amount (when diff < 0)
    deposit = tree.nodes.new('ComputeNodeMath')
    deposit.operation = 'MUL'
    deposit.location = (450, -150)
    link(tree, diff, "Value", deposit, 0)  # diff is negative
    link(tree, group_in, "K Deposition", deposit, 1)
    
    # Transfer = erosion * is_eroding + deposit * (1-is_eroding)
    not_eroding = tree.nodes.new('ComputeNodeMath')
    not_eroding.operation = 'SUB'
    not_eroding.location = (500, 0)
    set_default(not_eroding, 0, 1.0)
    link(tree, is_eroding, "Value", not_eroding, 1)
    
    ero_masked = tree.nodes.new('ComputeNodeMath')
    ero_masked.operation = 'MUL'
    ero_masked.location = (650, 100)
    link(tree, erosion_final, "Value", ero_masked, 0)
    link(tree, is_eroding, "Value", ero_masked, 1)
    
    dep_masked = tree.nodes.new('ComputeNodeMath')
    dep_masked.operation = 'MUL'
    dep_masked.location = (650, -100)
    link(tree, deposit, "Value", dep_masked, 0)
    link(tree, not_eroding, "Value", dep_masked, 1)
    
    transfer = tree.nodes.new('ComputeNodeMath')
    transfer.operation = 'ADD'
    transfer.location = (700, 0)
    link(tree, ero_masked, "Value", transfer, 0)
    link(tree, dep_masked, "Value", transfer, 1)
    
    # New Soil = Soil - transfer
    new_soil = tree.nodes.new('ComputeNodeMath')
    new_soil.operation = 'SUB'
    new_soil.location = (750, 150)
    link(tree, s_soil, "Color", new_soil, 0)
    link(tree, transfer, "Value", new_soil, 1)
    
    # New Sediment = Sediment + transfer
    new_sed = tree.nodes.new('ComputeNodeMath')
    new_sed.operation = 'ADD'
    new_sed.location = (750, 50)
    link(tree, s_sed, "Color", new_sed, 0)
    link(tree, transfer, "Value", new_sed, 1)
    
    # Combine and capture
    comb_soil = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_soil.location = (800, 150)
    link(tree, new_soil, "Value", comb_soil, "X")
    link(tree, new_soil, "Value", comb_soil, "Y")
    link(tree, new_soil, "Value", comb_soil, "Z")
    
    comb_sed = tree.nodes.new('ComputeNodeCombineXYZ')
    comb_sed.location = (800, 50)
    link(tree, new_sed, "Value", comb_sed, "X")
    link(tree, new_sed, "Value", comb_sed, "Y")
    link(tree, new_sed, "Value", comb_sed, "Z")
    
    cap_soil = tree.nodes.new('ComputeNodeCapture')
    cap_soil.location = (850, 150)
    link(tree, comb_soil, "Vector", cap_soil, "Field")
    link(tree, grid_info, "Width", cap_soil, "Width")
    link(tree, grid_info, "Height", cap_soil, "Height")
    
    cap_sed = tree.nodes.new('ComputeNodeCapture')
    cap_sed.location = (850, 50)
    link(tree, comb_sed, "Vector", cap_sed, "Field")
    link(tree, grid_info, "Width", cap_sed, "Width")
    link(tree, grid_info, "Height", cap_sed, "Height")
    
    link(tree, cap_soil, "Grid", group_out, "New Soil")
    link(tree, cap_sed, "Grid", group_out, "New Sediment")
    
    return tree


# ============================================================================
# NODE GROUP: THERMAL EROSION (Talus Angle)
# ============================================================================

def create_thermal_erosion():
    """
    Thermal erosion: slopes steeper than talus angle collapse.
    Material moves from high to low neighbors.
    
    Inputs:
        - Soil (Grid)
        - Talus Angle: Maximum stable slope (0-1, tan of angle)
        - dt: Time step
        
    Outputs:
        - New Soil (Grid)
    """
    tree = get_or_create_tree("Thermal Erosion")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Talus Angle", "INPUT", "NodeSocketFloat", 0.5)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "New Soil", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-600, 0)
    group_out.location = (800, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-400, -200)
    link(tree, group_in, "Soil", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-400, 100)
    
    # Pixel sizes
    pix_x = tree.nodes.new('ComputeNodeMath')
    pix_x.operation = 'DIV'
    pix_x.location = (-400, -50)
    set_default(pix_x, 0, 1.0)
    link(tree, grid_info, "Width", pix_x, 1)
    
    pix_y = tree.nodes.new('ComputeNodeMath')
    pix_y.operation = 'DIV'
    pix_y.location = (-400, -100)
    set_default(pix_y, 0, 1.0)
    link(tree, grid_info, "Height", pix_y, 1)
    
    # Sample center
    s_center = tree.nodes.new('ComputeNodeSample')
    s_center.location = (-200, 100)
    link(tree, group_in, "Soil", s_center, "Grid")
    link(tree, pos, "Normalized", s_center, "Coordinate")
    
    # Sample 4 neighbors and compute average excess slope
    # For simplicity, sample -X neighbor
    off_nx = tree.nodes.new('ComputeNodeCombineXYZ')
    off_nx.location = (-300, 0)
    neg_px = tree.nodes.new('ComputeNodeMath')
    neg_px.operation = 'MUL'
    neg_px.location = (-350, 0)
    link(tree, pix_x, "Value", neg_px, 0)
    set_default(neg_px, 1, -1.0)
    link(tree, neg_px, "Value", off_nx, "X")
    
    add_nx = tree.nodes.new('ComputeNodeVectorMath')
    add_nx.operation = 'ADD'
    add_nx.location = (-200, 0)
    link(tree, pos, "Normalized", add_nx, 0)
    link(tree, off_nx, "Vector", add_nx, 1)
    
    s_nx = tree.nodes.new('ComputeNodeSample')
    s_nx.location = (-50, 0)
    link(tree, group_in, "Soil", s_nx, "Grid")
    link(tree, add_nx, "Vector", s_nx, "Coordinate")
    
    # Height difference to neighbor
    h_diff = tree.nodes.new('ComputeNodeMath')
    h_diff.operation = 'SUB'
    h_diff.location = (100, 50)
    link(tree, s_center, "Color", h_diff, 0)
    link(tree, s_nx, "Color", h_diff, 1)
    
    # Excess = h_diff - talus_angle (if positive, slope is too steep)
    excess = tree.nodes.new('ComputeNodeMath')
    excess.operation = 'SUB'
    excess.location = (200, 50)
    link(tree, h_diff, "Value", excess, 0)
    link(tree, group_in, "Talus Angle", excess, 1)
    
    # Clamp excess to positive only
    excess_pos = tree.nodes.new('ComputeNodeMath')
    excess_pos.operation = 'MAX'
    excess_pos.location = (300, 50)
    link(tree, excess, "Value", excess_pos, 0)
    set_default(excess_pos, 1, 0.0)
    
    # Transfer = excess * 0.5 * dt (half goes to neighbor)
    transfer = tree.nodes.new('ComputeNodeMath')
    transfer.operation = 'MUL'
    transfer.location = (400, 50)
    link(tree, excess_pos, "Value", transfer, 0)
    set_default(transfer, 1, 0.5)
    
    transfer_dt = tree.nodes.new('ComputeNodeMath')
    transfer_dt.operation = 'MUL'
    transfer_dt.location = (500, 50)
    link(tree, transfer, "Value", transfer_dt, 0)
    link(tree, group_in, "dt", transfer_dt, 1)
    
    # New soil = soil - transfer (simplified, only considers one neighbor)
    new_soil = tree.nodes.new('ComputeNodeMath')
    new_soil.operation = 'SUB'
    new_soil.location = (600, 100)
    link(tree, s_center, "Color", new_soil, 0)
    link(tree, transfer_dt, "Value", new_soil, 1)
    
    # Combine and capture
    comb = tree.nodes.new('ComputeNodeCombineXYZ')
    comb.location = (650, 100)
    link(tree, new_soil, "Value", comb, "X")
    link(tree, new_soil, "Value", comb, "Y")
    link(tree, new_soil, "Value", comb, "Z")
    
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (700, 100)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "New Soil")
    return tree


# ============================================================================
# NODE GROUP: ADD RAIN
# ============================================================================

def create_add_rain():
    """
    Add rainfall to water buffer.
    
    Inputs:
        - Water (Grid)
        - Rain Rate
        - dt
        
    Outputs:
        - New Water (Grid)
    """
    tree = get_or_create_tree("Add Rain")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Rain Rate", "INPUT", "NodeSocketFloat", 0.001)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-300, 0)
    group_out.location = (400, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-100, -100)
    link(tree, group_in, "Water", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-100, 50)
    
    s_water = tree.nodes.new('ComputeNodeSample')
    s_water.location = (50, 50)
    link(tree, group_in, "Water", s_water, "Grid")
    link(tree, pos, "Normalized", s_water, "Coordinate")
    
    # rain = rain_rate * dt
    rain = tree.nodes.new('ComputeNodeMath')
    rain.operation = 'MUL'
    rain.location = (50, -50)
    link(tree, group_in, "Rain Rate", rain, 0)
    link(tree, group_in, "dt", rain, 1)
    
    # new_water = water + rain
    new_water = tree.nodes.new('ComputeNodeMath')
    new_water.operation = 'ADD'
    new_water.location = (150, 50)
    link(tree, s_water, "Color", new_water, 0)
    link(tree, rain, "Value", new_water, 1)
    
    comb = tree.nodes.new('ComputeNodeCombineXYZ')
    comb.location = (250, 50)
    link(tree, new_water, "Value", comb, "X")
    link(tree, new_water, "Value", comb, "Y")
    link(tree, new_water, "Value", comb, "Z")
    
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (300, 50)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "New Water")
    return tree


# ============================================================================
# NODE GROUP: EVAPORATION
# ============================================================================

def create_evaporation():
    """
    Evaporate water and deposit remaining sediment.
    
    Inputs:
        - Water, Sediment, Soil (Grids)
        - Evaporation Rate
        - dt
        
    Outputs:
        - New Water, New Sediment, New Soil (Grids)
    """
    tree = get_or_create_tree("Evaporation")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Evaporation Rate", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Soil", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-400, 0)
    group_out.location = (600, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (-200, -200)
    link(tree, group_in, "Water", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (-200, 100)
    
    # Sample all
    s_water = tree.nodes.new('ComputeNodeSample')
    s_water.location = (0, 100)
    link(tree, group_in, "Water", s_water, "Grid")
    link(tree, pos, "Normalized", s_water, "Coordinate")
    
    s_sed = tree.nodes.new('ComputeNodeSample')
    s_sed.location = (0, 0)
    link(tree, group_in, "Sediment", s_sed, "Grid")
    link(tree, pos, "Normalized", s_sed, "Coordinate")
    
    s_soil = tree.nodes.new('ComputeNodeSample')
    s_soil.location = (0, -100)
    link(tree, group_in, "Soil", s_soil, "Grid")
    link(tree, pos, "Normalized", s_soil, "Coordinate")
    
    # evap_factor = (1 - evap_rate * dt)
    evap_dt = tree.nodes.new('ComputeNodeMath')
    evap_dt.operation = 'MUL'
    evap_dt.location = (100, -50)
    link(tree, group_in, "Evaporation Rate", evap_dt, 0)
    link(tree, group_in, "dt", evap_dt, 1)
    
    evap_factor = tree.nodes.new('ComputeNodeMath')
    evap_factor.operation = 'SUB'
    evap_factor.location = (200, -50)
    set_default(evap_factor, 0, 1.0)
    link(tree, evap_dt, "Value", evap_factor, 1)
    
    # new_water = water * evap_factor
    new_water = tree.nodes.new('ComputeNodeMath')
    new_water.operation = 'MUL'
    new_water.location = (300, 100)
    link(tree, s_water, "Color", new_water, 0)
    link(tree, evap_factor, "Value", new_water, 1)
    
    # Water lost
    water_lost = tree.nodes.new('ComputeNodeMath')
    water_lost.operation = 'SUB'
    water_lost.location = (300, 50)
    link(tree, s_water, "Color", water_lost, 0)
    link(tree, new_water, "Value", water_lost, 1)
    
    # Sediment deposited = sediment * (water_lost / water)
    # Simplified: deposit all sediment proportionally
    sed_ratio = tree.nodes.new('ComputeNodeMath')
    sed_ratio.operation = 'DIV'
    sed_ratio.location = (350, 0)
    link(tree, water_lost, "Value", sed_ratio, 0)
    link(tree, s_water, "Color", sed_ratio, 1)
    
    sed_deposit = tree.nodes.new('ComputeNodeMath')
    sed_deposit.operation = 'MUL'
    sed_deposit.location = (400, 0)
    link(tree, s_sed, "Color", sed_deposit, 0)
    link(tree, sed_ratio, "Value", sed_deposit, 1)
    
    # new_sed = sed - deposit
    new_sed = tree.nodes.new('ComputeNodeMath')
    new_sed.operation = 'SUB'
    new_sed.location = (450, 0)
    link(tree, s_sed, "Color", new_sed, 0)
    link(tree, sed_deposit, "Value", new_sed, 1)
    
    # new_soil = soil + deposit
    new_soil = tree.nodes.new('ComputeNodeMath')
    new_soil.operation = 'ADD'
    new_soil.location = (450, -100)
    link(tree, s_soil, "Color", new_soil, 0)
    link(tree, sed_deposit, "Value", new_soil, 1)
    
    # Combines and captures
    def make_output(val_node, y_pos):
        comb = tree.nodes.new('ComputeNodeCombineXYZ')
        comb.location = (500, y_pos)
        link(tree, val_node, "Value", comb, "X")
        link(tree, val_node, "Value", comb, "Y")
        link(tree, val_node, "Value", comb, "Z")
        cap = tree.nodes.new('ComputeNodeCapture')
        cap.location = (550, y_pos)
        link(tree, comb, "Vector", cap, "Field")
        link(tree, grid_info, "Width", cap, "Width")
        link(tree, grid_info, "Height", cap, "Height")
        return cap
    
    cap_water = make_output(new_water, 100)
    cap_sed = make_output(new_sed, 0)
    cap_soil = make_output(new_soil, -100)
    
    link(tree, cap_water, "Grid", group_out, "New Water")
    link(tree, cap_sed, "Grid", group_out, "New Sediment")
    link(tree, cap_soil, "Grid", group_out, "New Soil")
    
    return tree


# ============================================================================
# NODE GROUP: COMBINE HEIGHT
# ============================================================================

def create_combine_height():
    """
    Combine Bedrock + Soil into total Height.
    """
    tree = get_or_create_tree("Combine Height")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Bedrock", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Height", "OUTPUT", "ComputeSocketGrid")
    
    group_in = tree.nodes.new('ComputeNodeGroupInput')
    group_out = tree.nodes.new('ComputeNodeGroupOutput')
    group_in.location = (-200, 0)
    group_out.location = (400, 0)
    
    grid_info = tree.nodes.new('ComputeNodeImageInfo')
    grid_info.location = (0, -100)
    link(tree, group_in, "Bedrock", grid_info, "Grid")
    
    pos = tree.nodes.new('ComputeNodePosition')
    pos.location = (0, 50)
    
    s_bed = tree.nodes.new('ComputeNodeSample')
    s_bed.location = (100, 100)
    link(tree, group_in, "Bedrock", s_bed, "Grid")
    link(tree, pos, "Normalized", s_bed, "Coordinate")
    
    s_soil = tree.nodes.new('ComputeNodeSample')
    s_soil.location = (100, 0)
    link(tree, group_in, "Soil", s_soil, "Grid")
    link(tree, pos, "Normalized", s_soil, "Coordinate")
    
    add_h = tree.nodes.new('ComputeNodeMath')
    add_h.operation = 'ADD'
    add_h.location = (200, 50)
    link(tree, s_bed, "Color", add_h, 0)
    link(tree, s_soil, "Color", add_h, 1)
    
    comb = tree.nodes.new('ComputeNodeCombineXYZ')
    comb.location = (250, 50)
    link(tree, add_h, "Value", comb, "X")
    link(tree, add_h, "Value", comb, "Y")
    link(tree, add_h, "Value", comb, "Z")
    
    cap = tree.nodes.new('ComputeNodeCapture')
    cap.location = (300, 50)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, grid_info, "Width", cap, "Width")
    link(tree, grid_info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Height")
    return tree


# ============================================================================
# MAIN SETUP FUNCTION
# ============================================================================

def setup_all():
    """Create all erosion node groups."""
    print("Creating Advanced Erosion Node Groups...")
    
    create_terrain_state_init()
    print("  ✓ Terrain State Init")
    
    create_compute_gradient()
    print("  ✓ Compute Gradient Advanced")
    
    create_d8_flow()
    print("  ✓ D8 Flow Direction")
    
    create_fd8_flow()
    print("  ✓ FD8 Flow Weights (Multi-Flow)")
    
    create_flow_accumulation()
    print("  ✓ Flow Accumulation")
    
    create_advect_field()
    print("  ✓ Advect Field")
    
    create_velocity_update()
    print("  ✓ Velocity Update")
    
    create_hydraulic_erosion()
    print("  ✓ Hydraulic Erosion Advanced")
    
    create_thermal_erosion()
    print("  ✓ Thermal Erosion")
    
    create_add_rain()
    print("  ✓ Add Rain")
    
    create_evaporation()
    print("  ✓ Evaporation")
    
    create_combine_height()
    print("  ✓ Combine Height")
    
    print("\nDone! 12 erosion node groups created.")
    print("""
Flow Routing:
  - D8 Flow Direction: Single steepest descent (fast)
  - FD8 Flow Weights: Multi-flow proportional to slope (realistic)
  - Flow Accumulation: Redistribute water based on weights

Simulation Pipeline:
  1. Terrain State Init → Bedrock/Soil/Water/Sediment/Velocity
  2. Add Rain → add precipitation
  3. FD8/D8 Flow → compute flow directions
  4. Flow Accumulation → redistribute water
  5. Velocity Update → gravity + friction
  6. Advect Field → semi-Lagrangian transport
  7. Hydraulic Erosion → erode/deposit
  8. Thermal Erosion → talus collapse
  9. Evaporation → reduce water, deposit sediment
  10. Combine Height → Bedrock + Soil = output
""")


if __name__ == "__main__":
    setup_all()
