
import bpy
import random

# =============================================================================
# UTILS (Copied from Prodigy)
# =============================================================================

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

def _sample_with_offset(tree, grid_socket_node, grid_socket_name, info, pos_node, dx_pix, dy_pix, loc):
    comb_off = tree.nodes.new("ComputeNodeCombineXYZ")
    comb_off.location = (loc[0], loc[1])

    pix_x = tree.nodes.new("ComputeNodeMath")
    pix_x.operation = "DIV"
    pix_x.location = (loc[0]-220, loc[1]+60)
    set_default(pix_x, 0, float(dx_pix))
    link(tree, info, "Width", pix_x, 1)

    pix_y = tree.nodes.new("ComputeNodeMath"); pix_y.operation = "DIV"; pix_y.location = (loc[0]-220, loc[1]-60)
    set_default(pix_y, 0, float(dy_pix))
    link(tree, info, "Height", pix_y, 1)

    link(tree, pix_x, "Value", comb_off, "X"); link(tree, pix_y, "Value", comb_off, "Y")

    pos_off = tree.nodes.new("ComputeNodeVectorMath"); pos_off.operation = "ADD"; pos_off.location = (loc[0]+220, loc[1])
    link(tree, pos_node, "Normalized", pos_off, 0); link(tree, comb_off, "Vector", pos_off, 1)

    s = tree.nodes.new("ComputeNodeSample"); s.location = (loc[0]+420, loc[1])
    link(tree, grid_socket_node, grid_socket_name, s, "Grid")
    link(tree, pos_off, "Vector", s, "Coordinate")
    return s

# =============================================================================
# MULTI-LAYER SOLVER
# =============================================================================

def create_multilayer_solver():
    """
    Multi-Layer Erosion Solver (Bedrock + Sand).
    
    Principles:
    1. Water has 'Capacity' to carry sediment.
    2. Capacity depends on Velocity and Slope.
    3. If Capacity > Sediment -> Erode.
       - Prefer eroding Sand first (soft).
       - If Sand runs out, erode Bedrock (hard).
    4. If Capacity < Sediment -> Deposit.
       - Deposit 'Sediment' into 'Sand' layer.
    """
    tree = get_or_create_tree("Prodigy MultiLayer Solver")
    clear_tree(tree)
    tree.interface.clear()
    
    # Inputs
    add_socket(tree, "Bedrock", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sand", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Vel Mag", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Slope", "INPUT", "ComputeSocketGrid")
    
    # Parameters
    add_socket(tree, "Capacity K", "INPUT", "NodeSocketFloat", 2.0)
    add_socket(tree, "Sand Erodibility", "INPUT", "NodeSocketFloat", 0.5)
    add_socket(tree, "Rock Erodibility", "INPUT", "NodeSocketFloat", 0.05)
    add_socket(tree, "Deposition Rate", "INPUT", "NodeSocketFloat", 0.1)
    
    # Outputs
    add_socket(tree, "New Bedrock", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sand", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")
    
    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1600, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1600, 0)
    
    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1400, -300)
    link(tree, n_in, "Bedrock", info, "Grid")
    pos = nodes.new("ComputeNodePosition"); pos.location = (-1400, 200)
    
    # Sample all inputs
    def samp(name, y):
        s = nodes.new("ComputeNodeSample"); s.location = (-1200, y)
        link(tree, n_in, name, s, "Grid"); link(tree, pos, "Normalized", s, "Coordinate")
        return s
        
    s_bed  = samp("Bedrock", 400)
    s_sand = samp("Sand", 200)
    
    s_wat  = samp("Water", 0)
    s_sed  = samp("Sediment", -200)
    s_vel  = samp("Vel Mag", -400)
    s_slp  = samp("Slope", -600)
    
    # ---------------------------------------------------------
    # 1. Calc Transport Capacity
    # Capacity = K * Vel * Slope * Water
    # ---------------------------------------------------------
    mul1 = nodes.new("ComputeNodeMath"); mul1.operation="MUL"; mul1.location = (-900, -300)
    link(tree, s_vel, "Color", mul1, 0); link(tree, s_slp, "Color", mul1, 1)
    
    mul2 = nodes.new("ComputeNodeMath"); mul2.operation="MUL"; mul2.location = (-720, -300)
    link(tree, mul1, "Value", mul2, 0); link(tree, s_wat, "Color", mul2, 1)
    
    cap = nodes.new("ComputeNodeMath"); cap.operation="MUL"; cap.location = (-540, -300)
    link(tree, mul2, "Value", cap, 0); link(tree, n_in, "Capacity K", cap, 1)
    
    # Diff = Capacity - Sediment
    diff = nodes.new("ComputeNodeMath"); diff.operation="SUB"; diff.location = (-360, -300)
    link(tree, cap, "Value", diff, 0); link(tree, s_sed, "Color", diff, 1)
    
    # ---------------------------------------------------------
    # 2. Logic Split: Erosion vs Deposition
    # ---------------------------------------------------------
    
    # ErodeAmount = Max(0, Diff)
    erode_req = nodes.new("ComputeNodeMath"); erode_req.operation="MAX"; erode_req.location = (-180, -200)
    link(tree, diff, "Value", erode_req, 0); set_default(erode_req, 1, 0.0)
    
    # DepositAmount = Max(0, -Diff) * Rate
    neg_diff = nodes.new("ComputeNodeMath"); neg_diff.operation="SUB"; neg_diff.location = (-360, -500)
    set_default(neg_diff, 0, 0.0); link(tree, diff, "Value", neg_diff, 1) # 0 - Diff
    
    deposit_base = nodes.new("ComputeNodeMath"); deposit_base.operation="MAX"; deposit_base.location = (-180, -500)
    link(tree, neg_diff, "Value", deposit_base, 0); set_default(deposit_base, 1, 0.0)
    
    deposit_amt = nodes.new("ComputeNodeMath"); deposit_amt.operation="MUL"; deposit_amt.location = (0, -500)
    link(tree, deposit_base, "Value", deposit_amt, 0); link(tree, n_in, "Deposition Rate", deposit_amt, 1)
    
    # ---------------------------------------------------------
    # 3. Multi-Layer Erosion Logic
    # We want to erode 'erode_req' amount.
    # Take from Sand first. Then Bedrock.
    # ---------------------------------------------------------
    
    # Available Sand to erode?
    # SandErosion = Min(Sand, ErodeReq * SandErodability)
    # Note: We scale ErodeReq by erodibility here.
    
    req_sand = nodes.new("ComputeNodeMath"); req_sand.operation="MUL"; req_sand.location = (0, -200)
    link(tree, erode_req, "Value", req_sand, 0); link(tree, n_in, "Sand Erodibility", req_sand, 1)
    
    actual_sand_erosion = nodes.new("ComputeNodeMath"); actual_sand_erosion.operation="MIN"; actual_sand_erosion.location = (180, -200)
    link(tree, req_sand, "Value", actual_sand_erosion, 0); link(tree, s_sand, "Color", actual_sand_erosion, 1)
    
    # Remaining Req = ErodeReq - (SandErosion / SandErodability)?
    # Actually simpler logic:
    # If we depleted sand (Sand < Req), we try to erode bedrock.
    # But scaling by 'Erodibility' complicates "Remaining".
    # Let's simplify:
    # We have 'Potential Erosion' P = Diff.
    # Try to satisfy P using Sand.
    #   SandTaken = Min(Sand, P * SandRate)
    #   Unsatisfied P_residual = P - (SandTaken / SandRate) ... this is messy mathematically.
    
    # Alternative Logic (SoilMachine-ish):
    # Erode Sand: E_sand = P * SandRate.
    # Erode Bedrock: E_rock = P * RockRate.
    # RealSandErosion = Min(Sand, E_sand).
    # Did we penetrate? If RealSandErosion < E_sand (meaning Sand was small), we might erode bedrock?
    # Let's stick to strict layering:
    # 1. Calculate SandErosion = Min(Sand, ErodeReq * SandRate)
    # 2. Check if Sand was depleted (Sand < Epsilon?).
    #    If Sand is 0, we erode bedrock.
    #    If Sand > 0, we protect bedrock.
    # This creates a hard mask.
    
    # Is Sand Depleted? (Sand < epsilon)
    # Using 0.0001
    sand_eps = nodes.new("ComputeNodeMath"); sand_eps.operation="LESS_THAN"; sand_eps.location = (0, 0)
    link(tree, s_sand, "Color", sand_eps, 0); set_default(sand_eps, 1, 0.0001)
    
    # Bedrock Erosion = (ErodeReq * RockRate) * IsSandDepleted
    req_rock = nodes.new("ComputeNodeMath"); req_rock.operation="MUL"; req_rock.location = (180, 0)
    link(tree, erode_req, "Value", req_rock, 0); link(tree, n_in, "Rock Erodibility", req_rock, 1)
    
    actual_rock_erosion = nodes.new("ComputeNodeMath"); actual_rock_erosion.operation="MUL"; actual_rock_erosion.location = (360, 0)
    link(tree, req_rock, "Value", actual_rock_erosion, 0); link(tree, sand_eps, "Value", actual_rock_erosion, 1)
    
    # ---------------------------------------------------------
    # 4. Apply Changes
    # ---------------------------------------------------------
    
    # New Sand = Sand - SandErosion + DepositAmount
    sand_sub = nodes.new("ComputeNodeMath"); sand_sub.operation="SUB"; sand_sub.location = (600, 200)
    link(tree, s_sand, "Color", sand_sub, 0); link(tree, actual_sand_erosion, "Value", sand_sub, 1)
    
    sand_add = nodes.new("ComputeNodeMath"); sand_add.operation="ADD"; sand_add.location = (780, 200)
    link(tree, sand_sub, "Value", sand_add, 0); link(tree, deposit_amt, "Value", sand_add, 1)
    
    # Clamp
    new_sand = nodes.new("ComputeNodeMath"); new_sand.operation="MAX"; new_sand.location = (960, 200)
    link(tree, sand_add, "Value", new_sand, 0); set_default(new_sand, 1, 0.0)
    
    # New Bedrock = Bedrock - RockErosion
    bed_sub = nodes.new("ComputeNodeMath"); bed_sub.operation="SUB"; bed_sub.location = (600, 400)
    link(tree, s_bed, "Color", bed_sub, 0); link(tree, actual_rock_erosion, "Value", bed_sub, 1)
    
    # Clamp
    new_bed = nodes.new("ComputeNodeMath"); new_bed.operation="MAX"; new_bed.location = (960, 400)
    link(tree, bed_sub, "Value", new_bed, 0); set_default(new_bed, 1, 0.0)
    
    # New Sediment = Sediment + SandErosion + RockErosion - DepositAmount
    sed_add1 = nodes.new("ComputeNodeMath"); sed_add1.operation="ADD"; sed_add1.location = (600, -100)
    link(tree, s_sed, "Color", sed_add1, 0); link(tree, actual_sand_erosion, "Value", sed_add1, 1)
    
    sed_add2 = nodes.new("ComputeNodeMath"); sed_add2.operation="ADD"; sed_add2.location = (780, -100)
    link(tree, sed_add1, "Value", sed_add2, 0); link(tree, actual_rock_erosion, "Value", sed_add2, 1)
    
    sed_sub = nodes.new("ComputeNodeMath"); sed_sub.operation="SUB"; sed_sub.location = (960, -100)
    link(tree, sed_add2, "Value", sed_sub, 0); link(tree, deposit_amt, "Value", sed_sub, 1)
    
    # Clamp
    new_sed = nodes.new("ComputeNodeMath"); new_sed.operation="MAX"; new_sed.location = (1140, -100)
    link(tree, sed_sub, "Value", new_sed, 0); set_default(new_sed, 1, 0.0)

    # Capture outputs
    def cap(val_node, name, y):
        comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (1300, y)
        link(tree, val_node, "Value", comb, "X"); link(tree, val_node, "Value", comb, "Y"); link(tree, val_node, "Value", comb, "Z")
        c = nodes.new("ComputeNodeCapture"); c.location = (1450, y)
        link(tree, comb, "Vector", c, "Field")
        link(tree, info, "Width", c, "Width"); link(tree, info, "Height", c, "Height")
        link(tree, c, "Grid", n_out, name)
    
    cap(new_bed, "New Bedrock", 400)
    cap(new_sand, "New Sand", 200)
    cap(new_sed, "New Sediment", -100)
    
    return tree

# =============================================================================
# DEMO GRAPH
# =============================================================================

def create_multilayer_demo():
    """Create the Main Demo Graph using Multi-Layer approach."""
    tree = get_or_create_tree("Erosion MultiLayer Demo")
    clear_tree(tree)
    
    nodes = tree.nodes
    
    # 1. Inputs
    # -------------------------------------------------------------------------
    # Initial Noise for Bedrock
    noise = nodes.new("ComputeNodeNoiseTexture")
    noise.location = (-1200, 200)
    noise.inputs["Scale"].default_value = 4.0
    noise.inputs["Detail"].default_value = 6.0
    
    # Scale Height (0..1 -> 0..15)
    h_scale = nodes.new("ComputeNodeMath"); h_scale.operation="MUL"; h_scale.location=(-1000, 200)
    link(tree, noise, "Color", h_scale, 0); set_default(h_scale, 1, 15.0)

    # Capture Bedrock Init
    cap_bed = nodes.new("ComputeNodeCapture"); cap_bed.location=(-800, 200); cap_bed.label="Init Bedrock"
    cap_bed.inputs["Width"].default_value = 512; cap_bed.inputs["Height"].default_value = 512
    link(tree, h_scale, "Value", cap_bed, "Field")

    # Initial Sand (Zero)
    cap_sand = nodes.new("ComputeNodeCapture"); cap_sand.location=(-800, 0); cap_sand.label="Init Sand"
    cap_sand.inputs["Width"].default_value = 512; cap_sand.inputs["Height"].default_value = 512
    # Default is 0, so no link needed (or link strict 0)

    # 2. Main Loop
    # -------------------------------------------------------------------------
    rep_in = nodes.new("ComputeNodeRepeatInput"); rep_in.location = (-400, 0)
    rep_out = nodes.new("ComputeNodeRepeatOutput"); rep_out.location = (1600, 0)
    
    # States
    rep_in.add_state("Bedrock", "ComputeSocketGrid")
    rep_in.add_state("Sand", "ComputeSocketGrid")
    rep_in.add_state("Water", "ComputeSocketGrid")
    rep_in.add_state("Sediment", "ComputeSocketGrid")
    print(f"Repeat Items: {[item.name for item in rep_in.repeat_items]}")
    print(f"Repeat Outputs: {rep_in.outputs.keys()}")
    
    # Connect Init
    link(tree, cap_bed, "Grid", rep_in, "Bedrock")
    link(tree, cap_sand, "Grid", rep_in, "Sand")
    
    # Sync Output
    rep_out.paired_input = rep_in.name
    rep_in._sync_paired_output()
    
    # -------------------------------------------------------------------------
    # Loop Body
    # -------------------------------------------------------------------------
    
    # Step A: Combine Height (Bedrock + Sand)
    # We can reuse prodigy's "Combine Height" or just Add
    
    # Manual Add + Capture for simplicity (ensure graph self-contained)
    comb_info = nodes.new("ComputeNodeImageInfo"); comb_info.location = (-200, -300)
    link(tree, rep_in, "Bedrock", comb_info, "Grid")
    comb_pos = nodes.new("ComputeNodePosition"); comb_pos.location = (-200, 200)
    
    s_b = nodes.new("ComputeNodeSample"); s_b.location = (0, 300)
    link(tree, rep_in, "Bedrock", s_b, "Grid"); link(tree, comb_pos, "Normalized", s_b, "Coordinate")
    
    s_s = nodes.new("ComputeNodeSample"); s_s.location = (0, 150)
    link(tree, rep_in, "Sand", s_s, "Grid"); link(tree, comb_pos, "Normalized", s_s, "Coordinate")
    
    add_h = nodes.new("ComputeNodeMath"); add_h.operation="ADD"; add_h.location=(200, 220)
    link(tree, s_b, "Color", add_h, 0); link(tree, s_s, "Color", add_h, 1)
    
    # Capture Total Height
    cap_h = nodes.new("ComputeNodeCapture"); cap_h.location=(400, 220); cap_h.label="Total Height"
    link(tree, add_h, "Value", cap_h, "Field")
    link(tree, comb_info, "Width", cap_h, "Width"); link(tree, comb_info, "Height", cap_h, "Height")
    
    # Step B: Add Rain
    # Reusing prodigy "Prodigy Add Rain" if available, else assuming it's imported
    # We will assume this script is alongside `erosion_prodigy_improved_v3.py` or just recreate node
    # For now, let's assume we can load "Prodigy Add Rain" or similar.
    # To be safe, I'll instantiate "Prodigy Add Rain" node group, assuming the USER has run the other script
    # OR I should define it here. Since I didn't copy `create_add_rain`, I should define it.
    # Wait, I didn't copy it in the text above. I should have.
    # I will just inline the rain addition.
    
    curr_wat = rep_in.outputs["Water"] # Keep ref for variable reuse if needed (but unneeded for link)
    s_wat = nodes.new("ComputeNodeSample"); s_wat.location=(0, 0)
    link(tree, rep_in, "Water", s_wat, "Grid"); link(tree, comb_pos, "Normalized", s_wat, "Coordinate")
    
    wat_add = nodes.new("ComputeNodeMath"); wat_add.operation="ADD"; wat_add.location=(200, 0)
    link(tree, s_wat, "Color", wat_add, 0); wat_add.inputs[1].default_value = 0.005 # Rain Rate
    
    cap_wat = nodes.new("ComputeNodeCapture"); cap_wat.location=(400, 0); cap_wat.label="Rain Water"
    link(tree, wat_add, "Value", cap_wat, "Field")
    link(tree, comb_info, "Width", cap_wat, "Width"); link(tree, comb_info, "Height", cap_wat, "Height")
    
    # Step C: Gradient FD
    # Need gradient of Height.
    # Loading "Prodigy Gradient FD" assuming it exists (common library).
    # If not, this will fail. Better to define it or `import erosion_prodigy_improved_v3`?
    # I will import the module to ensure groups exist.
    
    grad_node = nodes.new("ComputeNodeGroup"); grad_node.location=(600, 200)
    grad_node.node_tree = bpy.data.node_groups.get("Prodigy Gradient FD")
    # If None, we rely on user running setup. I will add setup call at bottom.
    link(tree, cap_h, "Grid", grad_node, "Height")
    
    # Step D: Pipe Flow (Water Transport)
    pipe_node = nodes.new("ComputeNodeGroup"); pipe_node.location=(600, 0)
    pipe_node.node_tree = bpy.data.node_groups.get("Prodigy Pipe Flow Step")
    # link(tree, cap_surf, "Grid", pipe_node, "Surface") # REMOVED: Premature usage
    # Wait, Pipe Flow expects Surface = Height + Water.
    # I need to add Water to Height first?
    # "Prodigy Pipe Flow Step" usually expects 'Surface' which decides flow direction.
    # Ideally Surface = Bedrock + Sand + Water.
    # Let's add Water to Height.
    
    s_h_tot = nodes.new("ComputeNodeSample"); s_h_tot.location=(450, 100)
    link(tree, cap_h, "Grid", s_h_tot, "Grid"); link(tree, comb_pos, "Normalized", s_h_tot, "Coordinate")
    s_w_rain = nodes.new("ComputeNodeSample"); s_w_rain.location=(450, -50)
    link(tree, cap_wat, "Grid", s_w_rain, "Grid"); link(tree, comb_pos, "Normalized", s_w_rain, "Coordinate")
    
    surf_add = nodes.new("ComputeNodeMath"); surf_add.operation="ADD"; surf_add.location=(580, 50)
    link(tree, s_h_tot, "Color", surf_add, 0); link(tree, s_w_rain, "Color", surf_add, 1)
    
    cap_surf = nodes.new("ComputeNodeCapture"); cap_surf.location=(700, 50); cap_surf.label="Surface Level"
    link(tree, surf_add, "Value", cap_surf, "Field"); link(tree, comb_info, "Width", cap_surf, "Width"); link(tree, comb_info, "Height", cap_surf, "Height")
    
    link(tree, cap_surf, "Grid", pipe_node, "Surface")
    link(tree, cap_wat, "Grid", pipe_node, "Water")
    pipe_node.inputs["Flow Rate"].default_value = 0.2
    
    # Step E: Multi-Layer Sediment Solver
    solver = nodes.new("ComputeNodeGroup"); solver.location=(900, 0)
    solver.node_tree = get_or_create_tree("Prodigy MultiLayer Solver") # The one we defined above
    
    link(tree, rep_in, "Bedrock", solver, "Bedrock")
    link(tree, rep_in, "Sand", solver, "Sand")
    link(tree, pipe_node, "New Water", solver, "Water")
    link(tree, rep_in, "Sediment", solver, "Sediment") # Sediment from loop
    # Wait, rep_in.outputs["Sediment"] is a Socket.
    # link(tree, rep_in.outputs["Sediment"], solver, "Sediment") -> BROKEN
    # Replaced with: link(tree, rep_in, "Sediment", solver, "Sediment")
    link(tree, pipe_node, "Vel Mag", solver, "Vel Mag")
    link(tree, grad_node, "Slope", solver, "Slope")
    
    # Params
    solver.inputs["Capacity K"].default_value = 2.0
    solver.inputs["Sand Erodibility"].default_value = 0.5
    solver.inputs["Rock Erodibility"].default_value = 0.05
    solver.inputs["Deposition Rate"].default_value = 0.1
    
    # Connect to Loop Output
    link(tree, solver, "New Bedrock", rep_out, "Bedrock")
    link(tree, solver, "New Sand", rep_out, "Sand")
    link(tree, pipe_node, "New Water", rep_out, "Water")
    link(tree, solver, "New Sediment", rep_out, "Sediment")
    
    # 3. Final Output
    # -------------------------------------------------------------------------
    img_out = nodes.new("ComputeNodeOutputImage"); img_out.location=(1800, 0)
    img_out.label = "Terrain Output"
    link(tree, rep_in, "Bedrock", img_out, "Image") # Visualize Bedrock (from Repeat Input state)
    
    # Maybe visualize Height?
    # Need to re-combine Bedrock+Sand after loop
    final_bed = rep_out.outputs["Bedrock"]
    final_sand = rep_out.outputs["Sand"]
    
    # (Optional: Re-Add for viz)
    
    return tree

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Ensure dependencies (Prodigy base groups)
    import erosion_prodigy_improved_v3
    erosion_prodigy_improved_v3.create_gradient_fd()
    erosion_prodigy_improved_v3.create_pipe_flow_step()
    # erosion_prodigy_improved_v3.create_state_init() # Not needed
    
    # Create our new stuff
    create_multilayer_solver()
    create_multilayer_demo()
