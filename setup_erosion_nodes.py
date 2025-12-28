import bpy

def get_or_create_group(name):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    group = bpy.data.node_groups.new(name, "ComputeNodeTree")
    return group

def create_group_texel_size():
    """ Creates 'Compute Texel Size' group.
    Inputs: Grid
    Outputs: Texel Size (Vector)
    """
    group = get_or_create_group("Compute Texel Size")
    nodes = group.nodes
    links = group.links
    
    # Interface
    iface = group.interface
    iface.new_socket(name="Grid", in_out='INPUT', socket_type='ComputeSocketGrid')
    iface.new_socket(name="Texel Size", in_out='OUTPUT', socket_type='NodeSocketVector')
    
    # Nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-400, 0)
    
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (400, 0)
    
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-150, 0)
    
    math_w = nodes.new("ComputeNodeMath")
    math_w.location = (50, 100)
    math_w.operation = 'DIV'
    math_w.inputs[0].default_value = 1.0
    math_w.name = "Inv Width"
    
    math_h = nodes.new("ComputeNodeMath")
    math_h.location = (50, -100)
    math_h.operation = 'DIV'
    math_h.inputs[0].default_value = 1.0
    math_h.name = "Inv Height"
    
    combine = nodes.new("ComputeNodeCombineXYZ")
    combine.location = (250, 0)
    
    # Links
    links.new(group_in.outputs["Grid"], info.inputs["Grid"])
    links.new(info.outputs["Width"], math_w.inputs[1])
    links.new(info.outputs["Height"], math_h.inputs[1])
    links.new(math_w.outputs[0], combine.inputs["X"])
    links.new(math_h.outputs[0], combine.inputs["Y"])
    links.new(combine.outputs[0], group_out.inputs["Texel Size"])
    
    print(f"Created Group: {group.name}")
    return group

def create_group_gradient():
    """ Creates 'Compute Gradient' group.
    Inputs: Height (Grid)
    Outputs: Slope (Vector)
    """
    group = get_or_create_group("Compute Gradient")
    nodes = group.nodes
    links = group.links
    
    # Interface
    iface = group.interface
    iface.new_socket(name="Height", in_out='INPUT', socket_type='ComputeSocketGrid')
    iface.new_socket(name="Slope", in_out='OUTPUT', socket_type='NodeSocketVector')

    # Nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-800, 0)

    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (1000, 0)

    pos = nodes.new("ComputeNodePosition")
    pos.location = (-600, -150)

    # Re-implementing Texel Size logic inline for robustness/speed
    grid_info = nodes.new("ComputeNodeImageInfo")
    grid_info.location = (-600, 150)

    math_inv_w = nodes.new("ComputeNodeMath")
    math_inv_w.location = (-400, 200)
    math_inv_w.operation = 'DIV'
    math_inv_w.inputs[0].default_value = 1.0

    math_inv_h = nodes.new("ComputeNodeMath")
    math_inv_h.location = (-400, 100)
    math_inv_h.operation = 'DIV'
    math_inv_h.inputs[0].default_value = 1.0

    combine_texel = nodes.new("ComputeNodeCombineXYZ")
    combine_texel.location = (-250, 150)

    # Offsets
    vmath_add_r = nodes.new("ComputeNodeVectorMath")
    vmath_add_r.location = (-50, 300)
    vmath_add_r.operation = 'ADD'

    vmath_sub_l = nodes.new("ComputeNodeVectorMath")
    vmath_sub_l.location = (-50, 150)
    vmath_sub_l.operation = 'SUB'

    vmath_add_u = nodes.new("ComputeNodeVectorMath")
    vmath_add_u.location = (-50, 0)
    vmath_add_u.operation = 'ADD'

    vmath_sub_d = nodes.new("ComputeNodeVectorMath")
    vmath_sub_d.location = (-50, -150)
    vmath_sub_d.operation = 'SUB'

    # Samples
    sample_r = nodes.new("ComputeNodeSample")
    sample_r.location = (150, 300)
    sample_l = nodes.new("ComputeNodeSample")
    sample_l.location = (150, 150)
    sample_u = nodes.new("ComputeNodeSample")
    sample_u.location = (150, 0)
    sample_d = nodes.new("ComputeNodeSample")
    sample_d.location = (150, -150)

    # Separate
    sep_r = nodes.new("ComputeNodeSeparateColor")
    sep_r.location = (350, 300)
    sep_l = nodes.new("ComputeNodeSeparateColor")
    sep_l.location = (350, 150)
    sep_u = nodes.new("ComputeNodeSeparateColor")
    sep_u.location = (350, 0)
    sep_d = nodes.new("ComputeNodeSeparateColor")
    sep_d.location = (350, -150)

    # Gradients
    math_sub_x = nodes.new("ComputeNodeMath")
    math_sub_x.location = (550, 200)
    math_sub_x.operation = 'SUB'
    math_div_x = nodes.new("ComputeNodeMath")
    math_div_x.location = (750, 200)
    math_div_x.operation = 'DIV'
    math_div_x.inputs[1].default_value = 2.0

    math_sub_y = nodes.new("ComputeNodeMath")
    math_sub_y.location = (550, -50)
    math_sub_y.operation = 'SUB'
    math_div_y = nodes.new("ComputeNodeMath")
    math_div_y.location = (750, -50)
    math_div_y.operation = 'DIV'
    math_div_y.inputs[1].default_value = 2.0

    combine = nodes.new("ComputeNodeCombineXYZ")
    combine.location = (900, 75)

    # Wiring
    # Grid -> Info / Samples
    links.new(group_in.outputs["Height"], grid_info.inputs["Grid"])
    links.new(group_in.outputs["Height"], sample_r.inputs["Grid"])
    links.new(group_in.outputs["Height"], sample_l.inputs["Grid"])
    links.new(group_in.outputs["Height"], sample_u.inputs["Grid"])
    links.new(group_in.outputs["Height"], sample_d.inputs["Grid"])

    # Texel Size
    links.new(grid_info.outputs["Width"], math_inv_w.inputs[1])
    links.new(grid_info.outputs["Height"], math_inv_h.inputs[1])
    links.new(math_inv_w.outputs[0], combine_texel.inputs["X"])
    links.new(math_inv_h.outputs[0], combine_texel.inputs["Y"])

    # UV Offsets
    links.new(pos.outputs["Normalized"], vmath_add_r.inputs[0])
    links.new(pos.outputs["Normalized"], vmath_sub_l.inputs[0])
    links.new(pos.outputs["Normalized"], vmath_add_u.inputs[0])
    links.new(pos.outputs["Normalized"], vmath_sub_d.inputs[0])

    links.new(combine_texel.outputs[0], vmath_add_r.inputs[1])
    links.new(combine_texel.outputs[0], vmath_sub_l.inputs[1])
    links.new(combine_texel.outputs[0], vmath_add_u.inputs[1])
    links.new(combine_texel.outputs[0], vmath_sub_d.inputs[1])

    # Sampling
    links.new(vmath_add_r.outputs[0], sample_r.inputs["Coordinate"])
    links.new(vmath_sub_l.outputs[0], sample_l.inputs["Coordinate"])
    links.new(vmath_add_u.outputs[0], sample_u.inputs["Coordinate"])
    links.new(vmath_sub_d.outputs[0], sample_d.inputs["Coordinate"])

    # Separation
    links.new(sample_r.outputs["Color"], sep_r.inputs[0])
    links.new(sample_l.outputs["Color"], sep_l.inputs[0])
    links.new(sample_u.outputs["Color"], sep_u.inputs[0])
    links.new(sample_d.outputs["Color"], sep_d.inputs[0])

    # Calc
    links.new(sep_r.outputs["Red"], math_sub_x.inputs[0])
    links.new(sep_l.outputs["Red"], math_sub_x.inputs[1])
    links.new(sep_u.outputs["Red"], math_sub_y.inputs[0])
    links.new(sep_d.outputs["Red"], math_sub_y.inputs[1])

    links.new(math_sub_x.outputs[0], math_div_x.inputs[0])
    links.new(math_sub_y.outputs[0], math_div_y.inputs[0])

    links.new(math_div_x.outputs[0], combine.inputs["X"])
    links.new(math_div_y.outputs[0], combine.inputs["Y"])
    links.new(combine.outputs[0], group_out.inputs["Slope"])

    print(f"Created Group: {group.name}")
    return group

def create_group_advection():
    """ Creates 'Compute Advection' group.
    Inputs: Quantity (Grid), Velocity (Grid), dt (Float)
    Outputs: Advected (Color)
    Logic: 
      Traceback = UV - (Velocity * dt * TexelSize)
      Result = Sample(Quantity, Traceback)
    """
    group = get_or_create_group("Compute Advection")
    nodes = group.nodes
    links = group.links

    # Interface
    iface = group.interface
    iface.new_socket(name="Quantity", in_out='INPUT', socket_type='ComputeSocketGrid')
    iface.new_socket(name="Velocity", in_out='INPUT', socket_type='ComputeSocketGrid')
    
    # dt with default value
    socket_dt = iface.new_socket(name="dt", in_out='INPUT', socket_type='NodeSocketFloat')
    socket_dt.default_value = 0.016
    
    iface.new_socket(name="Result", in_out='OUTPUT', socket_type='NodeSocketColor')

    # Nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-600, 0)
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (600, 0)

    # 1. Get Velocity Vector
    pos = nodes.new("ComputeNodePosition")
    pos.location = (-400, 100)
    
    sample_vel = nodes.new("ComputeNodeSample")
    sample_vel.location = (-200, 100)
    sample_vel.name = "Sample Velocity"

    # 2. Get Texel Size
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-400, -200)

    math_w = nodes.new("ComputeNodeMath")
    math_w.location = (-200, -150)
    math_w.operation = 'DIV'
    math_w.inputs[0].default_value = 1.0
    
    math_h = nodes.new("ComputeNodeMath")
    math_h.location = (-200, -250)
    math_h.operation = 'DIV'
    math_h.inputs[0].default_value = 1.0

    combine_texel = nodes.new("ComputeNodeCombineXYZ")
    combine_texel.location = (0, -200)

    # 3. Calculate Traceback Offset
    
    # Vel * dt
    scale_vel = nodes.new("ComputeNodeVectorMath")
    scale_vel.location = (0, 100)
    scale_vel.operation = 'SCALE'
    scale_vel.name = "Vel * dt"
    
    # Vel * dt * TexelSize
    mul_texel = nodes.new("ComputeNodeVectorMath")
    mul_texel.location = (200, 0)
    mul_texel.operation = 'MUL'
    mul_texel.name = "Convert to UV Space"

    # Traceback = UV - Offset
    sub_trace = nodes.new("ComputeNodeVectorMath")
    sub_trace.location = (400, 100)
    sub_trace.operation = 'SUB'
    sub_trace.name = "UV - Offset"

    # Sample Quantity at Traceback
    sample_qty = nodes.new("ComputeNodeSample")
    sample_qty.location = (600, -50)
    sample_qty.name = "Sample Quantity"

    # Links
    
    # Info
    links.new(group_in.outputs["Velocity"], info.inputs["Grid"])
    links.new(info.outputs["Width"], math_w.inputs[1])
    links.new(info.outputs["Height"], math_h.inputs[1])
    links.new(math_w.outputs[0], combine_texel.inputs["X"])
    links.new(math_h.outputs[0], combine_texel.inputs["Y"])

    # Velocity Sample
    links.new(group_in.outputs["Velocity"], sample_vel.inputs["Grid"])
    links.new(pos.outputs["Normalized"], sample_vel.inputs["Coordinate"])

    # Calc Offset
    links.new(sample_vel.outputs["Color"], scale_vel.inputs[0]) 
    links.new(group_in.outputs["dt"], scale_vel.inputs[3]) # Scale input
    
    links.new(scale_vel.outputs[0], mul_texel.inputs[0])
    links.new(combine_texel.outputs[0], mul_texel.inputs[1])

    # Traceback
    links.new(pos.outputs["Normalized"], sub_trace.inputs[0])
    links.new(mul_texel.outputs[0], sub_trace.inputs[1])

    # Sample Quantity
    links.new(group_in.outputs["Quantity"], sample_qty.inputs["Grid"])
    links.new(sub_trace.outputs[0], sample_qty.inputs["Coordinate"])
    
    links.new(sample_qty.outputs["Color"], group_out.inputs["Result"])

    print(f"Created Group: {group.name}")
    return group

def create_group_flow_velocity():
    """ Creates 'Compute Flow Velocity' group.
    Inputs: Slope (Vector)
    Outputs: Velocity (Vector)
    Logic: Velocity = Slope (Simple gravity model for now)
    Future: Add Inertia/Water Amount
    """
    group = get_or_create_group("Compute Flow Velocity")
    nodes = group.nodes
    links = group.links
    iface = group.interface
    
    # Interface
    iface.new_socket(name="Slope", in_out='INPUT', socket_type='NodeSocketVector')
    iface.new_socket(name="Velocity", in_out='OUTPUT', socket_type='NodeSocketVector')
    
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-400, 0)
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (400, 0)
    
    # Pass through for now (Pipes/Flux model is complex, starting with Gradient Advection)
    # Velocity is just the slope direction/magnitude
    
    # Maybe add a standard "Gravity" constant multiplier
    math_gravity = nodes.new("ComputeNodeVectorMath")
    math_gravity.location = (0, 0)
    math_gravity.operation = 'SCALE'
    math_gravity.inputs[3].default_value = 9.8 
    math_gravity.name = "Gravity Accel"
    
    links.new(group_in.outputs["Slope"], math_gravity.inputs[0])
    links.new(math_gravity.outputs[0], group_out.inputs["Velocity"])
    
    print(f"Created Group: {group.name}")
    return group

def create_group_erosion_deposition():
    """ Creates 'Compute Erosion Deposition' group.
    Inputs: Height, Sediment, Velocity, K_erosion, K_deposition, K_capacity
    Outputs: New Height, New Sediment
    """
    group = get_or_create_group("Compute Erosion Deposition")
    nodes = group.nodes
    links = group.links
    iface = group.interface
    
    # Interface
    iface.new_socket(name="Height", in_out='INPUT', socket_type='ComputeSocketGrid')
    iface.new_socket(name="Sediment", in_out='INPUT', socket_type='ComputeSocketGrid')
    iface.new_socket(name="Velocity", in_out='INPUT', socket_type='ComputeSocketGrid')
    
    ks = iface.new_socket(name="K Erosion", in_out='INPUT', socket_type='NodeSocketFloat')
    ks.default_value = 0.5
    kd = iface.new_socket(name="K Deposition", in_out='INPUT', socket_type='NodeSocketFloat')
    kd.default_value = 0.5
    kc = iface.new_socket(name="K Capacity", in_out='INPUT', socket_type='NodeSocketFloat')
    kc.default_value = 1.0
    
    iface.new_socket(name="New Height", in_out='OUTPUT', socket_type='NodeSocketColor')
    iface.new_socket(name="New Sediment", in_out='OUTPUT', socket_type='NodeSocketColor')

    # Nodes
    group_in = nodes.new("ComputeNodeGroupInput")
    group_in.location = (-1000, 0)
    group_out = nodes.new("ComputeNodeGroupOutput")
    group_out.location = (1200, 0)

    # 1. Sample Height, Sediment, Velocity at current pos
    pos = nodes.new("ComputeNodePosition")
    pos.location = (-800, 200)

    sample_h = nodes.new("ComputeNodeSample")
    sample_h.location = (-600, 300)
    sample_h.name = "Sample Height"
    
    sample_s = nodes.new("ComputeNodeSample")
    sample_s.location = (-600, 100)
    sample_s.name = "Sample Sediment"
    
    sample_v = nodes.new("ComputeNodeSample")
    sample_v.location = (-600, -100)
    sample_v.name = "Sample Velocity"
    
    # 2. Calculate Capacity = Length(Velocity) * K_capacity
    # Velocity is Color -> Vector conversion implicit?
    # Length
    len_v = nodes.new("ComputeNodeVectorMath")
    len_v.location = (-400, -100)
    len_v.operation = 'LENGTH'
    
    cap = nodes.new("ComputeNodeMath")
    cap.location = (-200, -100)
    cap.operation = 'MUL'
    cap.name = "Capacity"
    
    # 3. Diff = Capacity - Sediment
    # Sediment is Color (R channel used)
    sep_s = nodes.new("ComputeNodeSeparateColor")
    sep_s.location = (-400, 100)
    
    diff = nodes.new("ComputeNodeMath")
    diff.location = (0, 0)
    diff.operation = 'SUB'
    diff.name = "Diff (Cap - Sed)"
    
    # 4. Branching Factor (Unsigned Diff / Condition)
    # We need to know if Diff > 0 or < 0
    # Greater Than 0
    gt_zero = nodes.new("ComputeNodeMath")
    gt_zero.location = (200, 100)
    gt_zero.operation = 'GREATER_THAN'
    gt_zero.inputs[1].default_value = 0.0

    # 5. Calculate Amount
    # If Diff > 0 (Erode): Amount = Diff * K_erosion
    # If Diff < 0 (Deposit): Amount = Diff * K_deposition
    
    amount_erode = nodes.new("ComputeNodeMath")
    amount_erode.location = (200, -50)
    amount_erode.operation = 'MUL'
    amount_erode.name = "Amt Erode"
    
    amount_deposit = nodes.new("ComputeNodeMath")
    amount_deposit.location = (200, -150)
    amount_deposit.operation = 'MUL'
    amount_deposit.name = "Amt Deposit"
    
    # Mix amounts based on GT Zero
    mix_amount = nodes.new("ComputeNodeMath") # Is there a Mix Float? Yes, Mix node usually.
    # ComputeNodeMath doesn't have Mix. We can use Mix Color or write custom mix math logic.
    # Logic: Amount = GT ? Erode : Deposit
    # Emulate Mix: (A * Fac) + (B * (1-Fac))
    # Or use 'Switch' if available? Assuming we don't have switch yet.
    # Let's use Lerp logic with Math nodes or try finding Mix node.
    # Checking existing nodes... 'ComputeNodeMix' usually exists in Blender shaders.
    # If not, let's use: (Erode * GT) + (Deposit * (1-GT))
    # Note: GT is 1.0 or 0.0
    
    # Term 1: Erode * GT
    term1 = nodes.new("ComputeNodeMath")
    term1.location = (400, 0)
    term1.operation = 'MUL'
    
    # Term 2: Deposit * (1-GT)
    # 1 - GT
    one_minus_gt = nodes.new("ComputeNodeMath")
    one_minus_gt.location = (300, 200)
    one_minus_gt.operation = 'SUB'
    one_minus_gt.inputs[0].default_value = 1.0
    
    term2 = nodes.new("ComputeNodeMath")
    term2.location = (400, -100)
    term2.operation = 'MUL'
    
    final_amount = nodes.new("ComputeNodeMath")
    final_amount.location = (600, -50)
    final_amount.operation = 'ADD'
    final_amount.name = "Transfer Amount"
    
    # 6. Apply to Height and Sediment
    # New Height = Height - Amount (Erode: Amount>0 -> H decreases. Deposit: Amount<0 -> H increases)
    # New Sediment = Sediment + Amount
    
    sep_h = nodes.new("ComputeNodeSeparateColor")
    sep_h.location = (-400, 300)
    
    new_h = nodes.new("ComputeNodeMath")
    new_h.location = (800, 200)
    new_h.operation = 'SUB'
    new_h.name = "Height - Amt"
    
    new_s = nodes.new("ComputeNodeMath")
    new_s.location = (800, 0)
    new_s.operation = 'ADD'
    new_s.name = "Sed + Amt"
    
    # Recombine to Colors (Monochrome R channel)
    comb_h = nodes.new("ComputeNodeCombineColor")
    comb_h.location = (1000, 200)
    
    comb_s = nodes.new("ComputeNodeCombineColor")
    comb_s.location = (1000, 0)

    # Wiring
    # Inputs -> Samples
    links.new(group_in.outputs["Height"], sample_h.inputs["Grid"])
    links.new(group_in.outputs["Sediment"], sample_s.inputs["Grid"])
    links.new(group_in.outputs["Velocity"], sample_v.inputs["Grid"])
    links.new(pos.outputs["Normalized"], sample_h.inputs["Coordinate"])
    links.new(pos.outputs["Normalized"], sample_s.inputs["Coordinate"])
    links.new(pos.outputs["Normalized"], sample_v.inputs["Coordinate"])
    
    # Velocity Len -> Capacity
    links.new(sample_v.outputs["Color"], len_v.inputs[0]) 
    links.new(len_v.outputs[0], cap.inputs[0])
    links.new(group_in.outputs["K Capacity"], cap.inputs[1])
    
    # Diff
    links.new(sample_s.outputs["Color"], sep_s.inputs[0])
    links.new(cap.outputs[0], diff.inputs[0])
    links.new(sep_s.outputs["Red"], diff.inputs[1])
    
    # Branching
    links.new(diff.outputs[0], gt_zero.inputs[0])
    
    # Amounts
    links.new(diff.outputs[0], amount_erode.inputs[0])
    links.new(group_in.outputs["K Erosion"], amount_erode.inputs[1])
    
    links.new(diff.outputs[0], amount_deposit.inputs[0])
    links.new(group_in.outputs["K Deposition"], amount_deposit.inputs[1])
    
    # Mixing / Selection
    links.new(amount_erode.outputs[0], term1.inputs[0])
    links.new(gt_zero.outputs[0], term1.inputs[1]) # Multiply by 1 or 0
    
    links.new(gt_zero.outputs[0], one_minus_gt.inputs[1]) # 1.0 - GT
    links.new(amount_deposit.outputs[0], term2.inputs[0])
    links.new(one_minus_gt.outputs[0], term2.inputs[1])
    
    links.new(term1.outputs[0], final_amount.inputs[0])
    links.new(term2.outputs[0], final_amount.inputs[1])
    
    # Apply
    links.new(sample_h.outputs["Color"], sep_h.inputs[0])
    links.new(sep_h.outputs["Red"], new_h.inputs[0])
    links.new(final_amount.outputs[0], new_h.inputs[1])
    
    links.new(sep_s.outputs["Red"], new_s.inputs[0])
    links.new(final_amount.outputs[0], new_s.inputs[1])
    
    # Output
    links.new(new_h.outputs[0], comb_h.inputs["Red"])
    links.new(new_h.outputs[0], comb_h.inputs["Green"])
    links.new(new_h.outputs[0], comb_h.inputs["Blue"])
    
    links.new(new_s.outputs[0], comb_s.inputs["Red"])
    links.new(new_s.outputs[0], comb_s.inputs["Green"])
    links.new(new_s.outputs[0], comb_s.inputs["Blue"])
    
    links.new(comb_h.outputs["Color"], group_out.inputs["New Height"])
    links.new(comb_s.outputs["Color"], group_out.inputs["New Sediment"])

    print(f"Created Group: {group.name}")
    return group

def main():
    print("---------------------------------------")
    print("Generating Erosion Node Groups...")
    create_group_texel_size()
    create_group_gradient()
    create_group_advection()
    create_group_flow_velocity()
    create_group_erosion_deposition()
    print("Done.")

if __name__ == "__main__":
    main()
