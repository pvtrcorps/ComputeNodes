import bpy
import numpy as np

def create_ping_pong_test():
    name = "Ping Pong Test"
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    tree = bpy.data.node_groups.new(name, "ComputeNodeTree")
    nodes = tree.nodes
    links = tree.links
    
    # Repeat Input
    rep_in = nodes.new("ComputeNodeRepeatInput")
    rep_in.location = (-300, 0)
    rep_out = nodes.new("ComputeNodeRepeatOutput")
    rep_out.location = (300, 0)
    
    rep_in.paired_output = rep_out.name
    rep_out.paired_input = rep_in.name
    
    # State: "Counter" (Grid)
    # Connect an input to avoid 'state.size' unpacking bug in default initialization path
    # (This also mimics user setup)
    noise = nodes.new("ComputeNodeNoiseTexture")
    noise.location = (-700, 0)
    capt = nodes.new("ComputeNodeCapture")
    capt.location = (-500, 0)
    capt.inputs["Width"].default_value = 512
    capt.inputs["Height"].default_value = 512
    links.new(noise.outputs["Color"], capt.inputs["Field"])
    
    rep_in.add_state("Counter", "ComputeSocketGrid")
    links.new(capt.outputs["Grid"], rep_in.inputs["Counter"])
    # rep_in.inputs["Counter"].default_value = 0.0 # No longer needed with link
    
    # Add 0.01
    add = nodes.new("ComputeNodeMath")
    add.operation = "ADD"
    add.location = (0, 0)
    
    # Sample the ping buffer
    # But wait, Repeat Input outputs are *Fields* that read from the buffer?
    # Or Grids?
    # ComputeNodeRepeatInput outputs are GRIDS. 
    # To use math, we usually Sample them. 
    # But Math node accepts Color (field).
    # Does Math node auto-sample Grid?
    # Protocol: Grid -> Sample -> Field.
    
    info = nodes.new("ComputeNodeImageInfo")
    info.location = (-200, -200)
    links.new(rep_in.outputs["Counter"], info.inputs["Grid"])
    
    pos = nodes.new("ComputeNodePosition")
    pos.location = (-200, 100)
    
    samp = nodes.new("ComputeNodeSample")
    samp.location = (-100, 0)
    links.new(rep_in.outputs["Counter"], samp.inputs["Grid"])
    links.new(pos.outputs["Normalized"], samp.inputs["Coordinate"])
    
    links.new(samp.outputs["Color"], add.inputs[0])
    add.inputs[1].default_value = 0.01 # Increment
    
    # Capture back to grid
    comb = nodes.new("ComputeNodeCombineXYZ")
    comb.location = (100, 0)
    links.new(add.outputs["Value"], comb.inputs["X"])
    
    cap = nodes.new("ComputeNodeCapture")
    cap.location = (200, 0)
    links.new(comb.outputs["Vector"], cap.inputs["Field"])
    links.new(info.outputs["Width"], cap.inputs["Width"])
    links.new(info.outputs["Height"], cap.inputs["Height"])
    
    # Connect to Output
    links.new(cap.outputs["Grid"], rep_out.inputs["Counter"])
    
    # Output Image to verify
    out_img = nodes.new("ComputeNodeOutputImage")
    out_img.location = (500, 0)
    links.new(rep_out.outputs["Counter"], out_img.inputs["Grid"])
    
    # Set iterations
    # How? Repeat Input has 'iterations' property? 
    # Let's find it. Usually rep_in.iterations
    rep_in.iterations = 100

    print("Ping Pong Test graph created.")
    return tree

if __name__ == "__main__":
    create_ping_pong_test()
