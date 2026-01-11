import bpy
import math

# =============================================================================
# UTILS
# =============================================================================

def get_or_create_tree(name: str) -> bpy.types.NodeTree:
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    return bpy.data.node_groups.new(name, 'ComputeNodeTree')

def clear_tree(tree: bpy.types.NodeTree):
    tree.nodes.clear()

def add_socket(tree, name, in_out, socket_type, default=None):
    # Depending on Blender version, interface might be via tree.interface or tree.inputs/outputs
    # For Compute Nodes (Blender 4.0+ style usually):
    item = tree.interface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None and hasattr(item, 'default_value'):
        item.default_value = default
    return item

def link(tree, from_node, from_socket, to_node, to_socket):
    try:
        out = from_node.outputs[from_socket] if isinstance(from_socket, (int, str)) else from_socket
        inp = to_node.inputs[to_socket] if isinstance(to_socket, (int, str)) else to_socket
        tree.links.new(out, inp)
    except Exception as e:
        print(f"LINK ERROR: {e}")
        print(f"  From: {from_node.name} . {from_socket}")
        # print keys
        if hasattr(from_node, 'outputs'): print(f"  Available Outputs: {from_node.outputs.keys()}")
        print(f"  To: {to_node.name} . {to_socket}")
        if hasattr(to_node, 'inputs'): print(f"  Available Inputs: {to_node.inputs.keys()}")
        raise e

def set_default(node, socket, value):
    try:
        if isinstance(socket, int):
            node.inputs[socket].default_value = value
        elif socket in node.inputs:
            node.inputs[socket].default_value = value
    except:
        pass

# =============================================================================
# TIER 1: MATH PRIMITIVES
# =============================================================================

def create_moore_neighbor_sample():
    """
    Samples a Grid at Center + 8 Neighbors (Moore Neighborhood).
    Inputs: Grid, UV
    Outputs: Values for C, N, S, E, W, NE, NW, SE, SW
    """
    tree_name = "CN Erosion Moore Sample"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    

    # Inputs
    tree.interface.clear() # Fix for re-runs
    add_socket(tree, "Grid", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "UV", "INPUT", "NodeSocketVector") # Or explicit Coordinates
    
    # Outputs
    outputs = ["Center", "N", "S", "E", "W", "NE", "NW", "SE", "SW"]
    for out_name in outputs:
        add_socket(tree, out_name, "OUTPUT", "NodeSocketFloat")
        
    nodes = tree.nodes
    
    # Nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-800, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (800, 0)
    
    # Calculate Pixel Size (dx, dy)
    # DEBUG: Hardcoding 1/512 to prevent NaN division inside loops
    # info = nodes.new("ComputeNodeImageInfo"); info.location = (-600, 200); info.label="Info_Moore"
    # link(tree, n_in, "Grid", info, "Grid")
    
    div_x = nodes.new("ComputeNodeMath"); div_x.operation = "ADD"; div_x.location = (-400, 200)
    div_x.inputs[0].default_value = 0.001953125 # 1/512
    # div_x.inputs[0].default_value = 1.0
    # link(tree, info, "Width", div_x, 1) # 1 / Width
    
    div_y = nodes.new("ComputeNodeMath"); div_y.operation = "ADD"; div_y.location = (-400, 100)
    div_y.inputs[0].default_value = 0.001953125 # 1/512
    # div_y.inputs[0].default_value = 1.0
    # link(tree, info, "Height", div_y, 1) # 1 / Height
    
    # We combine these into offsets
    # dx vector
    vec_dx = nodes.new("ComputeNodeCombineXYZ"); vec_dx.location = (-200, 200)
    link(tree, div_x, "Value", vec_dx, "X")
    
    # dy vector
    vec_dy = nodes.new("ComputeNodeCombineXYZ"); vec_dy.location = (-200, 100)
    link(tree, div_y, "Value", vec_dy, "Y")
    
    # Samples
    # Helper to sample at offset
    def sample_offset(name, x_mult, y_mult, loc_y):
        """Sample Grid at UV + offset (dx*x_mult, dy*y_mult)"""
        
        sampler = nodes.new("ComputeNodeSample"); sampler.location = (400, loc_y)
        sampler.label = f"Sample {name}"
        link(tree, n_in, "Grid", sampler, "Grid")
        
        # Coordinate
        if x_mult == 0 and y_mult == 0:
            # Center: sample at UV directly
            link(tree, n_in, "UV", sampler, "Coordinate")
        else:
            # Neighbor: sample at UV + offset
            # Build offset vector using CombineXYZ
            offset = nodes.new("ComputeNodeCombineXYZ"); offset.location = (100, loc_y)
            
            # X offset
            if x_mult == 0:
                offset.inputs["X"].default_value = 0.0
            elif x_mult == 1:
                link(tree, div_x, "Value", offset, "X")
            elif x_mult == -1:
                neg_x = nodes.new("ComputeNodeMath"); neg_x.operation = "MUL"; neg_x.location = (-50, loc_y)
                link(tree, div_x, "Value", neg_x, 0)
                neg_x.inputs[1].default_value = -1.0
                link(tree, neg_x, "Value", offset, "X")
            
            # Y offset
            if y_mult == 0:
                offset.inputs["Y"].default_value = 0.0
            elif y_mult == 1:
                link(tree, div_y, "Value", offset, "Y")
            elif y_mult == -1:
                neg_y = nodes.new("ComputeNodeMath"); neg_y.operation = "MUL"; neg_y.location = (-50, loc_y - 50)
                link(tree, div_y, "Value", neg_y, 0)
                neg_y.inputs[1].default_value = -1.0
                link(tree, neg_y, "Value", offset, "Y")
            
            # Add UV + offset
            add_vec = nodes.new("ComputeNodeVectorMath"); add_vec.operation = "ADD"; add_vec.location = (250, loc_y)
            link(tree, n_in, "UV", add_vec, 0)
            link(tree, offset, "Vector", add_vec, 1)
            link(tree, add_vec, "Vector", sampler, "Coordinate")
            
        link(tree, sampler, "Color", n_out, name)  # Link Color (auto-convert to Float)

        
    # Generate 9 samples
    y_start = 400
    y_step = -100
    
    # 0: Center
    sample_offset("Center", 0, 0, y_start); y_start+=y_step
    
    # Ortho
    sample_offset("N", 0, 1, y_start); y_start+=y_step
    sample_offset("S", 0, -1, y_start); y_start+=y_step
    sample_offset("E", 1, 0, y_start); y_start+=y_step
    sample_offset("W", -1, 0, y_start); y_start+=y_step
    
    # Diag
    sample_offset("NE", 1, 1, y_start); y_start+=y_step
    sample_offset("NW", -1, 1, y_start); y_start+=y_step
    sample_offset("SE", 1, -1, y_start); y_start+=y_step
    sample_offset("SW", -1, -1, y_start); y_start+=y_step
    
    n_out.location = (800, 0)
    return tree

def create_gradient_sobel():
    """
    Calculates Gradient Vector (SlopeX, SlopeY, 0) using 8 neighbors.
    Uses Sobel Operator.
    """
    tree_name = "CN Erosion Gradient Sobel"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    
    # Inputs: 9 values from Moore Sample
    input_names = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]
    for name in input_names:
        add_socket(tree, name, "INPUT", "NodeSocketFloat")

    add_socket(tree, "Cell Size", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Height Scale", "INPUT", "NodeSocketFloat", 1.0)
    
    # Output
    add_socket(tree, "Gradient", "OUTPUT", "NodeSocketVector")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1000, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1000, 0)
    
    # SOBEL X
    # (NE + 2E + SE) - (NW + 2W + SW)
    
    # Right (0, 0)
    add_ne_se = nodes.new("ComputeNodeMath"); add_ne_se.operation="ADD"; add_ne_se.location=(-600, 400)
    link(tree, n_in, "NE", add_ne_se, 0); link(tree, n_in, "SE", add_ne_se, 1)
    
    mul_e2 = nodes.new("ComputeNodeMath"); mul_e2.operation="MUL"; mul_e2.location=(-600, 300)
    link(tree, n_in, "E", mul_e2, 0); mul_e2.inputs[1].default_value = 2.0
    
    sum_right = nodes.new("ComputeNodeMath"); sum_right.operation="ADD"; sum_right.location=(-400, 350)
    link(tree, add_ne_se, "Value", sum_right, 0); link(tree, mul_e2, "Value", sum_right, 1)
    
    # Left (-600, 100)
    add_nw_sw = nodes.new("ComputeNodeMath"); add_nw_sw.operation="ADD"; add_nw_sw.location=(-600, 200)
    link(tree, n_in, "NW", add_nw_sw, 0); link(tree, n_in, "SW", add_nw_sw, 1)
    
    mul_w2 = nodes.new("ComputeNodeMath"); mul_w2.operation="MUL"; mul_w2.location=(-600, 100)
    link(tree, n_in, "W", mul_w2, 0); mul_w2.inputs[1].default_value = 2.0
    
    sum_left = nodes.new("ComputeNodeMath"); sum_left.operation="ADD"; sum_left.location=(-400, 150)
    link(tree, add_nw_sw, "Value", sum_left, 0); link(tree, mul_w2, "Value", sum_left, 1)
    
    diff_x = nodes.new("ComputeNodeMath"); diff_x.operation="SUB"; diff_x.location=(-200, 250)
    link(tree, sum_right, "Value", diff_x, 0); link(tree, sum_left, "Value", diff_x, 1)
    
    # SOBEL Y
    # Top
    add_nw_ne = nodes.new("ComputeNodeMath"); add_nw_ne.operation="ADD"; add_nw_ne.location=(-600, -100)
    link(tree, n_in, "NW", add_nw_ne, 0); link(tree, n_in, "NE", add_nw_ne, 1)
    
    mul_n2 = nodes.new("ComputeNodeMath"); mul_n2.operation="MUL"; mul_n2.location=(-600, -200)
    link(tree, n_in, "N", mul_n2, 0); mul_n2.inputs[1].default_value = 2.0
    
    sum_top = nodes.new("ComputeNodeMath"); sum_top.operation="ADD"; sum_top.location=(-400, -150)
    link(tree, add_nw_ne, "Value", sum_top, 0); link(tree, mul_n2, "Value", sum_top, 1)
    
    # Bottom
    add_sw_se = nodes.new("ComputeNodeMath"); add_sw_se.operation="ADD"; add_sw_se.location=(-600, -300)
    link(tree, n_in, "SW", add_sw_se, 0); link(tree, n_in, "SE", add_sw_se, 1)
    
    mul_s2 = nodes.new("ComputeNodeMath"); mul_s2.operation="MUL"; mul_s2.location=(-600, -400)
    link(tree, n_in, "S", mul_s2, 0); mul_s2.inputs[1].default_value = 2.0
    
    sum_bot = nodes.new("ComputeNodeMath"); sum_bot.operation="ADD"; sum_bot.location=(-400, -350)
    link(tree, add_sw_se, "Value", sum_bot, 0); link(tree, mul_s2, "Value", sum_bot, 1)
    
    diff_y = nodes.new("ComputeNodeMath"); diff_y.operation="SUB"; diff_y.location=(-200, -250)
    link(tree, sum_top, "Value", diff_y, 0); link(tree, sum_bot, "Value", diff_y, 1)
    
    # Scaling
    mul_8 = nodes.new("ComputeNodeMath"); mul_8.operation="MUL"; mul_8.location=(0, -50)
    link(tree, n_in, "Cell Size", mul_8, 0); mul_8.inputs[1].default_value = 8.0
    
    factor = nodes.new("ComputeNodeMath"); factor.operation="DIV"; factor.location=(200, -50)
    link(tree, n_in, "Height Scale", factor, 0); link(tree, mul_8, "Value", factor, 1)
    
    grad_x = nodes.new("ComputeNodeMath"); grad_x.operation="MUL"; grad_x.location=(400, 150)
    link(tree, diff_x, "Value", grad_x, 0); link(tree, factor, "Value", grad_x, 1)
    
    grad_y = nodes.new("ComputeNodeMath"); grad_y.operation="MUL"; grad_y.location=(400, -150)
    link(tree, diff_y, "Value", grad_y, 0); link(tree, factor, "Value", grad_y, 1)
    
    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location=(600, 0)
    link(tree, grad_x, "Value", comb, "X")
    link(tree, grad_y, "Value", comb, "Y")
    
    link(tree, comb, "Vector", n_out, "Gradient")
    return tree

# =============================================================================
# TIER 2: PHYSICS KERNELS
# =============================================================================

def create_hydraulic_flux_8way():
    """
    Virtual Pipe Model (8-way).
    Inputs: 
        Height (Grid)
        Water (Grid)
        FluxOrtho_In (Grid RGBA: N, S, E, W)
        FluxDiag_In (Grid RGBA: NE, NW, SE, SW)
        dt, pipe_len, gravity
    Outputs:
        FluxOrtho_Out
        FluxDiag_Out
    """
    tree_name = "CN Erosion Hydraulic Flux"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    # Inputs
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxOrtho In", "INPUT", "ComputeSocketGrid") # RGBA
    add_socket(tree, "FluxDiag In", "INPUT", "ComputeSocketGrid") # RGBA
    
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "Gravity", "INPUT", "NodeSocketFloat", 9.8)
    add_socket(tree, "Pipe Len", "INPUT", "NodeSocketFloat", 1.0) # Lx = Ly
    add_socket(tree, "Friction", "INPUT", "NodeSocketFloat", 0.5)
    
    # Outputs
    add_socket(tree, "FluxOrtho Out", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxDiag Out", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1200, 0)
    
    # 1. Sample Heights and Water at Moore Neighbors
    moore_h = nodes.new("ComputeNodeGroup"); moore_h.location=(-900, 200); moore_h.label="Moore Height"
    moore_h.node_tree = get_or_create_tree("CN Erosion Moore Sample")
    link(tree, n_in, "Height", moore_h, "Grid")
    
    moore_w = nodes.new("ComputeNodeGroup"); moore_w.location=(-900, -200); moore_w.label="Moore Water"
    moore_w.node_tree = get_or_create_tree("CN Erosion Moore Sample")
    link(tree, n_in, "Water", moore_w, "Grid")
    
    pos = nodes.new("ComputeNodePosition"); pos.location=(-1100, 300)
    link(tree, pos, "Normalized", moore_h, "UV")
    link(tree, pos, "Normalized", moore_w, "UV")
    
    # 2. Sample Current Flux (RGBA)
    s_flux_o = nodes.new("ComputeNodeSample"); s_flux_o.location=(-900, -400); s_flux_o.label="Sample Flux Ortho"
    link(tree, n_in, "FluxOrtho In", s_flux_o, "Grid")
    link(tree, pos, "Normalized", s_flux_o, "Coordinate")
    
    s_flux_d = nodes.new("ComputeNodeSample"); s_flux_d.location=(-900, -500); s_flux_d.label="Sample Flux Diag"
    link(tree, n_in, "FluxDiag In", s_flux_d, "Grid")
    link(tree, pos, "Normalized", s_flux_d, "Coordinate")
    
    # 3. Calculate Hydrostatic Pressure Difference
    def calc_pressure_delta(idx_name):
        add_c = nodes.new("ComputeNodeMath"); add_c.operation="ADD"
        link(tree, moore_h, "Center", add_c, 0); link(tree, moore_w, "Center", add_c, 1)
        
        add_n = nodes.new("ComputeNodeMath"); add_n.operation="ADD"
        link(tree, moore_h, idx_name, add_n, 0); link(tree, moore_w, idx_name, add_n, 1)
        
        diff = nodes.new("ComputeNodeMath"); diff.operation="SUB"
        link(tree, add_c, "Value", diff, 0); link(tree, add_n, "Value", diff, 1)
        return diff
        
    k_base = nodes.new("ComputeNodeMath"); k_base.operation="MUL"; k_base.location=(-600, 400)
    link(tree, n_in, "dt", k_base, 0); link(tree, n_in, "Gravity", k_base, 1)
    
    k_fact = nodes.new("ComputeNodeMath"); k_fact.operation="DIV"; k_fact.location=(-450, 400)
    link(tree, k_base, "Value", k_fact, 0); link(tree, n_in, "Pipe Len", k_fact, 1)
    
    k_diag = nodes.new("ComputeNodeMath"); k_diag.operation="DIV"; k_diag.location=(-300, 400)
    link(tree, k_fact, "Value", k_diag, 0); k_diag.inputs[1].default_value = 1.4142
    
    # 4. Update Flux
    sep_o = nodes.new("ComputeNodeSeparateColor"); sep_o.location=(-700, -400)
    link(tree, s_flux_o, "Color", sep_o, 0)
    
    sep_d = nodes.new("ComputeNodeSeparateColor"); sep_d.location=(-700, -500)
    link(tree, s_flux_d, "Color", sep_d, 0)
    
    def get_new_flux(old_val_socket, neighbor_name, is_diag):
        dt = calc_pressure_delta(neighbor_name)
        inc = nodes.new("ComputeNodeMath"); inc.operation="MUL"
        link(tree, dt, "Value", inc, 0)
        link(tree, k_diag if is_diag else k_fact, "Value", inc, 1)
        
        # Apply Friction: old * (1.0 - Friction * dt)
        f_rate = nodes.new("ComputeNodeMath"); f_rate.operation="MUL"; f_rate.location=(-500, -100)
        link(tree, n_in, "Friction", f_rate, 0); link(tree, n_in, "dt", f_rate, 1)
        
        f_sub = nodes.new("ComputeNodeMath"); f_sub.operation="SUB"; f_sub.location=(-500, -200)
        f_sub.inputs[0].default_value = 1.0; link(tree, f_rate, "Value", f_sub, 1)
        
        f_damp = nodes.new("ComputeNodeMath"); f_damp.operation="MUL"; f_damp.location=(-500, -300)
        link(tree, old_val_socket.node, old_val_socket, f_damp, 0); link(tree, f_sub, "Value", f_damp, 1)
        
        add = nodes.new("ComputeNodeMath"); add.operation="ADD"
        link(tree, f_damp, "Value", add, 0); link(tree, inc, "Value", add, 1)
        
        clamp = nodes.new("ComputeNodeMath"); clamp.operation="MAX"
        link(tree, add, "Value", clamp, 0); clamp.inputs[1].default_value=0.0
        return clamp
    
    # We will let these nodes float naturally or force execution, 
    # but since there are 8 of them, layout logic is tricky inside loops.
    # Blender will often auto-arrange newly added nodes if we don't set location,
    # but we can try to fan them out.
    
    f_n = get_new_flux(sep_o.outputs["Red"], "N", False); f_n.location=(-300, -100)
    f_s = get_new_flux(sep_o.outputs["Green"], "S", False); f_s.location=(-300, -200)
    f_e = get_new_flux(sep_o.outputs["Blue"], "E", False); f_e.location=(-300, -300)
    f_w = get_new_flux(sep_o.outputs["Alpha"], "W", False); f_w.location=(-300, -400)
    
    f_ne = get_new_flux(sep_d.outputs["Red"], "NE", True); f_ne.location=(-100, -100)
    f_nw = get_new_flux(sep_d.outputs["Green"], "NW", True); f_nw.location=(-100, -200)
    f_se = get_new_flux(sep_d.outputs["Blue"], "SE", True); f_se.location=(-100, -300)
    f_sw = get_new_flux(sep_d.outputs["Alpha"], "SW", True); f_sw.location=(-100, -400)
    
    # 5. Scaling (K limit)
    # Sum of all fluxes
    sum_1 = nodes.new("ComputeNodeMath"); sum_1.operation="ADD"; sum_1.location=(200, 150)
    link(tree, f_n, "Value", sum_1, 0); link(tree, f_s, "Value", sum_1, 1)
    sum_2 = nodes.new("ComputeNodeMath"); sum_2.operation="ADD"; sum_2.location=(200, 50)
    link(tree, f_e, "Value", sum_2, 0); link(tree, f_w, "Value", sum_2, 1)
    sum_3 = nodes.new("ComputeNodeMath"); sum_3.operation="ADD"; sum_3.location=(200, -50)
    link(tree, f_ne, "Value", sum_3, 0); link(tree, f_nw, "Value", sum_3, 1)
    sum_4 = nodes.new("ComputeNodeMath"); sum_4.operation="ADD"; sum_4.location=(200, -150)
    link(tree, f_se, "Value", sum_4, 0); link(tree, f_sw, "Value", sum_4, 1)
    
    tot_1 = nodes.new("ComputeNodeMath"); tot_1.operation="ADD"; tot_1.location=(400, 100)
    link(tree, sum_1, "Value", tot_1, 0); link(tree, sum_2, "Value", tot_1, 1)
    tot_2 = nodes.new("ComputeNodeMath"); tot_2.operation="ADD"; tot_2.location=(400, -100)
    link(tree, sum_3, "Value", tot_2, 0); link(tree, sum_4, "Value", tot_2, 1)
    
    total_flux = nodes.new("ComputeNodeMath"); total_flux.operation="ADD"; total_flux.location=(600, 0)
    link(tree, tot_1, "Value", total_flux, 0); link(tree, tot_2, "Value", total_flux, 1)
    
    # K = Min(1, Water / (TotalFlux + epsilon))
    eps = nodes.new("ComputeNodeMath"); eps.operation="ADD"; eps.location=(700, 100)
    link(tree, total_flux, "Value", eps, 0); eps.inputs[1].default_value = 1e-6

    div_w = nodes.new("ComputeNodeMath"); div_w.operation="DIV"; div_w.location=(800, 300)
    link(tree, moore_w, "Center", div_w, 0); link(tree, eps, "Value", div_w, 1)
    
    k_scale = nodes.new("ComputeNodeMath"); k_scale.operation="MIN"; k_scale.location=(1000, 300)
    link(tree, div_w, "Value", k_scale, 0); k_scale.inputs[1].default_value = 1.0
    
    def apply_k(node, x, y):
        m = nodes.new("ComputeNodeMath"); m.operation="MUL"; m.location=(x, y)
        link(tree, node, "Value", m, 0); link(tree, k_scale, "Value", m, 1)
        return m
        
    f_n_f = apply_k(f_n, 1200, 300); f_s_f = apply_k(f_s, 1200, 200)
    f_e_f = apply_k(f_e, 1200, 100); f_w_f = apply_k(f_w, 1200, 0)
    f_ne_f = apply_k(f_ne, 1200, -100); f_nw_f = apply_k(f_nw, 1200, -200)
    f_se_f = apply_k(f_se, 1200, -300); f_sw_f = apply_k(f_sw, 1200, -400)
    
    # 6. Capture Outputs
    comb_o = nodes.new("ComputeNodeCombineColor"); comb_o.location=(1400, 200)
    link(tree, f_n_f, "Value", comb_o, "Red")
    link(tree, f_s_f, "Value", comb_o, "Green")
    link(tree, f_e_f, "Value", comb_o, "Blue")
    link(tree, f_w_f, "Value", comb_o, "Alpha")
    
    comb_d = nodes.new("ComputeNodeCombineColor"); comb_d.location=(1400, -200)
    link(tree, f_ne_f, "Value", comb_d, "Red")
    link(tree, f_nw_f, "Value", comb_d, "Green")
    link(tree, f_se_f, "Value", comb_d, "Blue")
    link(tree, f_sw_f, "Value", comb_d, "Alpha")
    
    info = nodes.new("ComputeNodeImageInfo"); info.location=(1600, -500)
    link(tree, n_in, "Height", info, "Grid")
    
    cap_o = nodes.new("ComputeNodeCapture"); cap_o.location=(1800, 200)
    link(tree, comb_o, "Color", cap_o, "Field")
    link(tree, info, "Width", cap_o, "Width"); link(tree, info, "Height", cap_o, "Height")
    
    cap_d = nodes.new("ComputeNodeCapture"); cap_d.location=(1800, -200)
    link(tree, comb_d, "Color", cap_d, "Field")
    link(tree, info, "Width", cap_d, "Width"); link(tree, info, "Height", cap_d, "Height")
    
    n_out.location=(2000, 0)
    link(tree, cap_o, "Grid", n_out, "FluxOrtho Out")
    link(tree, cap_d, "Grid", n_out, "FluxDiag Out")
    
    return tree

def create_velocity_solve():
    """
    Calculates Velocity Vector from Flux.
    """
    tree_name = "CN Erosion Velocity Solve"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxOrtho", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxDiag", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1000, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1200, 0)
    pos = nodes.new("ComputeNodePosition"); pos.location=(-1000, 300)
    
    # Samples
    s_fo = nodes.new("ComputeNodeSample"); s_fo.location=(-800, 200)
    link(tree, n_in, "FluxOrtho", s_fo, "Grid"); link(tree, pos, "Normalized", s_fo, "Coordinate")
    
    s_fd = nodes.new("ComputeNodeSample"); s_fd.location=(-800, 0)
    link(tree, n_in, "FluxDiag", s_fd, "Grid"); link(tree, pos, "Normalized", s_fd, "Coordinate")
    
    s_wat = nodes.new("ComputeNodeSample"); s_wat.location=(-800, -200)
    link(tree, n_in, "Water", s_wat, "Grid"); link(tree, pos, "Normalized", s_wat, "Coordinate")
    
    sep_o = nodes.new("ComputeNodeSeparateColor"); sep_o.location=(-600, 200); link(tree, s_fo, "Color", sep_o, 0)
    sep_d = nodes.new("ComputeNodeSeparateColor"); sep_d.location=(-600, 0); link(tree, s_fd, "Color", sep_d, 0)
    
    sqrt2inv = 0.707
    
    # X
    sub_ew = nodes.new("ComputeNodeMath"); sub_ew.operation="SUB"; sub_ew.location=(-400, 300)
    link(tree, sep_o, "Blue", sub_ew, 0); link(tree, sep_o, "Alpha", sub_ew, 1) # E - W
    
    sum_diag_e = nodes.new("ComputeNodeMath"); sum_diag_e.operation="ADD"; sum_diag_e.location=(-400, 200)
    link(tree, sep_d, "Red", sum_diag_e, 0); link(tree, sep_d, "Blue", sum_diag_e, 1) # NE + SE
    
    sum_diag_w = nodes.new("ComputeNodeMath"); sum_diag_w.operation="ADD"; sum_diag_w.location=(-400, 100)
    link(tree, sep_d, "Green", sum_diag_w, 0); link(tree, sep_d, "Alpha", sum_diag_w, 1) # NW + SW
    
    sub_diag_x = nodes.new("ComputeNodeMath"); sub_diag_x.operation="SUB"; sub_diag_x.location=(-200, 150)
    link(tree, sum_diag_e, "Value", sub_diag_x, 0); link(tree, sum_diag_w, "Value", sub_diag_x, 1)
    
    scale_diag_x = nodes.new("ComputeNodeMath"); scale_diag_x.operation="MUL"; scale_diag_x.location=(0, 150)
    link(tree, sub_diag_x, "Value", scale_diag_x, 0); scale_diag_x.inputs[1].default_value = sqrt2inv
    
    total_x = nodes.new("ComputeNodeMath"); total_x.operation="ADD"; total_x.location=(200, 250)
    link(tree, sub_ew, "Value", total_x, 0); link(tree, scale_diag_x, "Value", total_x, 1)
    
    # Y
    sub_ns = nodes.new("ComputeNodeMath"); sub_ns.operation="SUB"; sub_ns.location=(-400, -100)
    link(tree, sep_o, "Red", sub_ns, 0); link(tree, sep_o, "Green", sub_ns, 1) # N - S
    
    sum_diag_n = nodes.new("ComputeNodeMath"); sum_diag_n.operation="ADD"; sum_diag_n.location=(-400, -200) 
    link(tree, sep_d, "Red", sum_diag_n, 0); link(tree, sep_d, "Green", sum_diag_n, 1) # NE + NW
    
    sum_diag_s = nodes.new("ComputeNodeMath"); sum_diag_s.operation="ADD"; sum_diag_s.location=(-400, -300) 
    link(tree, sep_d, "Blue", sum_diag_s, 0); link(tree, sep_d, "Alpha", sum_diag_s, 1) # SE + SW
    
    sub_diag_y = nodes.new("ComputeNodeMath"); sub_diag_y.operation="SUB"; sub_diag_y.location=(-200, -250)
    link(tree, sum_diag_n, "Value", sub_diag_y, 0); link(tree, sum_diag_s, "Value", sub_diag_y, 1)
    
    scale_diag_y = nodes.new("ComputeNodeMath"); scale_diag_y.operation="MUL"; scale_diag_y.location=(0, -250)
    link(tree, sub_diag_y, "Value", scale_diag_y, 0); scale_diag_y.inputs[1].default_value = sqrt2inv
    
    total_y = nodes.new("ComputeNodeMath"); total_y.operation="ADD"; total_y.location=(200, -150)
    link(tree, sub_ns, "Value", total_y, 0); link(tree, scale_diag_y, "Value", total_y, 1)
    
    wat_safe = nodes.new("ComputeNodeMath"); wat_safe.operation="MAX"; wat_safe.location=(-200, -400)
    link(tree, s_wat, "Color", wat_safe, 0); wat_safe.inputs[1].default_value=0.0001

    # Velocity (Pixel units per Step) = total_avg_flux / (Water * CellSize)
    eps = nodes.new("ComputeNodeMath"); eps.operation="ADD"; eps.location=(300, -200)
    link(tree, wat_safe, "Value", eps, 0); eps.inputs[1].default_value = 0.0001
    
    # We want velocity in PIXEL UNITS per step
    # total_x is volume/step. 
    # Velocity = total_x / (Water * CellSize)
    
    # Actually, simpler: just output Displacement (total_x / Water)
    # AND in Advect, divide by Resolution.
    
    vel_x = nodes.new("ComputeNodeMath"); vel_x.operation="DIV"; vel_x.location=(400, 100)
    link(tree, total_x, "Value", vel_x, 0); link(tree, eps, "Value", vel_x, 1)
    
    # Clamp Velocity to prevent teleportation (-10 to 10 pixels per step) using MIN/MAX
    max_vx = nodes.new("ComputeNodeMath"); max_vx.operation="MAX"; max_vx.location=(500, 150)
    link(tree, vel_x, "Value", max_vx, 0); max_vx.inputs[1].default_value = -10.0
    
    min_vx = nodes.new("ComputeNodeMath"); min_vx.operation="MIN"; min_vx.location=(550, 150)
    link(tree, max_vx, "Value", min_vx, 0); min_vx.inputs[1].default_value = 10.0
    clamp_vx = min_vx

    vel_y = nodes.new("ComputeNodeMath"); vel_y.operation="DIV"; vel_y.location=(400, -100)
    link(tree, total_y, "Value", vel_y, 0); link(tree, eps, "Value", vel_y, 1)
    
    max_vy = nodes.new("ComputeNodeMath"); max_vy.operation="MAX"; max_vy.location=(500, -150)
    link(tree, vel_y, "Value", max_vy, 0); max_vy.inputs[1].default_value = -10.0
    
    min_vy = nodes.new("ComputeNodeMath"); min_vy.operation="MIN"; min_vy.location=(550, -150)
    link(tree, max_vy, "Value", min_vy, 0); min_vy.inputs[1].default_value = 10.0
    clamp_vy = min_vy

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location=(600, 0)
    link(tree, clamp_vx, "Value", comb, "X"); link(tree, clamp_vy, "Value", comb, "Y")
    
    info = nodes.new("ComputeNodeImageInfo"); info.location=(400, 400); info.label="Info_Velocity"
    link(tree, n_in, "FluxOrtho", info, "Grid")
    
    cap = nodes.new("ComputeNodeCapture"); cap.location=(800, 0)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")
    
    n_out.location=(1000, 0)
    link(tree, cap, "Grid", n_out, "Velocity")
    return tree

# =============================================================================
# TIER 3: TRANSPORT & REACTION
# =============================================================================

def create_sediment_advect():
    """
    Semi-Lagrangian Advection of Sediment.
    NewSediment(x) = OldSediment(x - v*dt).
    """
    tree_name = "CN Erosion Sediment Advect"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1000, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1000, 0)
    
    # 1. Get Velocity at current pos
    pos = nodes.new("ComputeNodePosition"); pos.location=(-1000, 200)
    
    s_vel = nodes.new("ComputeNodeSample"); s_vel.location=(-800, 200)
    link(tree, n_in, "Velocity", s_vel, "Grid"); link(tree, pos, "Normalized", s_vel, "Coordinate")
    
    # 2. Calculate Backtrace UV
    # Velocity is displacement per step (in pixel-like units).
    # To get UV offset: displacement / resolution
    
    # Divide by Resolution
    info = nodes.new("ComputeNodeImageInfo"); info.location=(-800, 0); info.label="Info_Advect"
    link(tree, n_in, "Sediment", info, "Grid")
    
    # UV_offset = Velocity / Resolution
    div_w = nodes.new("ComputeNodeMath"); div_w.operation="DIV"; div_w.location=(-400, 100)
    sep_v = nodes.new("ComputeNodeSeparateXYZ"); sep_v.location=(-600, 100)
    link(tree, s_vel, "Color", sep_v, "Vector")
    link(tree, sep_v, "X", div_w, 0); link(tree, info, "Width", div_w, 1)
    
    div_h = nodes.new("ComputeNodeMath"); div_h.operation="DIV"; div_h.location=(-400, 0)
    link(tree, sep_v, "Y", div_h, 0); link(tree, info, "Height", div_h, 1)
    
    uv_off = nodes.new("ComputeNodeCombineXYZ"); uv_off.location=(-200, 50)
    link(tree, div_w, "Value", uv_off, "X"); link(tree, div_h, "Value", uv_off, "Y")
    
    new_uv = nodes.new("ComputeNodeVectorMath"); new_uv.operation="SUB"; new_uv.location=(0, 100)
    link(tree, pos, "Normalized", new_uv, 0); link(tree, uv_off, "Vector", new_uv, 1)
    
    # 3. Sample Sediment at new UV
    s_sed = nodes.new("ComputeNodeSample"); s_sed.location=(0, 0)
    link(tree, n_in, "Sediment", s_sed, "Grid")
    link(tree, new_uv, "Vector", s_sed, "Coordinate")
    
    # 4. Capture
    cap = nodes.new("ComputeNodeCapture"); cap.location=(300, 0)
    link(tree, s_sed, "Color", cap, "Field") # Sediment is Float inside Color R
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")
    
    n_out.location=(600, 0)
    link(tree, cap, "Grid", n_out, "New Sediment")
    return tree

def create_erosion_deposition():
    """
    Standard Capacity-based Erosion/Deposition.
    Updates Height, Sediment, Hardness.
    """
    tree_name = "CN Erosion Reaction"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Hardness", "INPUT", "ComputeSocketGrid")
    
    add_socket(tree, "K Erosion", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "K Deposit", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "Capacity", "INPUT", "NodeSocketFloat", 1.0) # Base capacity
    add_socket(tree, "Height Scale", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Cell Size", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.01)
    
    add_socket(tree, "New Height", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Hardness", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1200, 0)
    
    pos = nodes.new("ComputeNodePosition"); pos.location=(-1000, 400)
    
    # Sample Inputs
    # Sample Inputs
    def samp(sock_name, loc_y):
        s = nodes.new("ComputeNodeSample"); s.location=(-900, loc_y)
        link(tree, n_in, sock_name, s, "Grid"); link(tree, pos, "Normalized", s, "Coordinate")
        return s
        
    # DIRECT LINKING FIX (No Reroute)
    s_h = nodes.new("ComputeNodeSample"); s_h.location=(-900, 300)
    link(tree, n_in, "Height", s_h, "Grid"); link(tree, pos, "Normalized", s_h, "Coordinate")
    
    s_sed = samp("Sediment", 150)
    s_wat = samp("Water", 0)
    s_vel = samp("Velocity", -150)
    s_hard = samp("Hardness", -300)
    
    # Calculate Slope (Gradient).
    moore = nodes.new("ComputeNodeGroup"); moore.location=(-700, 500); moore.node_tree = get_or_create_tree("CN Erosion Moore Sample")
    link(tree, n_in, "Height", moore, "Grid"); link(tree, pos, "Normalized", moore, "UV")
    
    sob = nodes.new("ComputeNodeGroup"); sob.location=(-500, 500); sob.node_tree = get_or_create_tree("CN Erosion Gradient Sobel")
    input_names = ["N", "S", "E", "W", "NE", "NW", "SE", "SW"]
    for name in input_names:
        link(tree, moore, name, sob, name)
    
    link(tree, n_in, "Height Scale", sob, "Height Scale")
    link(tree, n_in, "Cell Size", sob, "Cell Size")

    grad_vec = sob # Output "Gradient"
    
    # Slope = Length(Gradient)
    len_slope = nodes.new("ComputeNodeVectorMath"); len_slope.operation="LENGTH"; len_slope.location=(-200, 500)
    link(tree, grad_vec, "Gradient", len_slope, 0)
    
    # Speed = Length(Velocity)
    len_vel = nodes.new("ComputeNodeVectorMath"); len_vel.operation="LENGTH"; len_vel.location=(-700, -150)
    link(tree, s_vel, "Color", len_vel, 0)
    
    # Capacity = K_cap * Speed * Water * Slope
    cap_1 = nodes.new("ComputeNodeMath"); cap_1.operation="MUL"; cap_1.location=(-400, 0)
    link(tree, n_in, "Capacity", cap_1, 0); link(tree, len_vel, "Value", cap_1, 1)
    
    cap_2 = nodes.new("ComputeNodeMath"); cap_2.operation="MUL"; cap_2.location=(-200, 0)
    link(tree, cap_1, "Value", cap_2, 0); link(tree, s_wat, "Color", cap_2, 1) # Water value
    
    cap_3 = nodes.new("ComputeNodeMath"); cap_3.operation="MUL"; cap_3.location=(0, 200)
    link(tree, cap_2, "Value", cap_3, 0); link(tree, len_slope, "Value", cap_3, 1)
    
    # Min Capacity (prevent 0)
    k_cap = nodes.new("ComputeNodeMath"); k_cap.operation="MAX"; k_cap.location=(200, 200)
    link(tree, cap_3, "Value", k_cap, 0); k_cap.inputs[1].default_value = 0.0001
    
    # Diff = Capacity - Sediment
    diff = nodes.new("ComputeNodeMath"); diff.operation="SUB"; diff.location=(400, 200)
    link(tree, k_cap, "Value", diff, 0); link(tree, s_sed, "Color", diff, 1)
    
    # Logic: Scale Diff by ErosionRate or DepositRate
    gt_0 = nodes.new("ComputeNodeMath"); gt_0.operation="GREATER_THAN"; gt_0.location=(600, 400)
    link(tree, diff, "Value", gt_0, 0); gt_0.inputs[1].default_value = 0.0
    
    # Branch Erosion (Positive Diff)
    # Erodability logic: Amount = Base * Hardness (where 1=Soft, 0=Hard?) 
    # Let's assume Hardness 1.0 = Bedrock (Very hard). So Factor = (1 - Hardness).
    
    one_minus = nodes.new("ComputeNodeMath"); one_minus.operation="SUB"; one_minus.location=(-400, -300)
    one_minus.inputs[0].default_value = 1.0; link(tree, s_hard, "Color", one_minus, 1)
    
    erode_base = nodes.new("ComputeNodeMath"); erode_base.operation="MUL"; erode_base.location=(600, 200)
    link(tree, diff, "Value", erode_base, 0); link(tree, n_in, "K Erosion", erode_base, 1)
    
    erode_amt = nodes.new("ComputeNodeMath"); erode_amt.operation="MUL"; erode_amt.location=(800, 200)
    link(tree, erode_base, "Value", erode_amt, 0); link(tree, one_minus, "Value", erode_amt, 1) 
    
    # Branch Deposition (Negative Diff)
    deposit_amt = nodes.new("ComputeNodeMath"); deposit_amt.operation="MUL"; deposit_amt.location=(800, 0)
    link(tree, diff, "Value", deposit_amt, 0); link(tree, n_in, "K Deposit", deposit_amt, 1)
    
    # Switch
    delta = nodes.new("ComputeNodeSwitch"); delta.location=(1000, 200)
    delta.input_type = 'FLOAT'
    link(tree, gt_0, "Value", delta, "Switch")
    link(tree, erode_amt, "Value", delta, "True")
    link(tree, deposit_amt, "Value", delta, "False")

    # Scale Delta by dt
    delta_dt = nodes.new("ComputeNodeMath"); delta_dt.operation="MUL"; delta_dt.location=(1100, 200)
    link(tree, delta, "Output", delta_dt, 0); link(tree, n_in, "dt", delta_dt, 1)
    
    # Apply Delta
    new_h_val = nodes.new("ComputeNodeMath"); new_h_val.operation="SUB"; new_h_val.location=(1300, 300)
    link(tree, s_h, "Color", new_h_val, 0); link(tree, delta_dt, "Value", new_h_val, 1)
    
    # Clamp H >= 0
    clamp_h = nodes.new("ComputeNodeMath"); clamp_h.operation="MAX"; clamp_h.location=(1500, 300)
    link(tree, new_h_val, "Value", clamp_h, 0); clamp_h.inputs[1].default_value = 0.0
    new_h_final = clamp_h

    new_s_val = nodes.new("ComputeNodeMath"); new_s_val.operation="ADD"; new_s_val.location=(1300, 100)
    link(tree, s_sed, "Color", new_s_val, 0); link(tree, delta_dt, "Value", new_s_val, 1)
    
    # Clamp S >= 0
    clamp_s = nodes.new("ComputeNodeMath"); clamp_s.operation="MAX"; clamp_s.location=(1500, 100)
    link(tree, new_s_val, "Value", clamp_s, 0); clamp_s.inputs[1].default_value = 0.0
    new_s_final = clamp_s
    
    # Update Hardness
    abs_d = nodes.new("ComputeNodeMath"); abs_d.operation="ABS"; abs_d.location=(1200, -100)
    link(tree, delta_dt, "Value", abs_d, 0)
    
    # Target Hardness
    target_h = nodes.new("ComputeNodeSwitch"); target_h.location=(1200, -300)
    target_h.input_type = 'FLOAT'
    link(tree, gt_0, "Value", target_h, "Switch")
    target_h.inputs["True"].default_value = 1.0 # Erode -> Bedrock
    target_h.inputs["False"].default_value = 0.0 # Deposit -> Sand
    
    # Compute Mix
    mix_h = nodes.new("ComputeNodeMix"); mix_h.location=(1400, -200); mix_h.data_type='FLOAT'
    link(tree, abs_d, "Value", mix_h, "Factor")
    link(tree, s_hard, "Color", mix_h, "A")
    link(tree, target_h, "Output", mix_h, "B")
    
    # Capture Results
    info = nodes.new("ComputeNodeImageInfo"); info.location=(1400, 500); info.label="Info_Erosion"
    link(tree, n_in, "Height", info, "Grid")
    
    def cap(val_node, name, y_loc):
        c = nodes.new("ComputeNodeCapture"); c.location=(1600, y_loc)
        # Simplify port selection
        port = "Value"
        if val_node.bl_idname == "ComputeNodeMix": port = "Result"
        elif val_node.bl_idname == "ComputeNodeSwitch": port = "Output"
        elif val_node.bl_idname == "ComputeNodeVectorMath": port = "Vector"
        elif val_node.bl_idname == "ComputeNodeSample": port = "Color"
        
        link(tree, val_node, port, c, "Field")
        link(tree, info, "Width", c, "Width"); link(tree, info, "Height", c, "Height")
        link(tree, c, "Grid", n_out, name)
        
    cap(new_h_final, "New Height", 200)
    cap(new_s_final, "New Sediment", 0)
    cap(mix_h, "New Hardness", -200)
    
    n_out.location=(1800, 0)
    return tree

# =============================================================================
# SOLVER ASSEMBLY
# =============================================================================

def create_water_update():
    """
    Updates Water depth.
    dWater = dt * (Sum(Flux_In) - Sum(Flux_Out) + Rain).
    Water *= (1 - Evaporation * dt)
    """
    tree_name = "CN Erosion Water Update"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxOrtho", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "FluxDiag", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "Rain", "INPUT", "NodeSocketFloat", 0.0)
    add_socket(tree, "Evaporation", "INPUT", "NodeSocketFloat", 0.0)
    
    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1200, 0)
    
    pos = nodes.new("ComputeNodePosition"); pos.location=(-1200, 300)
    
    # Helper to link from socket object
    def link_sock(sock, to_node, to_sock_idx):
        link(tree, sock.node, sock, to_node, to_sock_idx)
    
    # 1. Sample Flux Neighborhoods
    moore_o = nodes.new("ComputeNodeGroup"); moore_o.location=(-900, 200); moore_o.label="Moore Flux Ortho"
    moore_o.node_tree = get_or_create_tree("CN Erosion Moore Sample")
    link(tree, n_in, "FluxOrtho", moore_o, "Grid"); link(tree, pos, "Normalized", moore_o, "UV")
    
    moore_d = nodes.new("ComputeNodeGroup"); moore_d.location=(-900, -200); moore_d.label="Moore Flux Diag"
    moore_d.node_tree = get_or_create_tree("CN Erosion Moore Sample")
    link(tree, n_in, "FluxDiag", moore_d, "Grid"); link(tree, pos, "Normalized", moore_d, "UV")
    
    # 2. Extract Influx components
    def get_comp(socket, chan, y_loc):
        sep = nodes.new("ComputeNodeSeparateColor"); sep.location=(-700, y_loc)
        link_sock(socket, sep, 0)
        return sep.outputs[chan]
        
    in_n = get_comp(moore_o.outputs["N"], "Green", 400)
    in_s = get_comp(moore_o.outputs["S"], "Red", 300)
    in_e = get_comp(moore_o.outputs["E"], "Alpha", 200)
    in_w = get_comp(moore_o.outputs["W"], "Blue", 100)
    
    in_ne = get_comp(moore_d.outputs["NE"], "Alpha", -100)
    in_nw = get_comp(moore_d.outputs["NW"], "Blue", -200)
    in_se = get_comp(moore_d.outputs["SE"], "Green", -300)
    in_sw = get_comp(moore_d.outputs["SW"], "Red", -400)
    
    # Sum Influx
    sum_1 = nodes.new("ComputeNodeMath"); sum_1.operation="ADD"; sum_1.location=(-400, 350)
    link_sock(in_n, sum_1, 0); link_sock(in_s, sum_1, 1)
    
    sum_2 = nodes.new("ComputeNodeMath"); sum_2.operation="ADD"; sum_2.location=(-400, 250)
    link_sock(in_e, sum_2, 0); link_sock(in_w, sum_2, 1)
    
    sum_3 = nodes.new("ComputeNodeMath"); sum_3.operation="ADD"; sum_3.location=(-400, -250)
    link_sock(in_ne, sum_3, 0); link_sock(in_nw, sum_3, 1)
    
    sum_4 = nodes.new("ComputeNodeMath"); sum_4.operation="ADD"; sum_4.location=(-400, -350) 
    link_sock(in_se, sum_4, 0); link_sock(in_sw, sum_4, 1)
    
    tot_in_1 = nodes.new("ComputeNodeMath"); tot_in_1.operation="ADD"; tot_in_1.location=(-200, 300)
    link(tree, sum_1, "Value", tot_in_1, 0); link(tree, sum_2, "Value", tot_in_1, 1)
    
    tot_in_2 = nodes.new("ComputeNodeMath"); tot_in_2.operation="ADD"; tot_in_2.location=(-200, -300)
    link(tree, sum_3, "Value", tot_in_2, 0); link(tree, sum_4, "Value", tot_in_2, 1)
    
    flux_in = nodes.new("ComputeNodeMath"); flux_in.operation="ADD"; flux_in.location=(0, 0)
    link(tree, tot_in_1, "Value", flux_in, 0); link(tree, tot_in_2, "Value", flux_in, 1)
    
    # 3. Calculate Out Flux (Center)
    out_c_o = moore_o.outputs["Center"]
    out_c_d = moore_d.outputs["Center"]
    
    def sum_rgba(sock, y_loc):
        sep = nodes.new("ComputeNodeSeparateColor"); sep.location=(-600, y_loc)
        link_sock(sock, sep, 0)
        
        sum_rb = nodes.new("ComputeNodeMath"); sum_rb.operation="ADD"; sum_rb.location=(-400, y_loc + 50)
        link_sock(sep.outputs[0], sum_rb, 0); link_sock(sep.outputs[2], sum_rb, 1)
        
        sum_ga = nodes.new("ComputeNodeMath"); sum_ga.operation="ADD"; sum_ga.location=(-400, y_loc - 50)
        link_sock(sep.outputs[1], sum_ga, 0); link_sock(sep.outputs[3], sum_ga, 1)
        
        tot = nodes.new("ComputeNodeMath"); tot.operation="ADD"; tot.location=(-200, y_loc)
        link(tree, sum_rb, "Value", tot, 0); link(tree, sum_ga, "Value", tot, 1)
        return tot
        
    out_o = sum_rgba(out_c_o, 100)
    out_d = sum_rgba(out_c_d, -100)
    
    flux_out = nodes.new("ComputeNodeMath"); flux_out.operation="ADD"; flux_out.location=(0, -100)
    link(tree, out_o, "Value", flux_out, 0); link(tree, out_d, "Value", flux_out, 1)
    
    # 4. Net Change
    net = nodes.new("ComputeNodeMath"); net.operation="SUB"; net.location=(200, 0)
    link(tree, flux_in, "Value", net, 0); link(tree, flux_out, "Value", net, 1)
    
    # Add Rain (Rate * dt)
    rain_vol = nodes.new("ComputeNodeMath"); rain_vol.operation="MUL"; rain_vol.location=(400, 100)
    link(tree, n_in, "Rain", rain_vol, 0); link(tree, n_in, "dt", rain_vol, 1)
    
    # dv = net (Flux In - Flux Out) + RainVol
    dv = nodes.new("ComputeNodeMath"); dv.operation="ADD"; dv.location=(600, 0)
    link(tree, net, "Value", dv, 0); link(tree, rain_vol, "Value", dv, 1)
    
    # 5. New Water = Old + dv
    s_wat = nodes.new("ComputeNodeSample"); s_wat.location=(-900, -400)
    link(tree, n_in, "Water", s_wat, "Grid"); link(tree, pos, "Normalized", s_wat, "Coordinate")
    
    add_w = nodes.new("ComputeNodeMath"); add_w.operation="ADD"; add_w.location=(800, 0)
    link(tree, s_wat, "Color", add_w, 0); link(tree, dv, "Value", add_w, 1)
    
    # Apply Evaporation: Water * (1 - Evap*dt)
    
    # Evap factor
    evap_rate = nodes.new("ComputeNodeMath"); evap_rate.operation="MUL"; evap_rate.location=(600, -200)
    link(tree, n_in, "Evaporation", evap_rate, 0); link(tree, n_in, "dt", evap_rate, 1)
    
    one_minus_evap = nodes.new("ComputeNodeMath"); one_minus_evap.operation="SUB"; one_minus_evap.location=(800, -200)
    one_minus_evap.inputs[0].default_value = 1.0; link(tree, evap_rate, "Value", one_minus_evap, 1)
    
    w_evap = nodes.new("ComputeNodeMath"); w_evap.operation="MUL"; w_evap.location=(1000, 0)
    link(tree, add_w, "Value", w_evap, 0); link(tree, one_minus_evap, "Value", w_evap, 1)
    
    # Max(0)
    clamp_w = nodes.new("ComputeNodeMath"); clamp_w.operation="MAX"; clamp_w.location=(1200, 0)
    link(tree, w_evap, "Value", clamp_w, 0); clamp_w.inputs[1].default_value=0.0
    
    # Capture
    info = nodes.new("ComputeNodeImageInfo"); info.location=(1400, 200); info.label="Info_Water"
    link(tree, n_in, "Water", info, "Grid")
    
    cap = nodes.new("ComputeNodeCapture"); cap.location=(1600, 0)
    link(tree, clamp_w, "Value", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")
    
    n_out.location=(1800, 0)
    link(tree, cap, "Grid", n_out, "New Water")
    return tree

def create_solver_assembly():
    """
    Main Assembly: Repeat Zone orchestrating the physics loop.
    Self-initializes internal buffers to avoid unlinked-input errors.
    """
    tree_name = "CN Erosion Solver"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    # Inputs
    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Iterations", "INPUT", "NodeSocketInt", 10)
    add_socket(tree, "dt", "INPUT", "NodeSocketFloat", 0.05)
    
    # Physics Params
    add_socket(tree, "Gravity", "INPUT", "NodeSocketFloat", 9.8)
    add_socket(tree, "Pipe Len", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "K Erosion", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "K Deposit", "INPUT", "NodeSocketFloat", 0.1)
    add_socket(tree, "Capacity", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Height Scale", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Cell Size", "INPUT", "NodeSocketFloat", 1.0)
    add_socket(tree, "Rain", "INPUT", "NodeSocketFloat", 0.0)
    add_socket(tree, "Evaporation", "INPUT", "NodeSocketFloat", 0.0)
    add_socket(tree, "Friction", "INPUT", "NodeSocketFloat", 0.5)
    
    # Outputs
    add_socket(tree, "Height", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Hardness", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location=(-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location=(1200, 0)
    
    # --- Internal Initialization ---
    # We essentially need "Zero Grid" and "One Grid".
    
    # 1. Get Dims dynamically from Input Height
    # We must ensure this Info node evaluates before the Capture nodes.
    # The GraphExtractor should handle this dependency if linked correctly.
    info = nodes.new("ComputeNodeImageInfo"); info.location=(-1000, 200); info.label="Info_Solver_Init"
    link(tree, n_in, "Height", info, "Grid")

    # 2. Create Constant Fields
    # Zero (0.0)
    f_zero = nodes.new("ComputeNodeMath"); f_zero.operation="ADD"; f_zero.location=(-1000, 100)
    f_zero.inputs[0].default_value = 0.0
    f_zero.inputs[1].default_value = 0.0
    
    # Half (0.5) - For erodible soil
    f_half = nodes.new("ComputeNodeMath"); f_half.operation="ADD"; f_half.location=(-1000, 0)
    f_half.inputs[0].default_value = 0.5
    f_half.inputs[1].default_value = 0.0
    
    # 3. Capture Initial Grids using Dynamic Resolution
    def cap_init(val_node, name, y):
        c = nodes.new("ComputeNodeCapture"); c.location=(-800, y); c.label=f"Init {name}"
        link(tree, val_node, "Value", c, "Field")
        link(tree, info, "Width", c, "Width")
        link(tree, info, "Height", c, "Height")
        return c
        
    init_flux_o = cap_init(f_zero, "FluxOrtho", 100)
    init_flux_d = cap_init(f_zero, "FluxDiag", 0)
    init_water = cap_init(f_zero, "Water", -100)
    init_sed = cap_init(f_zero, "Sediment", -200)
    init_hard = cap_init(f_half, "Hardness", -300) # Default Soft Soil (0.5)
    
    # --- Repeat Zone ---
    
    rep_in = nodes.new("ComputeNodeRepeatInput"); rep_in.location=(-300, 0)
    rep_out = nodes.new("ComputeNodeRepeatOutput"); rep_out.location=(900, 0)
    
    rep_in.paired_output = rep_out.name
    rep_out.paired_input = rep_in.name
    
    link(tree, n_in, "Iterations", rep_in, "Iterations")
    
    # Define State
    
    rep_in.add_state("Height", "ComputeSocketGrid")
    link(tree, n_in, "Height", rep_in, "Height")
    
    rep_in.add_state("Water", "ComputeSocketGrid")
    link(tree, init_water, "Grid", rep_in, "Water")
    
    rep_in.add_state("Hardness", "ComputeSocketGrid")
    link(tree, init_hard, "Grid", rep_in, "Hardness")
    
    rep_in.add_state("Sediment", "ComputeSocketGrid")
    link(tree, init_sed, "Grid", rep_in, "Sediment")
    
    rep_in.add_state("FluxOrtho", "ComputeSocketGrid")
    link(tree, init_flux_o, "Grid", rep_in, "FluxOrtho")
    
    rep_in.add_state("FluxDiag", "ComputeSocketGrid")
    link(tree, init_flux_d, "Grid", rep_in, "FluxDiag")
    
    # --- INSIDE LOOP ---
    
    # 1. Hydraulic Flux
    hydro = nodes.new("ComputeNodeGroup"); hydro.location=(0, 200); hydro.label="Hydraulic Flux"
    hydro.node_tree = get_or_create_tree("CN Erosion Hydraulic Flux")
    
    link(tree, rep_in, "Height", hydro, "Height")
    link(tree, rep_in, "Water", hydro, "Water")
    link(tree, rep_in, "FluxOrtho", hydro, "FluxOrtho In")
    link(tree, rep_in, "FluxDiag", hydro, "FluxDiag In")
    link(tree, n_in, "dt", hydro, "dt")
    link(tree, n_in, "Gravity", hydro, "Gravity")
    link(tree, n_in, "Cell Size", hydro, "Pipe Len")
    link(tree, n_in, "Friction", hydro, "Friction")
    
    # 2. Water Update
    w_upd = nodes.new("ComputeNodeGroup"); w_upd.location=(250, 200); w_upd.label="Water Update"
    w_upd.node_tree = get_or_create_tree("CN Erosion Water Update")
    
    link(tree, rep_in, "Water", w_upd, "Water")
    link(tree, hydro, "FluxOrtho Out", w_upd, "FluxOrtho")
    link(tree, hydro, "FluxDiag Out", w_upd, "FluxDiag")
    link(tree, n_in, "dt", w_upd, "dt")
    link(tree, n_in, "Rain", w_upd, "Rain")
    link(tree, n_in, "Evaporation", w_upd, "Evaporation")
    
    # 3. Velocity Solve
    vel = nodes.new("ComputeNodeGroup"); vel.location=(0, -200); vel.label="Velocity Solve"
    vel.node_tree = get_or_create_tree("CN Erosion Velocity Solve")
    
    link(tree, w_upd, "New Water", vel, "Water")
    link(tree, hydro, "FluxOrtho Out", vel, "FluxOrtho")
    link(tree, hydro, "FluxDiag Out", vel, "FluxDiag")
    
    # 4. Sediment Advect
    adv = nodes.new("ComputeNodeGroup"); adv.location=(250, -200); adv.label="Advect Helper"
    adv.node_tree = get_or_create_tree("CN Erosion Sediment Advect")
    
    link(tree, rep_in, "Sediment", adv, "Sediment")
    link(tree, vel, "Velocity", adv, "Velocity")
    link(tree, n_in, "dt", adv, "dt")
    
    # 5. Erosion Reaction
    react = nodes.new("ComputeNodeGroup"); react.location=(500, 0); react.label="Reaction"
    react.node_tree = get_or_create_tree("CN Erosion Reaction")
    
    link(tree, rep_in, "Height", react, "Height")
    link(tree, adv, "New Sediment", react, "Sediment")
    link(tree, w_upd, "New Water", react, "Water")
    link(tree, vel, "Velocity", react, "Velocity")
    link(tree, rep_in, "Hardness", react, "Hardness")
    
    # Propagate Params
    link(tree, n_in, "K Erosion", react, "K Erosion")
    link(tree, n_in, "K Deposit", react, "K Deposit")
    link(tree, n_in, "Capacity", react, "Capacity")
    link(tree, n_in, "Height Scale", react, "Height Scale")
    link(tree, n_in, "Cell Size", react, "Cell Size")
    link(tree, n_in, "dt", react, "dt")
    
    # Link Next Iteration (Repeat Output)
    rep_out.location=(800, 0)
    link(tree, react, "New Height", rep_out, "Height")
    link(tree, w_upd, "New Water", rep_out, "Water")
    link(tree, react, "New Hardness", rep_out, "Hardness")
    link(tree, react, "New Sediment", rep_out, "Sediment")
    link(tree, hydro, "FluxOrtho Out", rep_out, "FluxOrtho")
    link(tree, hydro, "FluxDiag Out", rep_out, "FluxDiag")
    
    # Connect Final Outputs (Repeat Output -> Group Output)
    link(tree, rep_out, "Height", n_out, "Height")
    link(tree, rep_out, "Water", n_out, "Water")
    link(tree, rep_out, "Sediment", n_out, "Sediment")
    link(tree, rep_out, "Hardness", n_out, "Hardness")
    
    print(f"--- DEBUG: {tree_name} Nodes ---")
    for n in tree.nodes:
        # print(f"Node: {n.name} ({n.bl_idname}) Label: {n.label}")
        if n.bl_idname == "ComputeNodeImageInfo":
            inp = n.inputs["Grid"]
            # print(f"  Image Info Input 'Grid': Linked={inp.is_linked}")
            if inp.is_linked:
                l = inp.links[0]
                # print(f"    From: {l.from_node.name}.{l.from_socket.name}")
    
    return tree

def create_demo_setup():
    """
    Creates a runnable Demo Graph using the Erosion Solver.
    """
    tree_name = "Erosion Simulation Demo"
    tree = get_or_create_tree(tree_name)
    clear_tree(tree)
    tree.interface.clear()
    
    nodes = tree.nodes
    
    # 1. Generate Initial Terain (Noise)
    # We need a Grid.
    pos = nodes.new("ComputeNodePosition"); pos.location=(-600, 200)
    noise = nodes.new("ComputeNodeNoiseTexture"); noise.location=(-400, 200)
    
    # User Request: Use Normalized Coordinates
    link(tree, pos, "Normalized", noise, "Vector")
    
    # User Request: Params (Scale=2, Detail=8, Roughness=0.45)
    noise.inputs["Scale"].default_value = 2.0
    noise.inputs["Detail"].default_value = 8.0
    noise.inputs["Roughness"].default_value = 0.45
    
    # Capture it to make a Grid
    cap_h = nodes.new("ComputeNodeCapture"); cap_h.location=(-200, 200); cap_h.label="Init Height"
    cap_h.inputs["Width"].default_value = 512 # Higher res for detail
    cap_h.inputs["Height"].default_value = 512
    link(tree, noise, "Color", cap_h, "Field") # Noise Color.r as Height
    
    # 2. Solver
    solver = nodes.new("ComputeNodeGroup"); solver.location=(100, 0); solver.label="Solver"
    solver.node_tree = get_or_create_tree("CN Erosion Solver")
    
    link(tree, cap_h, "Grid", solver, "Height")
    
    # 3. Set Defaults (High Fidelity)
    set_default(solver, "Iterations", 200)
    set_default(solver, "dt", 0.01)          # Smaller dt for better stability
    set_default(solver, "Gravity", 9.8)     
    set_default(solver, "Cell Size", 0.002) 
    set_default(solver, "Height Scale", 1.0)
    
    set_default(solver, "K Erosion", 0.5)   
    set_default(solver, "K Deposit", 0.5)   
    set_default(solver, "Capacity", 8.0)   
    
    set_default(solver, "Rain", 0.01)       
    set_default(solver, "Evaporation", 0.01)
    set_default(solver, "Friction", 0.1)
    # Low friction = more momentum
    
    # 4. Output
    out_img = nodes.new("ComputeNodeOutputImage"); out_img.location=(400, 0)
    # DEBUG: Show SEDIMENT to see if dirt is effectively moving
    link(tree, solver, "Sediment", out_img, "Grid")
    
    print(f"Created Demo Setup: {tree_name}")
    return tree

if __name__ == "__main__":
    create_moore_neighbor_sample()
    create_gradient_sobel()
    create_hydraulic_flux_8way()
    create_velocity_solve()
    create_sediment_advect()
    create_erosion_deposition()
    create_water_update()
    create_solver_assembly()
    create_demo_setup()
