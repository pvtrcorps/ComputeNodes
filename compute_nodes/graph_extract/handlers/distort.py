# Distort Handler
# Handles: ComputeNodeDistort
# High-level helper: auto-bakes inputs then samples with offset

from ...ir.ops import OpCode
from ...ir.resources import ImageDesc, ResourceAccess
from ...ir.types import DataType


def handle_distort(node, ctx):
    """
    Handle ComputeNodeDistort node.
    
    Bakes both value and offset inputs, then samples with distortion.
    
    CRITICAL: The order of op emission matters! The scheduler splits passes
    at IMAGE_STORE operations. So we must emit all sampling-related ops
    AFTER the stores to ensure they're in the sampling pass, not the bake pass.
    """
    builder = ctx['builder']
    get_socket_value = ctx['get_socket_value']
    socket_value_map = ctx['socket_value_map']
    get_socket_key = ctx['get_socket_key']
    
    # Get inputs
    val_input = get_socket_value(node.inputs[0])
    val_offset = get_socket_value(node.inputs[1])
    
    if val_input is None:
        val_input = builder.constant((0.0, 0.0, 0.0, 1.0), DataType.VEC4)
    
    if val_offset is None:
        val_offset = builder.constant((0.0, 0.0, 0.0), DataType.VEC3)
    
    width = node.width
    height = node.height
    strength = node.strength
    
    # === PHASE 1: Create resources ===
    bake_value_desc = ImageDesc(
        name=f"distort_val_{node.name}",
        access=ResourceAccess.READ_WRITE,
        format="rgba32f",
        size=(width, height),
        dimensions=2
    )
    val_baked_value = builder.add_resource(bake_value_desc)
    
    bake_offset_desc = ImageDesc(
        name=f"distort_off_{node.name}",
        access=ResourceAccess.READ_WRITE,
        format="rgba32f",
        size=(width, height),
        dimensions=2
    )
    val_baked_offset = builder.add_resource(bake_offset_desc)
    
    # === PHASE 2: Emit ALL store operations (these define pass boundary) ===
    
    # Prepare and store value
    if val_input.type == DataType.HANDLE:
        val_gid_v = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_coord_v = builder.swizzle(val_gid_v, "xy")
        val_coord_v_ivec = builder.cast(val_coord_v, DataType.IVEC2)
        val_to_bake = builder.image_load(val_input, val_coord_v_ivec)
    else:
        val_to_bake = val_input
        if val_to_bake.type == DataType.VEC3:
            val_to_bake = builder.cast(val_to_bake, DataType.VEC4)
        elif val_to_bake.type == DataType.FLOAT:
            val_to_bake = builder.cast(val_to_bake, DataType.VEC4)
    
    val_gid1 = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_coord1 = builder.swizzle(val_gid1, "xy")
    val_coord1_ivec = builder.cast(val_coord1, DataType.IVEC2)
    builder.image_store(val_baked_value, val_coord1_ivec, val_to_bake)
    
    # Prepare and store offset
    if val_offset.type == DataType.HANDLE:
        val_gid_o = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_coord_o = builder.swizzle(val_gid_o, "xy")
        val_coord_o_ivec = builder.cast(val_coord_o, DataType.IVEC2)
        val_offset_to_bake = builder.image_load(val_offset, val_coord_o_ivec)
    else:
        val_offset_to_bake = val_offset
        if val_offset_to_bake.type == DataType.VEC3:
            val_offset_to_bake = builder.cast(val_offset_to_bake, DataType.VEC4)
        elif val_offset_to_bake.type == DataType.VEC2:
            val_offset_to_bake = builder.cast(val_offset_to_bake, DataType.VEC4)
        elif val_offset_to_bake.type == DataType.FLOAT:
            val_offset_to_bake = builder.cast(val_offset_to_bake, DataType.VEC4)
    
    val_gid2 = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_coord2 = builder.swizzle(val_gid2, "xy")
    val_coord2_ivec = builder.cast(val_coord2, DataType.IVEC2)
    builder.image_store(val_baked_offset, val_coord2_ivec, val_offset_to_bake)
    
    # === PHASE 3: Emit ALL sampling operations (AFTER stores) ===
    # These will be in a new pass after the RAW hazard detection
    
    # Create fresh coords for loading offset (MUST be emitted HERE not before stores)
    val_gid3 = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
    val_coord3 = builder.swizzle(val_gid3, "xy")
    val_coord3_ivec = builder.cast(val_coord3, DataType.IVEC2)
    
    # Load offset from baked texture
    val_loaded_offset = builder.image_load(val_baked_offset, val_coord3_ivec)
    val_offset_xy = builder.swizzle(val_loaded_offset, "xy")
    
    # Apply distortion
    val_strength = builder.constant(strength, DataType.FLOAT)
    val_scaled_offset = builder.mul(val_offset_xy, val_strength)
    
    val_coord3_float = builder.cast(val_coord3, DataType.VEC2)
    val_half = builder.constant((0.5, 0.5), DataType.VEC2)
    val_center = builder.add(val_coord3_float, val_half)
    val_size = builder.constant((float(width), float(height)), DataType.VEC2)
    val_base_uv = builder.div(val_center, val_size)
    val_distorted_uv = builder.add(val_base_uv, val_scaled_offset)
    
    # Sample baked value with distorted coords
    val_sampled = builder.sample(val_baked_value, val_distorted_uv)
    
    # Store result
    out_key = get_socket_key(node.outputs[0])
    socket_value_map[out_key] = val_sampled
    
    return val_sampled

