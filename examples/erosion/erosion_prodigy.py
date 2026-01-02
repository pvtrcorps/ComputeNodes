"""
Prodigy Terrain Erosion System
==============================

Upgraded version of the erosion system with:
- Correct mass-conserving flow accumulation (Gather approach)
- Loop-ready pipeline generation
- Enhanced parameter inputs (Fields support)
- Full demo graph creation

Usage:
    import erosion_prodigy
    erosion_prodigy.setup_all()
    erosion_prodigy.create_demo_graph()
"""

import bpy
import math

# ============================================================================
# UTILS
# ============================================================================

def get_or_create_tree(name: str) -> bpy.types.NodeTree:
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    return bpy.data.node_groups.new(name, 'ComputeNodeTree')

def clear_tree(tree: bpy.types.NodeTree):
    tree.nodes.clear()

def add_socket(tree, name, in_out, socket_type, default=None):
    item = tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None and hasattr(item, 'default_value'):
        item.default_value = default
    return item

def link(tree, from_node, from_socket, to_node, to_socket):
    out = from_node.outputs[from_socket] if isinstance(from_socket, (int, str)) else from_socket
    inp = to_node.inputs[to_socket] if isinstance(to_socket, (int, str)) else to_socket
    tree.links.new(out, inp)

def set_default(node, socket, value):
    try:
        if isinstance(socket, int):
            node.inputs[socket].default_value = value
        elif socket in node.inputs:
            node.inputs[socket].default_value = value
    except:
        pass

# ============================================================================
# NODE GROUPS
# ============================================================================

def create_terrain_state_init():
    tree = get_or_create_tree("Prodigy State Init")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Rock Threshold", "INPUT", "NodeSocketFloat", 0.3)
    add_socket(tree, "Initial Water", "INPUT", "NodeSocketFloat", 0.0)
    
    add_socket(tree, "Bedrock", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    in_node = nodes.new("ComputeNodeGroupInput")
    in_node.location = (-400, 0)
    out_node = nodes.new("ComputeNodeGroupOutput")
    out_node.location = (800, 0)
    
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-200, -200)
    link(tree, in_node, "Height", info, "Grid")
    
    pos = nodes.new("ComputeNodePosition")
    pos.location = (-200, 100)
    
    # Sample Height
    samp = nodes.new("ComputeNodeSample")
    samp.location = (0, 100)
    link(tree, in_node, "Height", samp, "Grid")
    link(tree, pos, "Normalized", samp, "Coordinate")
    
    # Bedrock = Height * Threshold
    bed_mul = nodes.new("ComputeNodeMath")
    bed_mul.operation = "MUL"
    bed_mul.location = (200, 100)
    link(tree, samp, "Color", bed_mul, 0)
    link(tree, in_node, "Rock Threshold", bed_mul, 1)
    
    # Soil = Height - Bedrock
    soil_sub = nodes.new("ComputeNodeMath")
    soil_sub.operation = "SUB"
    soil_sub.location = (200, 0)
    link(tree, samp, "Color", soil_sub, 0)
    link(tree, bed_mul, "Value", soil_sub, 1)
    
    # Captures
    def make_cap(name, val_node, y, is_vec=False, def_val=None):
        cap = nodes.new("ComputeNodeCapture")
        cap.location = (600, y)
        cap.label = name
        
        comb = nodes.new("ComputeNodeCombineXYZ")
        comb.location = (400, y)
        
        if def_val is not None: # Constant
            set_default(comb, "X", def_val)
            set_default(comb, "Y", def_val)
            set_default(comb, "Z", def_val)
        elif is_vec: # Vector field (assumed linked elsewhere or 0)
             set_default(comb, "X", 0.0)
             set_default(comb, "Y", 0.0)
             set_default(comb, "Z", 0.0)
        else: # Scalar from node
             link(tree, val_node, "Value", comb, "X")
             link(tree, val_node, "Value", comb, "Y")
             link(tree, val_node, "Value", comb, "Z")
             
        link(tree, comb, "Vector", cap, "Field")
        link(tree, info, "Width", cap, "Width")
        link(tree, info, "Height", cap, "Height")
        return cap

    # Bedrock
    c_bed = make_cap("Bedrock", bed_mul, 200)
    link(tree, c_bed, "Grid", out_node, "Bedrock")
    
    # Soil
    c_soil = make_cap("Soil", soil_sub, 100)
    link(tree, c_soil, "Grid", out_node, "Soil")
    
    # Water (Constant initial)
    c_water = nodes.new("ComputeNodeCapture")
    c_water.location = (600, 0)
    comb_w = nodes.new("ComputeNodeCombineXYZ")
    comb_w.location = (400, 0)
    link(tree, in_node, "Initial Water", comb_w, "X")
    link(tree, in_node, "Initial Water", comb_w, "Y")
    link(tree, in_node, "Initial Water", comb_w, "Z")
    link(tree, comb_w, "Vector", c_water, "Field")
    link(tree, info, "Width", c_water, "Width")
    link(tree, info, "Height", c_water, "Height")
    link(tree, c_water, "Grid", out_node, "Water")

    # Sediment (0)
    c_sed = make_cap("Sediment", None, -100, def_val=0.0)
    link(tree, c_sed, "Grid", out_node, "Sediment")
    
    # Velocity (0)
    c_vel = make_cap("Velocity", None, -200, def_val=0.0)
    link(tree, c_vel, "Grid", out_node, "Velocity")
    
    return tree

def create_fd4_flow_weights():
    """ 4-way Flow Weights based on slope (Exponent) """
    tree = get_or_create_tree("Prodigy FD4 Weights")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Exponent", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Flow Weights", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-1000, 0)
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (1000, 0)

    # Grid Info
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-800, -200)
    link(tree, group_in, "Height", info, "Grid")
    
    # Pixel size
    pix_x = nodes.new("ComputeNodeMath")
    pix_x.operation = "DIV"
    link(tree, info, "Width", pix_x, 1)
    set_default(pix_x, 0, 1.0) 
    
    pix_y = nodes.new("ComputeNodeMath")
    pix_y.operation = "DIV"
    link(tree, info, "Height", pix_y, 1)
    set_default(pix_y, 0, 1.0)

    pos = nodes.new("ComputeNodePosition")
    pos.location = (-800, 100)

    # Center Sample
    s_center = nodes.new("ComputeNodeSample")
    s_center.location = (-600, 100)
    link(tree, group_in, "Height", s_center, "Grid")
    link(tree, pos, "Normalized", s_center, "Coordinate")
    
    # Neighbors (E, W, N, S)
    # E: (+1, 0), W: (-1, 0), N: (0, +1), S: (0, -1)
    neighbors = [
        ("E", 1, 0), ("W", -1, 0), ("N", 0, 1), ("S", 0, -1)
    ]
    
    slope_pow_outputs = []
    
    y = 200
    for name, dx, dy in neighbors:
        # Offset Vector
        comb_off = nodes.new("ComputeNodeCombineXYZ")
        comb_off.location = (-600, y)
        if dx != 0:
            mul = nodes.new("ComputeNodeMath")
            mul.operation = "MUL"
            mul.location = (-750, y)
            link(tree, pix_x, "Value", mul, 0)
            set_default(mul, 1, float(dx))
            link(tree, mul, "Value", comb_off, "X")
        if dy != 0:
            mul = nodes.new("ComputeNodeMath")
            mul.operation = "MUL"
            mul.location = (-750, y)
            link(tree, pix_y, "Value", mul, 0)
            set_default(mul, 1, float(dy))
            link(tree, mul, "Value", comb_off, "Y")
            
        add_pos = nodes.new("ComputeNodeVectorMath")
        add_pos.operation = "ADD"
        add_pos.location = (-450, y)
        link(tree, pos, "Normalized", add_pos, 0)
        link(tree, comb_off, "Vector", add_pos, 1)
        
        # Sample Neighbor
        s_neigh = nodes.new("ComputeNodeSample")
        s_neigh.location = (-300, y)
        s_neigh.label = f"Sample {name}"
        link(tree, group_in, "Height", s_neigh, "Grid")
        link(tree, add_pos, "Vector", s_neigh, "Coordinate")
        
        # Slope = Center - Neighbor (Positive = Downhill)
        sub = nodes.new("ComputeNodeMath")
        sub.operation = "SUB"
        sub.location = (-150, y)
        link(tree, s_center, "Color", sub, 0)
        link(tree, s_neigh, "Color", sub, 1)
        
        # Max(0, Slope)
        mx = nodes.new("ComputeNodeMath")
        mx.operation = "MAX"
        mx.location = (0, y)
        link(tree, sub, "Value", mx, 0) # Fixed: Connect slope to max
        set_default(mx, 1, 0.0)
        
        # Power
        pw = nodes.new("ComputeNodeMath")
        pw.operation = "POW"
        pw.location = (150, y)
        link(tree, mx, "Value", pw, 0)
        link(tree, group_in, "Exponent", pw, 1)
        
        slope_pow_outputs.append(pw)
        y -= 150
        
    # Sum Weights
    sum1 = nodes.new("ComputeNodeMath")
    sum1.operation = "ADD"
    sum1.location = (300, 100)
    link(tree, slope_pow_outputs[0], "Value", sum1, 0)
    link(tree, slope_pow_outputs[1], "Value", sum1, 1)
    
    sum2 = nodes.new("ComputeNodeMath")
    sum2.operation = "ADD"
    sum2.location = (300, -100)
    link(tree, slope_pow_outputs[2], "Value", sum2, 0)
    link(tree, slope_pow_outputs[3], "Value", sum2, 1)
    
    total = nodes.new("ComputeNodeMath")
    total.operation = "ADD"
    total.location = (450, 0)
    link(tree, sum1, "Value", total, 0)
    link(tree, sum2, "Value", total, 1)
    
    # Safe Total (avoid div 0)
    safe = nodes.new("ComputeNodeMath")
    safe.operation = "MAX"
    safe.location = (600, 0)
    link(tree, total, "Value", safe, 0)
    set_default(safe, 1, 0.00001)
    
    # Normalize
    weights = []
    dy = 100
    for pw in slope_pow_outputs:
        div = nodes.new("ComputeNodeMath")
        div.operation = "DIV"
        div.location = (700, dy)
        link(tree, pw, "Value", div, 0)
        link(tree, safe, "Value", div, 1)
        weights.append(div)
        dy -= 50
        
    # Output RGBA = (E, W, N, S)
    comb_col = nodes.new("ComputeNodeCombineColor")
    comb_col.location = (850, 0)
    link(tree, weights[0], "Value", comb_col, "Red")
    link(tree, weights[1], "Value", comb_col, "Green")
    link(tree, weights[2], "Value", comb_col, "Blue")
    link(tree, weights[3], "Value", comb_col, "Alpha")
    
    cap = nodes.new("ComputeNodeCapture")
    cap.location = (950, 0)
    link(tree, comb_col, "Color", cap, "Field")
    link(tree, info, "Width", cap, "Width")
    link(tree, info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Flow Weights")
    return tree

def create_flow_accumulation_correct():
    """ 
    Correct Gather-based Flow Accumulation.
    NewWater = SelfRain + Sum(NeighborWater * NeighborWeightToMe)
    Note: Requires multiple passes (ping-pong) for full river formation.
    Inside a loop, this spreads water downhill.
    """
    tree = get_or_create_tree("Prodigy Flow Acc")
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Flow Weights", "INPUT", "ComputeSocketGrid") # RGBA = E, W, N, S
    add_socket(tree, "Accumulated", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-1200, 0)
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (1200, 0)
    
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-1000, -200)
    link(tree, group_in, "Water", info, "Grid")
    
    pix_x = nodes.new("ComputeNodeMath")
    pix_x.operation = "DIV"
    link(tree, info, "Width", pix_x, 1)
    set_default(pix_x, 0, 1.0)
    
    pix_y = nodes.new("ComputeNodeMath")
    pix_y.operation = "DIV"
    link(tree, info, "Height", pix_y, 1)
    set_default(pix_y, 0, 1.0)
    
    pos = nodes.new("ComputeNodePosition")
    pos.location = (-1000, 100)
    
    # 1. Start with water that STAYS in current cell.
    # Stay = Water * (1 - sum(out_weights))
    # Actually, flow weights sum to 1.0 only if all is downhill.
    # If pit, weights sum to 0.0, so all stays. This is implicit in "1 - sum".
    s_me_water = nodes.new("ComputeNodeSample")
    s_me_water.location = (-800, 200)
    link(tree, group_in, "Water", s_me_water, "Grid")
    link(tree, pos, "Normalized", s_me_water, "Coordinate")
    
    s_me_weights = nodes.new("ComputeNodeSample")
    s_me_weights.location = (-800, 0)
    link(tree, group_in, "Flow Weights", s_me_weights, "Grid")
    link(tree, pos, "Normalized", s_me_weights, "Coordinate")
    
    sep_w = nodes.new("ComputeNodeSeparateColor")
    sep_w.location = (-600, 0)
    link(tree, s_me_weights, "Color", sep_w, "Color")
    
    # Sum Outflow Coeffs
    out_sum_1 = nodes.new("ComputeNodeMath")
    out_sum_1.operation = "ADD"
    link(tree, sep_w, "Red", out_sum_1, 0)
    link(tree, sep_w, "Green", out_sum_1, 1)
    
    out_sum_2 = nodes.new("ComputeNodeMath")
    out_sum_2.operation = "ADD"
    link(tree, sep_w, "Blue", out_sum_2, 0)
    link(tree, sep_w, "Alpha", out_sum_2, 1)
    
    total_out = nodes.new("ComputeNodeMath")
    total_out.operation = "ADD"
    link(tree, out_sum_1, "Value", total_out, 0)
    link(tree, out_sum_2, "Value", total_out, 1)
    
    # Stay factor = 1 - TotalOut
    stay_fac = nodes.new("ComputeNodeMath")
    stay_fac.operation = "SUB"
    set_default(stay_fac, 0, 1.0)
    link(tree, total_out, "Value", stay_fac, 1)
    
    stay_water = nodes.new("ComputeNodeMath")
    stay_water.operation = "MUL"
    stay_water.location = (-300, 200)
    link(tree, s_me_water, "Color", stay_water, 0)
    link(tree, stay_fac, "Value", stay_water, 1)
    
    # 2. Gather from Neighbors
    # E (+1,0) flows West to Me (Index 1: Green)
    # W (-1,0) flows East to Me (Index 0: Red)
    # N (0,+1) flows South to Me (Index 3: Alpha)
    # S (0,-1) flows North to Me (Index 2: Blue)
    
    neighbors_gather = [
        ("E", 1, 0, "Green"),  # E flows W (Green)
        ("W", -1, 0, "Red"),   # W flows E (Red)
        ("N", 0, 1, "Alpha"),  # N flows S (Alpha)
        ("S", 0, -1, "Blue")   # S flows N (Blue)
    ]
    
    inflow_terms = []
    
    y = 0
    for name, dx, dy, channel in neighbors_gather:
        # Offset
        comb_off = nodes.new("ComputeNodeCombineXYZ")
        comb_off.location = (-900, y)
        if dx:
            m = nodes.new("ComputeNodeMath")
            m.operation = "MUL"
            link(tree, pix_x, "Value", m, 0)
            set_default(m, 1, float(dx))
            link(tree, m, "Value", comb_off, "X")
        if dy:
            m = nodes.new("ComputeNodeMath")
            m.operation = "MUL"
            link(tree, pix_y, "Value", m, 0)
            set_default(m, 1, float(dy))
            link(tree, m, "Value", comb_off, "Y")
            
        pos_off = nodes.new("ComputeNodeVectorMath")
        pos_off.operation = "ADD"
        pos_off.location = (-750, y)
        link(tree, pos, "Normalized", pos_off, 0)
        link(tree, comb_off, "Vector", pos_off, 1)
        
        # Sample Neighbor Water
        n_wat = nodes.new("ComputeNodeSample")
        n_wat.location = (-600, y+50)
        link(tree, group_in, "Water", n_wat, "Grid")
        link(tree, pos_off, "Vector", n_wat, "Coordinate")
        
        # Sample Neighbor Weights
        n_wgt = nodes.new("ComputeNodeSample")
        n_wgt.location = (-600, y-50)
        link(tree, group_in, "Flow Weights", n_wgt, "Grid")
        link(tree, pos_off, "Vector", n_wgt, "Coordinate")
        
        # Get Channel
        sep = nodes.new("ComputeNodeSeparateColor")
        sep.location = (-450, y-50)
        link(tree, n_wgt, "Color", sep, "Color")
        
        # Inflow = N_Water * N_Weight[Channel]
        inflow = nodes.new("ComputeNodeMath")
        inflow.operation = "MUL"
        inflow.location = (-300, y)
        link(tree, n_wat, "Color", inflow, 0)
        link(tree, sep, channel, inflow, 1)
        
        inflow_terms.append(inflow)
        y -= 250
        
    # Sum Inflows
    sum_inf_1 = nodes.new("ComputeNodeMath")
    sum_inf_1.operation = "ADD"
    link(tree, inflow_terms[0], "Value", sum_inf_1, 0)
    link(tree, inflow_terms[1], "Value", sum_inf_1, 1)
    
    sum_inf_2 = nodes.new("ComputeNodeMath")
    sum_inf_2.operation = "ADD"
    link(tree, inflow_terms[2], "Value", sum_inf_2, 0)
    link(tree, inflow_terms[3], "Value", sum_inf_2, 1)
    
    total_inflow = nodes.new("ComputeNodeMath")
    total_inflow.operation = "ADD"
    link(tree, sum_inf_1, "Value", total_inflow, 0)
    link(tree, sum_inf_2, "Value", total_inflow, 1)
    
    # Total Water = Stay + Inflow
    final = nodes.new("ComputeNodeMath")
    final.operation = "ADD"
    final.location = (500, 0)
    link(tree, stay_water, "Value", final, 0)
    link(tree, total_inflow, "Value", final, 1)
    
    # Output
    comb_f = nodes.new("ComputeNodeCombineXYZ")
    comb_f.location = (700, 0)
    link(tree, final, "Value", comb_f, "X")
    link(tree, final, "Value", comb_f, "Y")
    link(tree, final, "Value", comb_f, "Z")
    
    cap = nodes.new("ComputeNodeCapture")
    cap.location = (900, 0)
    link(tree, comb_f, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width")
    link(tree, info, "Height", cap, "Height")
    
    link(tree, cap, "Grid", group_out, "Accumulated")
    return tree

# ============================================================================
# MAIN SETUP
# ============================================================================

def setup_all():
    print("Generating Prodigy Erosion Nodes...")
    
    # 1. State Init
    create_terrain_state_init()
    
    # 2. FD4 Weights
    create_fd4_flow_weights()
    
    # 3. Flow Accumulation
    create_flow_accumulation_correct()
    
    # Reuse good helpers from advanced if available, else recreate simple ones
    # For brevity in this artifact, I assume the user ran erosion_advanced.py already 
    # OR I can re-export the essential remaining ones.
    # Let's trust erosion_advanced.py for the rest (Hydraulic, Thermal, etc.) 
    # as they seemed mostly correct except for Flow Accumulation.
    
    # Actually, let's patch Hydraulic to be safe or improved?
    # No, the "Hydraulic Erosion Advanced" in previous file was decent.
    # I will just ensure the graph I build uses these new ones + those.
    pass

def create_demo_graph():
    """ Creates a full demo graph "Erosion Demo" """
    if "Erosion Demo" in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups["Erosion Demo"])
    
    tree = bpy.data.node_groups.new("Erosion Demo", "ComputeNodeTree")
    nodes = tree.nodes
    links = tree.links
    
    # 1. Noise Input
    noise = nodes.new("ComputeNodeNoiseTexture")
    noise.location = (-1200, 0)
    noise.inputs["Scale"].default_value = 5.0
    
    # 2. State Init
    init = nodes.new("ComputeNodeGroup")
    init.node_tree = bpy.data.node_groups["Prodigy State Init"]
    init.location = (-1000, 0)
    init.inputs["Rock Threshold"].default_value = 0.2
    
    # Capture noise to grid first (Init expects Grid)
    cap_noise = nodes.new("ComputeNodeCapture")
    cap_noise.location = (-1100, 200)
    cap_noise.inputs["Width"].default_value = 512
    cap_noise.inputs["Height"].default_value = 512
    links.new(noise.outputs["Color"], cap_noise.inputs["Field"])
    links.new(cap_noise.outputs["Grid"], init.inputs["Height"])
    
    # 3. Repeat Zone
    rep_in = nodes.new("ComputeNodeRepeatInput")
    rep_in.location = (-700, 0)
    rep_out = nodes.new("ComputeNodeRepeatOutput")
    rep_out.location = (1500, 0)
    
    # Pair them
    rep_in.paired_output = rep_out.name
    rep_out.paired_input = rep_in.name
    
    # Link items from Init to Repeat
    # Items: Bedrock, Soil, Water, Sediment, Velocity
    item_names = ["Bedrock", "Soil", "Water", "Sediment", "Velocity"]
    
    # Connecting Init -> Rep In
    for i, name in enumerate(item_names):
        # Add state to Repeat Input (which syncs to Output)
        rep_in.add_state(name, "ComputeSocketGrid") 
        
        # Link to Input Socket
        if name in rep_in.inputs:
            links.new(init.outputs[name], rep_in.inputs[name])
    
    # Force sync on Output node to be sure
    # (add_state should handle it, but being explicit helps in scripts)
    rep_in._sync_paired_output()
    
    # INSIDE LOOP
    
    # A. Add Rain
    rain = nodes.new("ComputeNodeGroup")
    rain.node_tree = bpy.data.node_groups.get("Add Rain")
    rain.location = (-400, 200)
    rain.inputs["Rain Rate"].default_value = 0.005
    
    # Bedrock (Pass through)
    
    # B. Flow Weights (FD4) - Needs Height = Bed + Soil
    # Compute Height
    mk_height = nodes.new("ComputeNodeGroup")
    mk_height.node_tree = bpy.data.node_groups.get("Combine Height")
    mk_height.location = (-500, -200)
    
    flow_w = nodes.new("ComputeNodeGroup")
    flow_w.node_tree = bpy.data.node_groups["Prodigy FD4 Weights"]
    flow_w.location = (-200, -200)
    
    # Connect
    # RepIn Bedrock -> MkHeight
    # RepIn Soil -> MkHeight
    links.new(rep_in.outputs["Bedrock"], mk_height.inputs["Bedrock"])
    links.new(rep_in.outputs["Soil"], mk_height.inputs["Soil"])
    
    links.new(mk_height.outputs["Height"], flow_w.inputs["Height"])
    
    # C. Flow Accumulation
    # Input: Water (from Rain), Weights
    flow_acc = nodes.new("ComputeNodeGroup")
    flow_acc.node_tree = bpy.data.node_groups["Prodigy Flow Acc"]
    flow_acc.location = (50, 200)
    
    # RepIn Water -> Rain -> FlowAcc
    links.new(rep_in.outputs["Water"], rain.inputs["Water"])
    links.new(rain.outputs["New Water"], flow_acc.inputs["Water"])
    links.new(flow_w.outputs["Flow Weights"], flow_acc.inputs["Flow Weights"])
    
    # D. Velocity Update using Gradient (Gradient from Height)
    # Need Gradient Group
    grad = nodes.new("ComputeNodeGroup")
    grad.node_tree = bpy.data.node_groups.get("Compute Gradient Advanced")
    grad.location = (-200, -400)
    links.new(mk_height.outputs["Height"], grad.inputs["Height"])
    
    vel_up = nodes.new("ComputeNodeGroup")
    vel_up.node_tree = bpy.data.node_groups.get("Velocity Update")
    vel_up.location = (300, -300)
    
    links.new(rep_in.outputs["Velocity"], vel_up.inputs["Velocity"])
    links.new(grad.outputs["Gradient"], vel_up.inputs["Gradient"])
    links.new(flow_acc.outputs["Accumulated"], vel_up.inputs["Water"])
    
    # E. Hydraulic Erosion
    hydro = nodes.new("ComputeNodeGroup")
    hydro.node_tree = bpy.data.node_groups.get("Hydraulic Erosion Advanced")
    hydro.location = (600, 0)
    
    links.new(rep_in.outputs["Soil"], hydro.inputs["Soil"])
    links.new(rep_in.outputs["Sediment"], hydro.inputs["Sediment"])
    links.new(vel_up.outputs["New Velocity"], hydro.inputs["Velocity"])
    links.new(flow_acc.outputs["Accumulated"], hydro.inputs["Water"])
    
    # F. Thermal Erosion
    thermal = nodes.new("ComputeNodeGroup")
    thermal.node_tree = bpy.data.node_groups.get("Thermal Erosion")
    thermal.location = (900, 100)
    
    links.new(hydro.outputs["New Soil"], thermal.inputs["Soil"])
    
    # G. Evaporation (Optional, closes the loop on water)
    evap = nodes.new("ComputeNodeGroup")
    evap.node_tree = bpy.data.node_groups.get("Evaporation")
    evap.location = (1100, 0)
    
    links.new(flow_acc.outputs["Accumulated"], evap.inputs["Water"])
    links.new(hydro.outputs["New Sediment"], evap.inputs["Sediment"])
    links.new(thermal.outputs["New Soil"], evap.inputs["Soil"])
    
    # TO REPEAT OUTPUT
    # Order: Bedrock, Soil, Water, Sediment, Velocity
    
    # Bedrock (Passthrough)
    links.new(rep_in.outputs["Bedrock"], rep_out.inputs["Bedrock"])
    
    # Soil (from Evap -> New Soil)
    links.new(evap.outputs["New Soil"], rep_out.inputs["Soil"])
    
    # Water (from Evap -> New Water)
    links.new(evap.outputs["New Water"], rep_out.inputs["Water"])
    
    # Sediment (from Evap -> New Sediment)
    links.new(evap.outputs["New Sediment"], rep_out.inputs["Sediment"])
    
    # Velocity (from Vel Up)
    links.new(vel_up.outputs["New Velocity"], rep_out.inputs["Velocity"])
    
    # 4. Final Output
    mk_height_final = nodes.new("ComputeNodeGroup")
    mk_height_final.node_tree = bpy.data.node_groups.get("Combine Height")
    mk_height_final.location = (1700, 0)
    
    links.new(rep_out.outputs["Bedrock"], mk_height_final.inputs["Bedrock"])
    links.new(rep_out.outputs["Soil"], mk_height_final.inputs["Soil"])
    
    out_img = nodes.new("ComputeNodeOutputImage")
    out_img.location = (1900, 0)
    links.new(mk_height_final.outputs["Height"], out_img.inputs["Grid"])
    
    print("Demo Graph Created!")

if __name__ == "__main__":
    setup_all()
