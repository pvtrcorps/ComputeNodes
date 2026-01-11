 """
Prodigy Terrain Erosion System (Gaea-like, GPU-friendly, grid-based)
===================================================================

This script generates a set of Compute node-groups intended for a 2.5D (heightmap) erosion
pipeline inside Blender using your compute-node add-on.

Design goals
------------
- Closer to "production" erosion tools (e.g., Gaea-style) than pure flow-accumulation hacks.
- Stable, mass-conserving *Eulerian* water flow on a grid (virtual-pipes / shallow-water-lite).
- Sediment capacity transport with controlled erosion/deposition.
- Optional thermal talus relaxation pass (bank collapse / slope limiting).
- Loop-ready graph (Repeat Input/Output ping-pong).

Important notes
---------------
- This script assumes the following node types exist in your add-on:
  ComputeNodeGroupInput/Output, ComputeNodeImageInfo, ComputeNodePosition,
  ComputeNodeSample, ComputeNodeMath, ComputeNodeVectorMath,
  ComputeNodeCombineXYZ, ComputeNodeCombineColor, ComputeNodeSeparateColor,
  ComputeNodeCapture, ComputeNodeNoiseTexture, ComputeNodeRepeatInput/Output,
  ComputeNodeOutputImage.
- Everything is built from these primitives (no dependency on other scripts).

Usage
-----
    import erosion_prodigy
    erosion_prodigy.setup_all()
    erosion_prodigy.create_demo_graph()

"""

import bpy

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

def _cap_scalar_to_grid(tree, info, scalar_value_socket, out_node, out_name, loc=(800,0)):
    """Helper: replicate scalar to XYZ and capture to grid."""
    comb = tree.nodes.new("ComputeNodeCombineXYZ")
    comb.location = (loc[0]-200, loc[1])
    link(tree, scalar_value_socket.node if hasattr(scalar_value_socket, "node") else scalar_value_socket, 
         scalar_value_socket.name if hasattr(scalar_value_socket, "name") else scalar_value_socket,
         comb, "X")

def _replicate_value_xyz(tree, value_node, value_socket_name, loc):
    comb = tree.nodes.new("ComputeNodeCombineXYZ")
    comb.location = loc
    link(tree, value_node, value_socket_name, comb, "X")
    link(tree, value_node, value_socket_name, comb, "Y")
    link(tree, value_node, value_socket_name, comb, "Z")
    return comb

def _capture_vector_as_grid(tree, info, vector_node, vector_socket_name, loc):
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.location = (loc[0]+220, loc[1])
    link(tree, vector_node, vector_socket_name, cap, "Field")
    link(tree, info, "Width", cap, "Width")
    link(tree, info, "Height", cap, "Height")
    return cap

def _capture_color_as_grid(tree, info, color_node, color_socket_name, loc):
    cap = tree.nodes.new("ComputeNodeCapture")
    cap.location = (loc[0]+220, loc[1])
    link(tree, color_node, color_socket_name, cap, "Field")
    link(tree, info, "Width", cap, "Width")
    link(tree, info, "Height", cap, "Height")
    return cap

def _sample_with_offset(tree, grid_socket_node, grid_socket_name, info, pos_node, dx_pix, dy_pix, loc):
    """Sample a grid at normalized position + pixel offset."""
    comb_off = tree.nodes.new("ComputeNodeCombineXYZ")
    comb_off.location = (loc[0], loc[1])

    # dx_pix, dy_pix are in *pixel units*; convert to normalized with 1/width, 1/height
    pix_x = tree.nodes.new("ComputeNodeMath")
    pix_x.operation = "DIV"
    pix_x.location = (loc[0]-220, loc[1]+60)
    set_default(pix_x, 0, float(dx_pix))
    link(tree, info, "Width", pix_x, 1)

    pix_y = tree.nodes.new("ComputeNodeMath")
    pix_y.operation = "DIV"
    pix_y.location = (loc[0]-220, loc[1]-60)
    set_default(pix_y, 0, float(dy_pix))
    link(tree, info, "Height", pix_y, 1)

    link(tree, pix_x, "Value", comb_off, "X")
    link(tree, pix_y, "Value", comb_off, "Y")

    pos_off = tree.nodes.new("ComputeNodeVectorMath")
    pos_off.operation = "ADD"
    pos_off.location = (loc[0]+220, loc[1])
    link(tree, pos_node, "Normalized", pos_off, 0)
    link(tree, comb_off, "Vector", pos_off, 1)

    s = tree.nodes.new("ComputeNodeSample")
    s.location = (loc[0]+420, loc[1])
    link(tree, grid_socket_node, grid_socket_name, s, "Grid")
    link(tree, pos_off, "Vector", s, "Coordinate")
    return s

# =============================================================================
# NODE GROUPS
# =============================================================================

def create_state_init():
    """Split an input Height into Bedrock + Soil, and initialize Water/Sediment/Velocity."""
    tree = get_or_create_tree("Prodigy State Init")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Rock Fraction", "INPUT", "NodeSocketFloat", 0.35)
    add_socket(tree, "Initial Water", "INPUT", "NodeSocketFloat", 0.0)

    add_socket(tree, "Bedrock", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Velocity", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput");  n_in.location = (-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1200, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1000, -240)
    link(tree, n_in, "Height", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-1000, 160)

    s_h = nodes.new("ComputeNodeSample"); s_h.location = (-760, 160)
    link(tree, n_in, "Height", s_h, "Grid")
    link(tree, pos, "Normalized", s_h, "Coordinate")

    # Bedrock = Height * RockFraction
    bed_mul = nodes.new("ComputeNodeMath"); bed_mul.operation = "MUL"; bed_mul.location = (-520, 220)
    link(tree, s_h, "Color", bed_mul, 0)
    link(tree, n_in, "Rock Fraction", bed_mul, 1)

    # Soil = Height - Bedrock
    soil_sub = nodes.new("ComputeNodeMath"); soil_sub.operation = "SUB"; soil_sub.location = (-520, 80)
    link(tree, s_h, "Color", soil_sub, 0)
    link(tree, bed_mul, "Value", soil_sub, 1)

    # Capture helpers
    def cap_scalar(val_node, val_socket, loc_xy):
        comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (loc_xy[0]-220, loc_xy[1])
        if val_node is None:
            set_default(comb, "X", 0.0); set_default(comb, "Y", 0.0); set_default(comb, "Z", 0.0)
        else:
            link(tree, val_node, val_socket, comb, "X")
            link(tree, val_node, val_socket, comb, "Y")
            link(tree, val_node, val_socket, comb, "Z")
        cap = nodes.new("ComputeNodeCapture"); cap.location = (loc_xy[0], loc_xy[1])
        link(tree, comb, "Vector", cap, "Field")
        link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")
        return cap

    c_bed = cap_scalar(bed_mul, "Value", (420, 260)); link(tree, c_bed, "Grid", n_out, "Bedrock")
    c_soil = cap_scalar(soil_sub, "Value", (420, 120)); link(tree, c_soil, "Grid", n_out, "Soil")

    # Water const
    comb_w = nodes.new("ComputeNodeCombineXYZ"); comb_w.location = (200, -40)
    link(tree, n_in, "Initial Water", comb_w, "X")
    link(tree, n_in, "Initial Water", comb_w, "Y")
    link(tree, n_in, "Initial Water", comb_w, "Z")
    cap_w = nodes.new("ComputeNodeCapture"); cap_w.location = (420, -40)
    link(tree, comb_w, "Vector", cap_w, "Field")
    link(tree, info, "Width", cap_w, "Width"); link(tree, info, "Height", cap_w, "Height")
    link(tree, cap_w, "Grid", n_out, "Water")

    c_sed = cap_scalar(None, "", (420, -200)); link(tree, c_sed, "Grid", n_out, "Sediment")
    c_vel = cap_scalar(None, "", (420, -360)); link(tree, c_vel, "Grid", n_out, "Velocity")

    return tree

def create_combine_height():
    """Height = Bedrock + Soil."""
    tree = get_or_create_tree("Prodigy Combine Height")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Bedrock", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Height", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-700, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (700, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-520, -220)
    link(tree, n_in, "Bedrock", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-520, 140)

    s_b = nodes.new("ComputeNodeSample"); s_b.location = (-300, 220)
    link(tree, n_in, "Bedrock", s_b, "Grid"); link(tree, pos, "Normalized", s_b, "Coordinate")

    s_s = nodes.new("ComputeNodeSample"); s_s.location = (-300, 40)
    link(tree, n_in, "Soil", s_s, "Grid"); link(tree, pos, "Normalized", s_s, "Coordinate")

    add = nodes.new("ComputeNodeMath"); add.operation = "ADD"; add.location = (-80, 140)
    link(tree, s_b, "Color", add, 0); link(tree, s_s, "Color", add, 1)

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (140, 140)
    link(tree, add, "Value", comb, "X"); link(tree, add, "Value", comb, "Y"); link(tree, add, "Value", comb, "Z")

    cap = nodes.new("ComputeNodeCapture"); cap.location = (360, 140)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")

    link(tree, cap, "Grid", n_out, "Height")
    return tree

def create_gradient_fd():
    """
    Central-difference gradient of Height (grid).
    Outputs:
      - Gradient (Vector grid): (dx, dy, 0)
      - Slope (Scalar grid): approx |grad|
    """
    tree = get_or_create_tree("Prodigy Gradient FD")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Gradient", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Slope", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1200, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1200, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1000, -240)
    link(tree, n_in, "Height", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-1000, 160)

    # Samples: E,W,N,S
    sE = _sample_with_offset(tree, n_in, "Height", info, pos, +1, 0, (-900, 220))
    sW = _sample_with_offset(tree, n_in, "Height", info, pos, -1, 0, (-900, 40))
    sN = _sample_with_offset(tree, n_in, "Height", info, pos, 0, +1, (-900, -140))
    sS = _sample_with_offset(tree, n_in, "Height", info, pos, 0, -1, (-900, -320))

    # dx = (E - W) * 0.5
    subx = nodes.new("ComputeNodeMath"); subx.operation = "SUB"; subx.location = (-200, 140)
    link(tree, sE, "Color", subx, 0); link(tree, sW, "Color", subx, 1)

    mulx = nodes.new("ComputeNodeMath"); mulx.operation = "MUL"; mulx.location = (0, 140)
    link(tree, subx, "Value", mulx, 0); set_default(mulx, 1, 0.5)

    # dy = (N - S) * 0.5
    suby = nodes.new("ComputeNodeMath"); suby.operation = "SUB"; suby.location = (-200, -120)
    link(tree, sN, "Color", suby, 0); link(tree, sS, "Color", suby, 1)

    muly = nodes.new("ComputeNodeMath"); muly.operation = "MUL"; muly.location = (0, -120)
    link(tree, suby, "Value", muly, 0); set_default(muly, 1, 0.5)

    # Slope ≈ sqrt(dx^2 + dy^2)
    dx2 = nodes.new("ComputeNodeMath"); dx2.operation = "MUL"; dx2.location = (220, 200)
    link(tree, mulx, "Value", dx2, 0); link(tree, mulx, "Value", dx2, 1)

    dy2 = nodes.new("ComputeNodeMath"); dy2.operation = "MUL"; dy2.location = (220, 40)
    link(tree, muly, "Value", dy2, 0); link(tree, muly, "Value", dy2, 1)

    sum2 = nodes.new("ComputeNodeMath"); sum2.operation = "ADD"; sum2.location = (420, 120)
    link(tree, dx2, "Value", sum2, 0); link(tree, dy2, "Value", sum2, 1)

    # sqrt via POW(x, 0.5)
    sqrt = nodes.new("ComputeNodeMath"); sqrt.operation = "POW"; sqrt.location = (620, 120)
    link(tree, sum2, "Value", sqrt, 0); set_default(sqrt, 1, 0.5)

    # Gradient vector
    comb_g = nodes.new("ComputeNodeCombineXYZ"); comb_g.location = (420, -120)
    link(tree, mulx, "Value", comb_g, "X")
    link(tree, muly, "Value", comb_g, "Y")
    set_default(comb_g, "Z", 0.0)

    cap_g = nodes.new("ComputeNodeCapture"); cap_g.location = (700, -120)
    link(tree, comb_g, "Vector", cap_g, "Field")
    link(tree, info, "Width", cap_g, "Width"); link(tree, info, "Height", cap_g, "Height")
    link(tree, cap_g, "Grid", n_out, "Gradient")

    # Slope scalar as grid
    comb_s = nodes.new("ComputeNodeCombineXYZ"); comb_s.location = (820, 120)
    link(tree, sqrt, "Value", comb_s, "X"); link(tree, sqrt, "Value", comb_s, "Y"); link(tree, sqrt, "Value", comb_s, "Z")
    cap_s = nodes.new("ComputeNodeCapture"); cap_s.location = (1040, 120)
    link(tree, comb_s, "Vector", cap_s, "Field")
    link(tree, info, "Width", cap_s, "Width"); link(tree, info, "Height", cap_s, "Height")
    link(tree, cap_s, "Grid", n_out, "Slope")

    return tree

def create_add_rain():
    """Water += RainRate."""
    tree = get_or_create_tree("Prodigy Add Rain")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Rain Rate", "INPUT", "NodeSocketFloat", 0.002)
    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-900, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (900, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-700, -220)
    link(tree, n_in, "Water", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-700, 140)
    s_w = nodes.new("ComputeNodeSample"); s_w.location = (-480, 140)
    link(tree, n_in, "Water", s_w, "Grid"); link(tree, pos, "Normalized", s_w, "Coordinate")

    add = nodes.new("ComputeNodeMath"); add.operation = "ADD"; add.location = (-240, 140)
    link(tree, s_w, "Color", add, 0); link(tree, n_in, "Rain Rate", add, 1)

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (0, 140)
    link(tree, add, "Value", comb, "X"); link(tree, add, "Value", comb, "Y"); link(tree, add, "Value", comb, "Z")

    cap = nodes.new("ComputeNodeCapture"); cap.location = (240, 140)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")
    link(tree, cap, "Grid", n_out, "New Water")
    return tree

def create_pipe_flow_step():
    """
    Mass-conserving pipe-style water flow (single Euler step).

    Inputs:
      - Surface: Height + Water (or any surface level)
      - Water: current water amount
      - Flow Rate: how aggressively water moves each step (0..1-ish)

    Outputs:
      - New Water
      - Outflow (RGBA) : outflows to (E,W,N,S) in channels (R,G,B,A)
      - Vel Mag : a scalar proxy for speed (sum outflow / water scale)
    """
    tree = get_or_create_tree("Prodigy Pipe Flow Step")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Surface", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Flow Rate", "INPUT", "NodeSocketFloat", 0.35)

    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Outflow", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "Vel Mag", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1400, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1400, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1200, -260)
    link(tree, n_in, "Surface", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-1200, 160)

    # Center surface and water
    s_surf = nodes.new("ComputeNodeSample"); s_surf.location = (-980, 220)
    link(tree, n_in, "Surface", s_surf, "Grid"); link(tree, pos, "Normalized", s_surf, "Coordinate")

    s_wat = nodes.new("ComputeNodeSample"); s_wat.location = (-980, 40)
    link(tree, n_in, "Water", s_wat, "Grid"); link(tree, pos, "Normalized", s_wat, "Coordinate")

    # Neighbor surfaces
    sE = _sample_with_offset(tree, n_in, "Surface", info, pos, +1, 0, (-1100, 420))
    sW = _sample_with_offset(tree, n_in, "Surface", info, pos, -1, 0, (-1100, 270))
    sN = _sample_with_offset(tree, n_in, "Surface", info, pos, 0, +1, (-1100, 120))
    sS = _sample_with_offset(tree, n_in, "Surface", info, pos, 0, -1, (-1100, -30))

    # delta = max(0, surf_center - surf_neighbor)
    def make_delta(nei_sample, y):
        sub = nodes.new("ComputeNodeMath"); sub.operation = "SUB"; sub.location = (-520, y)
        link(tree, s_surf, "Color", sub, 0); link(tree, nei_sample, "Color", sub, 1)
        mx = nodes.new("ComputeNodeMath"); mx.operation = "MAX"; mx.location = (-320, y)
        link(tree, sub, "Value", mx, 0); set_default(mx, 1, 0.0)
        return mx

    dE = make_delta(sE, 360)
    dW = make_delta(sW, 220)
    dN = make_delta(sN, 80)
    dS = make_delta(sS, -60)

    # sumD
    s1 = nodes.new("ComputeNodeMath"); s1.operation="ADD"; s1.location = (-120, 290)
    link(tree, dE, "Value", s1, 0); link(tree, dW, "Value", s1, 1)
    s2 = nodes.new("ComputeNodeMath"); s2.operation="ADD"; s2.location = (-120, 10)
    link(tree, dN, "Value", s2, 0); link(tree, dS, "Value", s2, 1)
    sumD = nodes.new("ComputeNodeMath"); sumD.operation="ADD"; sumD.location = (80, 150)
    link(tree, s1, "Value", sumD, 0); link(tree, s2, "Value", sumD, 1)

    # safeSumD
    safe = nodes.new("ComputeNodeMath"); safe.operation="MAX"; safe.location = (280, 150)
    link(tree, sumD, "Value", safe, 0); set_default(safe, 1, 1e-6)

    # Clamp Flow Rate to [0,1] using MAX/MIN (prevents outflow > available water)
    fr_pos = nodes.new("ComputeNodeMath"); fr_pos.operation="MAX"; fr_pos.location = (280, 300)
    link(tree, n_in, "Flow Rate", fr_pos, 0); set_default(fr_pos, 1, 0.0)
    fr_clamp = nodes.new("ComputeNodeMath"); fr_clamp.operation="MIN"; fr_clamp.location = (480, 300)
    link(tree, fr_pos, "Value", fr_clamp, 0); set_default(fr_clamp, 1, 1.0)

    # norm weights
    def norm(d, y):
        div = nodes.new("ComputeNodeMath"); div.operation="DIV"; div.location = (480, y)
        link(tree, d, "Value", div, 0); link(tree, safe, "Value", div, 1)
        return div

    wE, wW, wN, wS = norm(dE, 320), norm(dW, 220), norm(dN, 120), norm(dS, 20)

    # outflow_i = w_i * Water * FlowRate
    def outflow(w, y):
        mul1 = nodes.new("ComputeNodeMath"); mul1.operation="MUL"; mul1.location = (680, y)
        link(tree, w, "Value", mul1, 0); link(tree, s_wat, "Color", mul1, 1)
        mul2 = nodes.new("ComputeNodeMath"); mul2.operation="MUL"; mul2.location = (880, y)
        link(tree, mul1, "Value", mul2, 0); link(tree, fr_clamp, "Value", mul2, 1)
        return mul2

    oE, oW, oN, oS = outflow(wE, 320), outflow(wW, 220), outflow(wN, 120), outflow(wS, 20)

    # Total out
    so1 = nodes.new("ComputeNodeMath"); so1.operation="ADD"; so1.location = (1080, 290)
    link(tree, oE, "Value", so1, 0); link(tree, oW, "Value", so1, 1)
    so2 = nodes.new("ComputeNodeMath"); so2.operation="ADD"; so2.location = (1080, 70)
    link(tree, oN, "Value", so2, 0); link(tree, oS, "Value", so2, 1)
    tot_out = nodes.new("ComputeNodeMath"); tot_out.operation="ADD"; tot_out.location = (1280, 180)
    link(tree, so1, "Value", tot_out, 0); link(tree, so2, "Value", tot_out, 1)

    # Gather inflow from neighbors: sample neighbor outflow and pick opposite channel
    # We'll build outflow RGBA first then sample it.
    comb_out = nodes.new("ComputeNodeCombineColor"); comb_out.location = (1080, -140)
    link(tree, oE, "Value", comb_out, "Red")    # E
    link(tree, oW, "Value", comb_out, "Green")  # W
    link(tree, oN, "Value", comb_out, "Blue")   # N
    link(tree, oS, "Value", comb_out, "Alpha")  # S

    cap_out = nodes.new("ComputeNodeCapture"); cap_out.location = (1280, -140)
    link(tree, comb_out, "Color", cap_out, "Field")
    link(tree, info, "Width", cap_out, "Width"); link(tree, info, "Height", cap_out, "Height")

    # Sample neighbor outflow grids
    # Inflow from E neighbor is its W outflow => Green
    # Inflow from W neighbor is its E outflow => Red
    # Inflow from N neighbor is its S outflow => Alpha
    # Inflow from S neighbor is its N outflow => Blue
    def inflow_from(dx, dy, channel, y):
        s_of = _sample_with_offset(tree, cap_out, "Grid", info, pos, dx, dy, (720, y))
        sep = nodes.new("ComputeNodeSeparateColor"); sep.location = (980, y)
        link(tree, s_of, "Color", sep, "Color")
        return sep, channel

    sepE, chE = inflow_from(+1, 0, "Green", -320)
    sepW, chW = inflow_from(-1, 0, "Red", -520)
    sepN, chN = inflow_from(0, +1, "Alpha", -720)
    sepS, chS = inflow_from(0, -1, "Blue", -920)

    def pick(sep, ch, y):
        # sep outputs are sockets; connect directly to math add chain later
        # We'll just return (sep, ch)
        return sep, ch

    # total inflow = sum(picks)
    add_i1 = nodes.new("ComputeNodeMath"); add_i1.operation="ADD"; add_i1.location = (1200, -520)
    link(tree, sepE, chE, add_i1, 0); link(tree, sepW, chW, add_i1, 1)
    add_i2 = nodes.new("ComputeNodeMath"); add_i2.operation="ADD"; add_i2.location = (1200, -740)
    link(tree, sepN, chN, add_i2, 0); link(tree, sepS, chS, add_i2, 1)
    tot_in = nodes.new("ComputeNodeMath"); tot_in.operation="ADD"; tot_in.location = (1400, -640)
    link(tree, add_i1, "Value", tot_in, 0); link(tree, add_i2, "Value", tot_in, 1)

    # NewWater = Water - tot_out + tot_in
    sub = nodes.new("ComputeNodeMath"); sub.operation="SUB"; sub.location = (1520, 60)
    link(tree, s_wat, "Color", sub, 0); link(tree, tot_out, "Value", sub, 1)

    addw = nodes.new("ComputeNodeMath"); addw.operation="ADD"; addw.location = (1700, 60)
    link(tree, sub, "Value", addw, 0); link(tree, tot_in, "Value", addw, 1)

    # Clamp >= 0
    clamp0 = nodes.new("ComputeNodeMath"); clamp0.operation="MAX"; clamp0.location = (1880, 60)
    link(tree, addw, "Value", clamp0, 0); set_default(clamp0, 1, 0.0)

    # Capture NewWater
    comb_w = nodes.new("ComputeNodeCombineXYZ"); comb_w.location = (2060, 60)
    link(tree, clamp0, "Value", comb_w, "X"); link(tree, clamp0, "Value", comb_w, "Y"); link(tree, clamp0, "Value", comb_w, "Z")
    cap_w = nodes.new("ComputeNodeCapture"); cap_w.location = (2280, 60)
    link(tree, comb_w, "Vector", cap_w, "Field")
    link(tree, info, "Width", cap_w, "Width"); link(tree, info, "Height", cap_w, "Height")

    # VelMag proxy: tot_out / max(water, eps)
    safe_w = nodes.new("ComputeNodeMath"); safe_w.operation="MAX"; safe_w.location = (1520, 260)
    link(tree, s_wat, "Color", safe_w, 0); set_default(safe_w, 1, 1e-6)
    vel = nodes.new("ComputeNodeMath"); vel.operation="DIV"; vel.location = (1700, 260)
    link(tree, tot_out, "Value", vel, 0); link(tree, safe_w, "Value", vel, 1)

    comb_v = nodes.new("ComputeNodeCombineXYZ"); comb_v.location = (2060, 260)
    link(tree, vel, "Value", comb_v, "X"); link(tree, vel, "Value", comb_v, "Y"); link(tree, vel, "Value", comb_v, "Z")
    cap_v = nodes.new("ComputeNodeCapture"); cap_v.location = (2280, 260)
    link(tree, comb_v, "Vector", cap_v, "Field")
    link(tree, info, "Width", cap_v, "Width"); link(tree, info, "Height", cap_v, "Height")

    # Outputs
    link(tree, cap_w, "Grid", n_out, "New Water")
    link(tree, cap_out, "Grid", n_out, "Outflow")
    link(tree, cap_v, "Grid", n_out, "Vel Mag")

    return tree

def create_sediment_solver():
    """
    Capacity-based erosion/deposition on Soil (Bedrock unchanged).

    capacity = CapacityK * VelMag * Slope * Water
    erode    = max(0, capacity - sediment) * ErosionRate
    deposit  = max(0, sediment - capacity) * DepositionRate

    SoilNew     = max(0, Soil - erode + deposit)
    SedimentNew = max(0, Sediment + erode - deposit)
    """
    tree = get_or_create_tree("Prodigy Sediment Solver")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Sediment", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Vel Mag", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Slope", "INPUT", "ComputeSocketGrid")

    add_socket(tree, "Capacity K", "INPUT", "NodeSocketFloat", 2.0)
    add_socket(tree, "Erosion Rate", "INPUT", "NodeSocketFloat", 0.08)
    add_socket(tree, "Deposition Rate", "INPUT", "NodeSocketFloat", 0.12)

    add_socket(tree, "New Soil", "OUTPUT", "ComputeSocketGrid")
    add_socket(tree, "New Sediment", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1400, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1400, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1200, -260)
    link(tree, n_in, "Soil", info, "Grid")
    pos = nodes.new("ComputeNodePosition"); pos.location = (-1200, 160)

    # Sample fields
    def samp(name, y):
        s = nodes.new("ComputeNodeSample"); s.location = (-980, y)
        link(tree, n_in, name, s, "Grid"); link(tree, pos, "Normalized", s, "Coordinate")
        return s

    s_soil = samp("Soil", 260)
    s_wat  = samp("Water", 80)
    s_sed  = samp("Sediment", -100)
    s_vel  = samp("Vel Mag", -280)
    s_slp  = samp("Slope", -460)

    # capacity = K * vel * slope * water
    mul1 = nodes.new("ComputeNodeMath"); mul1.operation="MUL"; mul1.location = (-740, -280)
    link(tree, s_vel, "Color", mul1, 0); link(tree, s_slp, "Color", mul1, 1)

    mul2 = nodes.new("ComputeNodeMath"); mul2.operation="MUL"; mul2.location = (-520, -280)
    link(tree, mul1, "Value", mul2, 0); link(tree, s_wat, "Color", mul2, 1)

    cap = nodes.new("ComputeNodeMath"); cap.operation="MUL"; cap.location = (-300, -280)
    link(tree, mul2, "Value", cap, 0); link(tree, n_in, "Capacity K", cap, 1)

    # diff = capacity - sediment
    diff = nodes.new("ComputeNodeMath"); diff.operation="SUB"; diff.location = (-80, -200)
    link(tree, cap, "Value", diff, 0); link(tree, s_sed, "Color", diff, 1)

    # erode_amt = max(0, diff) * erosionRate
    mxE = nodes.new("ComputeNodeMath"); mxE.operation="MAX"; mxE.location = (140, -200)
    link(tree, diff, "Value", mxE, 0); set_default(mxE, 1, 0.0)

    er = nodes.new("ComputeNodeMath"); er.operation="MUL"; er.location = (360, -200)
    link(tree, mxE, "Value", er, 0); link(tree, n_in, "Erosion Rate", er, 1)

    # deposit_amt = max(0, -diff) * depositionRate  => max(0, sediment - capacity)
    diff2 = nodes.new("ComputeNodeMath"); diff2.operation="SUB"; diff2.location = (-80, -360)
    link(tree, s_sed, "Color", diff2, 0); link(tree, cap, "Value", diff2, 1)

    mxD = nodes.new("ComputeNodeMath"); mxD.operation="MAX"; mxD.location = (140, -360)
    link(tree, diff2, "Value", mxD, 0); set_default(mxD, 1, 0.0)

    dr = nodes.new("ComputeNodeMath"); dr.operation="MUL"; dr.location = (360, -360)
    link(tree, mxD, "Value", dr, 0); link(tree, n_in, "Deposition Rate", dr, 1)

    # soil_new = soil - erode + deposit
    sub = nodes.new("ComputeNodeMath"); sub.operation="SUB"; sub.location = (600, 220)
    link(tree, s_soil, "Color", sub, 0); link(tree, er, "Value", sub, 1)

    add = nodes.new("ComputeNodeMath"); add.operation="ADD"; add.location = (820, 220)
    link(tree, sub, "Value", add, 0); link(tree, dr, "Value", add, 1)

    clamp_soil = nodes.new("ComputeNodeMath"); clamp_soil.operation="MAX"; clamp_soil.location = (1040, 220)
    link(tree, add, "Value", clamp_soil, 0); set_default(clamp_soil, 1, 0.0)

    # sed_new = sed + erode - deposit
    addS = nodes.new("ComputeNodeMath"); addS.operation="ADD"; addS.location = (600, 40)
    link(tree, s_sed, "Color", addS, 0); link(tree, er, "Value", addS, 1)

    subS = nodes.new("ComputeNodeMath"); subS.operation="SUB"; subS.location = (820, 40)
    link(tree, addS, "Value", subS, 0); link(tree, dr, "Value", subS, 1)

    clamp_sed = nodes.new("ComputeNodeMath"); clamp_sed.operation="MAX"; clamp_sed.location = (1040, 40)
    link(tree, subS, "Value", clamp_sed, 0); set_default(clamp_sed, 1, 0.0)

    # Capture outputs
    comb_soil = nodes.new("ComputeNodeCombineXYZ"); comb_soil.location = (1200, 220)
    link(tree, clamp_soil, "Value", comb_soil, "X"); link(tree, clamp_soil, "Value", comb_soil, "Y"); link(tree, clamp_soil, "Value", comb_soil, "Z")
    cap_soil = nodes.new("ComputeNodeCapture"); cap_soil.location = (1320, 220)
    link(tree, comb_soil, "Vector", cap_soil, "Field")
    link(tree, info, "Width", cap_soil, "Width"); link(tree, info, "Height", cap_soil, "Height")

    comb_sed = nodes.new("ComputeNodeCombineXYZ"); comb_sed.location = (1200, 40)
    link(tree, clamp_sed, "Value", comb_sed, "X"); link(tree, clamp_sed, "Value", comb_sed, "Y"); link(tree, clamp_sed, "Value", comb_sed, "Z")
    cap_sed = nodes.new("ComputeNodeCapture"); cap_sed.location = (1320, 40)
    link(tree, comb_sed, "Vector", cap_sed, "Field")
    link(tree, info, "Width", cap_sed, "Width"); link(tree, info, "Height", cap_sed, "Height")

    link(tree, cap_soil, "Grid", n_out, "New Soil")
    link(tree, cap_sed, "Grid", n_out, "New Sediment")
    return tree

def create_thermal_talus():
    """
    Conservative thermal (talus) relaxation, implemented as a gather-based
    4-neighbour material transfer (mirrors the hydraulic gather pattern).

    For each cell, for each neighbour:
        delta = soil_center - soil_nei
        excess = max(0, abs(delta) - Talus)
        dir = max(0, delta / max(abs(delta), eps))   # 1 if center>nei else 0
        out_i = excess * dir * Strength

    Outflows are normalized so total_out <= soil_center, then we gather inflow
    from neighbour outflows (opposite channels) and update:

        new_soil = soil_center - total_out + total_in

    This yields stable, visually pleasing "bank collapse" behaviour without
    the non-conservative smoothing artefacts of naive avg-based passes.
    """
    tree = get_or_create_tree("Prodigy Thermal Talus")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Soil", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Talus", "INPUT", "NodeSocketFloat", 0.01)
    add_socket(tree, "Strength", "INPUT", "NodeSocketFloat", 0.35)
    add_socket(tree, "New Soil", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-1400, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (1700, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-1200, -260)
    link(tree, n_in, "Soil", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-1200, 200)

    # Center + neighbour samples (soil)
    sC = nodes.new("ComputeNodeSample"); sC.location = (-980, 200)
    link(tree, n_in, "Soil", sC, "Grid"); link(tree, pos, "Normalized", sC, "Coordinate")
    sE = _sample_with_offset(tree, n_in, "Soil", info, pos, +1, 0, (-980, 420))
    sW = _sample_with_offset(tree, n_in, "Soil", info, pos, -1, 0, (-980, 260))
    sN = _sample_with_offset(tree, n_in, "Soil", info, pos, 0, +1, (-980, 100))
    sS = _sample_with_offset(tree, n_in, "Soil", info, pos, 0, -1, (-980, -60))

    # Helper: outflow component to one neighbour
    def out_component(nei_sample, y):
        # delta = soil - nei
        sub = nodes.new("ComputeNodeMath"); sub.operation="SUB"; sub.location = (-720, y)
        link(tree, sC, "Color", sub, 0); link(tree, nei_sample, "Color", sub, 1)

        # abs(delta)
        ab = nodes.new("ComputeNodeMath"); ab.operation="ABS"; ab.location = (-520, y)
        link(tree, sub, "Value", ab, 0)

        # excess = max(0, abs(delta) - talus)
        sub_t = nodes.new("ComputeNodeMath"); sub_t.operation="SUB"; sub_t.location = (-320, y)
        link(tree, ab, "Value", sub_t, 0); link(tree, n_in, "Talus", sub_t, 1)

        mx_ex = nodes.new("ComputeNodeMath"); mx_ex.operation="MAX"; mx_ex.location = (-120, y)
        link(tree, sub_t, "Value", mx_ex, 0); set_default(mx_ex, 1, 0.0)

        # dir = max(0, delta / max(abs(delta), eps))
        safe = nodes.new("ComputeNodeMath"); safe.operation="MAX"; safe.location = (-520, y-120)
        link(tree, ab, "Value", safe, 0); set_default(safe, 1, 1e-6)

        div = nodes.new("ComputeNodeMath"); div.operation="DIV"; div.location = (-320, y-120)
        link(tree, sub, "Value", div, 0); link(tree, safe, "Value", div, 1)

        dirp = nodes.new("ComputeNodeMath"); dirp.operation="MAX"; dirp.location = (-120, y-120)
        link(tree, div, "Value", dirp, 0); set_default(dirp, 1, 0.0)

        # out = excess * dir * strength
        mul1 = nodes.new("ComputeNodeMath"); mul1.operation="MUL"; mul1.location = (80, y)
        link(tree, mx_ex, "Value", mul1, 0); link(tree, dirp, "Value", mul1, 1)

        mul2 = nodes.new("ComputeNodeMath"); mul2.operation="MUL"; mul2.location = (280, y)
        link(tree, mul1, "Value", mul2, 0); link(tree, n_in, "Strength", mul2, 1)
        return mul2

    oE = out_component(sE, 380)
    oW = out_component(sW, 220)
    oN = out_component(sN, 60)
    oS = out_component(sS, -100)

    # Total out
    so1 = nodes.new("ComputeNodeMath"); so1.operation="ADD"; so1.location = (520, 260)
    link(tree, oE, "Value", so1, 0); link(tree, oW, "Value", so1, 1)
    so2 = nodes.new("ComputeNodeMath"); so2.operation="ADD"; so2.location = (520, 0)
    link(tree, oN, "Value", so2, 0); link(tree, oS, "Value", so2, 1)
    tot_out = nodes.new("ComputeNodeMath"); tot_out.operation="ADD"; tot_out.location = (740, 140)
    link(tree, so1, "Value", tot_out, 0); link(tree, so2, "Value", tot_out, 1)

    # Normalize outflows so total_out <= soil_center
    safe_out = nodes.new("ComputeNodeMath"); safe_out.operation="MAX"; safe_out.location = (940, 140)
    link(tree, tot_out, "Value", safe_out, 0); set_default(safe_out, 1, 1e-6)

    ratio = nodes.new("ComputeNodeMath"); ratio.operation="DIV"; ratio.location = (1140, 140)
    link(tree, sC, "Color", ratio, 0); link(tree, safe_out, "Value", ratio, 1)

    scale = nodes.new("ComputeNodeMath"); scale.operation="MIN"; scale.location = (1340, 140)
    link(tree, ratio, "Value", scale, 0); set_default(scale, 1, 1.0)

    def scale_out(o, y):
        mul = nodes.new("ComputeNodeMath"); mul.operation="MUL"; mul.location = (1540, y)
        link(tree, o, "Value", mul, 0); link(tree, scale, "Value", mul, 1)
        return mul

    oE2, oW2, oN2, oS2 = scale_out(oE, 380), scale_out(oW, 220), scale_out(oN, 60), scale_out(oS, -100)

    tot_out2 = nodes.new("ComputeNodeMath"); tot_out2.operation="MUL"; tot_out2.location = (1540, 140)
    link(tree, tot_out, "Value", tot_out2, 0); link(tree, scale, "Value", tot_out2, 1)

    # Pack outflows in RGBA and capture to grid for neighbour sampling
    comb_out = nodes.new("ComputeNodeCombineColor"); comb_out.location = (1760, 0)
    link(tree, oE2, "Value", comb_out, "Red")
    link(tree, oW2, "Value", comb_out, "Green")
    link(tree, oN2, "Value", comb_out, "Blue")
    link(tree, oS2, "Value", comb_out, "Alpha")

    cap_out = nodes.new("ComputeNodeCapture"); cap_out.location = (1960, 0)
    link(tree, comb_out, "Color", cap_out, "Field")
    link(tree, info, "Width", cap_out, "Width"); link(tree, info, "Height", cap_out, "Height")

    # Sample neighbour outflow grids (gather inflow)
    sOE = _sample_with_offset(tree, cap_out, "Grid", info, pos, +1, 0, (2140, 420))
    sOW = _sample_with_offset(tree, cap_out, "Grid", info, pos, -1, 0, (2140, 260))
    sON = _sample_with_offset(tree, cap_out, "Grid", info, pos, 0, +1, (2140, 100))
    sOS = _sample_with_offset(tree, cap_out, "Grid", info, pos, 0, -1, (2140, -60))

    # Inflow from E neighbour uses its W channel => Green; from W uses its E => Red, etc.
    def pick_chan(sample_node, chan, y):
        sep = nodes.new("ComputeNodeSeparateColor"); sep.location = (2320, y)
        link(tree, sample_node, "Color", sep, "Color")
        return (sep, chan)

    sepE = nodes.new("ComputeNodeSeparateColor"); sepE.location = (2320, 420); link(tree, sOE, "Color", sepE, "Color")
    sepW = nodes.new("ComputeNodeSeparateColor"); sepW.location = (2320, 260); link(tree, sOW, "Color", sepW, "Color")
    sepN = nodes.new("ComputeNodeSeparateColor"); sepN.location = (2320, 100); link(tree, sON, "Color", sepN, "Color")
    sepS = nodes.new("ComputeNodeSeparateColor"); sepS.location = (2320, -60); link(tree, sOS, "Color", sepS, "Color")

    # Inflow components from neighbour outflow grid (channels: E=G, W=R, N=A, S=B)
    # (We keep them as node+socket names to match link() signature; do not store raw sockets.)
    # in_from_E = (sepE, "Green"); in_from_W = (sepW, "Red"); in_from_N = (sepN, "Alpha"); in_from_S = (sepS, "Blue")


    si1 = nodes.new("ComputeNodeMath"); si1.operation="ADD"; si1.location = (2540, 220)
    link(tree, sepE, "Green", si1, 0); link(tree, sepW, "Red", si1, 1)
    si2 = nodes.new("ComputeNodeMath"); si2.operation="ADD"; si2.location = (2540, 0)
    link(tree, sepN, "Alpha", si2, 0); link(tree, sepS, "Blue", si2, 1)
    tot_in = nodes.new("ComputeNodeMath"); tot_in.operation="ADD"; tot_in.location = (2760, 120)
    link(tree, si1, "Value", tot_in, 0); link(tree, si2, "Value", tot_in, 1)

    # new_soil = soil - tot_out_scaled + tot_in
    subN = nodes.new("ComputeNodeMath"); subN.operation="SUB"; subN.location = (2960, 120)
    link(tree, sC, "Color", subN, 0); link(tree, tot_out2, "Value", subN, 1)

    addN = nodes.new("ComputeNodeMath"); addN.operation="ADD"; addN.location = (3160, 120)
    link(tree, subN, "Value", addN, 0); link(tree, tot_in, "Value", addN, 1)

    clamp0 = nodes.new("ComputeNodeMath"); clamp0.operation="MAX"; clamp0.location = (3360, 120)
    link(tree, addN, "Value", clamp0, 0); set_default(clamp0, 1, 0.0)

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (3560, 120)
    link(tree, clamp0, "Value", comb, "X"); link(tree, clamp0, "Value", comb, "Y"); link(tree, clamp0, "Value", comb, "Z")

    cap = nodes.new("ComputeNodeCapture"); cap.location = (3760, 120)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")

    link(tree, cap, "Grid", n_out, "New Soil")
    return tree

def create_evaporation():
    """Water *= (1 - Evap Rate)."""
    tree = get_or_create_tree("Prodigy Evaporation")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Evap Rate", "INPUT", "NodeSocketFloat", 0.03)
    add_socket(tree, "New Water", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-900, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (900, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-700, -220)
    link(tree, n_in, "Water", info, "Grid")
    pos = nodes.new("ComputeNodePosition"); pos.location = (-700, 140)

    s = nodes.new("ComputeNodeSample"); s.location = (-480, 140)
    link(tree, n_in, "Water", s, "Grid"); link(tree, pos, "Normalized", s, "Coordinate")

    one_minus = nodes.new("ComputeNodeMath"); one_minus.operation="SUB"; one_minus.location = (-240, 140)
    set_default(one_minus, 0, 1.0); link(tree, n_in, "Evap Rate", one_minus, 1)

    mul = nodes.new("ComputeNodeMath"); mul.operation="MUL"; mul.location = (0, 140)
    link(tree, s, "Color", mul, 0); link(tree, one_minus, "Value", mul, 1)

    clamp0 = nodes.new("ComputeNodeMath"); clamp0.operation="MAX"; clamp0.location = (200, 140)
    link(tree, mul, "Value", clamp0, 0); set_default(clamp0, 1, 0.0)

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (420, 140)
    link(tree, clamp0, "Value", comb, "X"); link(tree, clamp0, "Value", comb, "Y"); link(tree, clamp0, "Value", comb, "Z")

    cap = nodes.new("ComputeNodeCapture"); cap.location = (640, 140)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")

    link(tree, cap, "Grid", n_out, "New Water")
    return tree


def create_surface_level():
    """Surface = Height + Water (scalar grids)."""
    tree = get_or_create_tree("Prodigy Surface Level")
    clear_tree(tree)
    tree.interface.clear()

    add_socket(tree, "Height", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Water", "INPUT", "ComputeSocketGrid")
    add_socket(tree, "Surface", "OUTPUT", "ComputeSocketGrid")

    nodes = tree.nodes
    n_in = nodes.new("ComputeNodeGroupInput"); n_in.location = (-900, 0)
    n_out = nodes.new("ComputeNodeGroupOutput"); n_out.location = (900, 0)

    info = nodes.new("ComputeNodeImageInfo"); info.location = (-700, -220)
    link(tree, n_in, "Height", info, "Grid")

    pos = nodes.new("ComputeNodePosition"); pos.location = (-700, 140)

    s_h = nodes.new("ComputeNodeSample"); s_h.location = (-480, 220)
    link(tree, n_in, "Height", s_h, "Grid"); link(tree, pos, "Normalized", s_h, "Coordinate")

    s_w = nodes.new("ComputeNodeSample"); s_w.location = (-480, 40)
    link(tree, n_in, "Water", s_w, "Grid"); link(tree, pos, "Normalized", s_w, "Coordinate")

    add = nodes.new("ComputeNodeMath"); add.operation="ADD"; add.location = (-240, 140)
    link(tree, s_h, "Color", add, 0); link(tree, s_w, "Color", add, 1)

    comb = nodes.new("ComputeNodeCombineXYZ"); comb.location = (0, 140)
    link(tree, add, "Value", comb, "X"); link(tree, add, "Value", comb, "Y"); link(tree, add, "Value", comb, "Z")

    cap = nodes.new("ComputeNodeCapture"); cap.location = (240, 140)
    link(tree, comb, "Vector", cap, "Field")
    link(tree, info, "Width", cap, "Width"); link(tree, info, "Height", cap, "Height")

    link(tree, cap, "Grid", n_out, "Surface")
    return tree

# =============================================================================
# MAIN SETUP
# =============================================================================

def setup_all():
    print("Generating Prodigy Erosion Nodes (Gaea-like)...")

    create_state_init()
    create_combine_height()
    create_gradient_fd()
    create_add_rain()
    create_surface_level()
    create_pipe_flow_step()
    create_sediment_solver()
    create_thermal_talus()
    create_evaporation()

    print("Done. Node groups created/updated.")

def create_demo_graph():
    """
    Creates a full demo graph "Erosion Demo (Prodigy)" with a clean layout.
    Tune Repeat iterations in the UI to iterate erosion.
    """
    name = "Erosion Demo (Prodigy)"
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])

    tree = bpy.data.node_groups.new(name, "ComputeNodeTree")
    nodes = tree.nodes
    links = tree.links

    # -------------------------------------------------------------------------
    # INPUT: noise -> capture grid
    # -------------------------------------------------------------------------
    noise = nodes.new("ComputeNodeNoiseTexture")
    noise.location = (-1600, 200)
    noise.inputs["Scale"].default_value = 6.0

    cap_noise = nodes.new("ComputeNodeCapture")
    cap_noise.location = (-1400, 200)
    cap_noise.inputs["Width"].default_value = 1024
    cap_noise.inputs["Height"].default_value = 1024
    links.new(noise.outputs["Color"], cap_noise.inputs["Field"])

    # -------------------------------------------------------------------------
    # INIT STATE
    # -------------------------------------------------------------------------
    init = nodes.new("ComputeNodeGroup")
    init.node_tree = bpy.data.node_groups["Prodigy State Init"]
    init.location = (-1200, 200)
    init.inputs["Rock Fraction"].default_value = 0.35
    init.inputs["Initial Water"].default_value = 0.0
    links.new(cap_noise.outputs["Grid"], init.inputs["Height"])

    # -------------------------------------------------------------------------
    # LOOP (Repeat)
    # -------------------------------------------------------------------------
    rep_in = nodes.new("ComputeNodeRepeatInput");  rep_in.location = (-900, 200)
    rep_out = nodes.new("ComputeNodeRepeatOutput"); rep_out.location = (1900, 200)
    rep_in.paired_output = rep_out.name
    rep_out.paired_input = rep_in.name

    for state_name in ["Bedrock", "Soil", "Water", "Sediment"]:
        rep_in.add_state(state_name, "ComputeSocketGrid")
        links.new(init.outputs[state_name], rep_in.inputs[state_name])
    rep_in._sync_paired_output()

    # -------------------------------------------------------------------------
    # INSIDE LOOP (left-to-right, lanes by concept)
    # -------------------------------------------------------------------------

    # Lane A: Surface / slope
    combine = nodes.new("ComputeNodeGroup")
    combine.node_tree = bpy.data.node_groups["Prodigy Combine Height"]
    combine.location = (-650, -120)
    links.new(rep_in.outputs["Bedrock"], combine.inputs["Bedrock"])
    links.new(rep_in.outputs["Soil"], combine.inputs["Soil"])

    grad = nodes.new("ComputeNodeGroup")
    grad.node_tree = bpy.data.node_groups["Prodigy Gradient FD"]
    grad.location = (-350, -120)
    links.new(combine.outputs["Height"], grad.inputs["Height"])

    # Lane B: Rain + water flow
    rain = nodes.new("ComputeNodeGroup")
    rain.node_tree = bpy.data.node_groups["Prodigy Add Rain"]
    rain.location = (-650, 220)
    rain.inputs["Rain Rate"].default_value = 0.002
    links.new(rep_in.outputs["Water"], rain.inputs["Water"])

    # Surface = Height + Water (after rain; keeps channels responsive)
    surface = nodes.new("ComputeNodeGroup")
    surface.node_tree = bpy.data.node_groups["Prodigy Surface Level"]
    surface.location = (-350, 220)
    links.new(combine.outputs["Height"], surface.inputs["Height"])
    links.new(rain.outputs["New Water"], surface.inputs["Water"])

    pipe = nodes.new("ComputeNodeGroup")
    pipe.node_tree = bpy.data.node_groups["Prodigy Pipe Flow Step"]
    pipe.location = (0, 220)
    pipe.inputs["Flow Rate"].default_value = 0.35
    links.new(surface.outputs["Surface"], pipe.inputs["Surface"])
    links.new(rain.outputs["New Water"], pipe.inputs["Water"])

    evap = nodes.new("ComputeNodeGroup")
    evap.node_tree = bpy.data.node_groups["Prodigy Evaporation"]
    evap.location = (320, 220)
    evap.inputs["Evap Rate"].default_value = 0.03
    links.new(pipe.outputs["New Water"], evap.inputs["Water"])

    # Lane C: Sediment solver
    sed = nodes.new("ComputeNodeGroup")
    sed.node_tree = bpy.data.node_groups["Prodigy Sediment Solver"]
    sed.location = (320, -120)
    sed.inputs["Capacity K"].default_value = 2.0
    sed.inputs["Erosion Rate"].default_value = 0.08
    sed.inputs["Deposition Rate"].default_value = 0.12

    links.new(rep_in.outputs["Soil"], sed.inputs["Soil"])
    links.new(evap.outputs["New Water"], sed.inputs["Water"])
    links.new(rep_in.outputs["Sediment"], sed.inputs["Sediment"])
    links.new(pipe.outputs["Vel Mag"], sed.inputs["Vel Mag"])
    links.new(grad.outputs["Slope"], sed.inputs["Slope"])

    # Lane D: Thermal talus (bank collapse)
    thermal = nodes.new("ComputeNodeGroup")
    thermal.node_tree = bpy.data.node_groups["Prodigy Thermal Talus"]
    thermal.location = (700, -120)
    thermal.inputs["Talus"].default_value = 0.01
    thermal.inputs["Strength"].default_value = 0.35
    links.new(sed.outputs["New Soil"], thermal.inputs["Soil"])

    # -------------------------------------------------------------------------
    # FEED BACK TO LOOP OUTPUT
    # -------------------------------------------------------------------------
    links.new(rep_in.outputs["Bedrock"], rep_out.inputs["Bedrock"])
    links.new(thermal.outputs["New Soil"], rep_out.inputs["Soil"])
    links.new(evap.outputs["New Water"], rep_out.inputs["Water"])
    links.new(sed.outputs["New Sediment"], rep_out.inputs["Sediment"])

    # -------------------------------------------------------------------------
    # FINAL HEIGHT OUTPUT
    # -------------------------------------------------------------------------
    combine2 = nodes.new("ComputeNodeGroup")
    combine2.node_tree = bpy.data.node_groups["Prodigy Combine Height"]
    combine2.location = (2150, 200)
    links.new(rep_out.outputs["Bedrock"], combine2.inputs["Bedrock"])
    links.new(rep_out.outputs["Soil"], combine2.inputs["Soil"])

    out_img = nodes.new("ComputeNodeOutputImage")
    out_img.location = (2400, 200)
    links.new(combine2.outputs["Height"], out_img.inputs["Grid"])

    print("Demo Graph Created:", name)

if __name__ == "__main__":
    setup_all()
    create_demo_graph()