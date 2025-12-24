
import logging
from typing import Dict, Any, List, Set, Optional
from .ir.graph import Graph, IRBuilder, Value, ValueKind
from .ir.ops import OpCode
from .ir.resources import ImageDesc, ResourceAccess, ResourceType
from .ir.types import DataType

logger = logging.getLogger(__name__)

# Mock BPY for separate testing if needed, or assume running in Blender
try:
    import bpy
except ImportError:
    bpy = None

def extract_graph(nodetree) -> Graph:
    """
    Converts a ComputeNodeTree into an IR Graph.
    Refined Version: Stable keys, Strict types, Validation.
    """
    graph = Graph(name=nodetree.name)
    builder = IRBuilder(graph)
    
    # Map: Socket Pointer (int) -> Value (SSA)
    # Using pointer for stability across python object recreations (if pointer persists during extraction)
    # or to resolve hash issues.
    socket_value_map: Dict[int, Value] = {}
    
    # Recursion stack for cycle detection
    # Set of (node.as_pointer, output_index) or similar unique ID
    # Actually just tracking nodes in current path is enough for basic cycle detection
    recursion_stack: Set[int] = set()
    
    # Find Output Node (Assuming one for MVP)
    # Find Output Nodes
    output_nodes = []
    for node in nodetree.nodes:
        if node.bl_idname == 'ComputeNodeOutput':
            output_nodes.append(node)
            
    if not output_nodes:
        logger.warning("No Output Node found")
        return graph

    def get_socket_key(socket):
        # Use as_pointer if available (Blender), else id()
        if hasattr(socket, "as_pointer"):
            return socket.as_pointer()
        return id(socket)

    def get_node_key(node):
        if hasattr(node, "as_pointer"):
            return node.as_pointer()
        return id(node)

    # Recursive extraction helper
    def get_socket_value(socket) -> Value:
        key = get_socket_key(socket)
        if key in socket_value_map:
            return socket_value_map[key]
            
        # If linked, traverse
        if socket.is_linked:
            if len(socket.links) > 1:
                raise ValueError(f"Socket {socket.name} has multiple links, which is not supported for Inputs.")
            
            link = socket.links[0]
            from_socket = link.from_socket
            from_node = link.from_node
            
            # Recursive call to process dependency
            val = process_node(from_node, from_socket)
            socket_value_map[key] = val
            return val
        else:
             # Not linked: Use default value
             if hasattr(socket, "default_value"):
                 # Handle ComputeSocketImage default value (PointerProperty)
                 if socket.bl_idname == 'ComputeSocketImage':
                     img = socket.default_value
                     if not img:
                         return None
                     
                     # Determine format
                     fmt = "rgba32f" if img.is_float else "rgba8"
                     # Determine Access: If it's an Input Socket, assume READ.
                     # Context is hard to know here without node type, but usually inputs are Reads.
                     # Output Node's "Target Image" is an Input Socket, but used for Write.
                     # We might need to defer access decision or infer it.
                     # For now, let's treat it as a READ resource by default (like Image Input node).
                     # IMPORTANT: The Output node extraction logic (later in file) handles its specific input socket
                     # by looking at the Value. If we return a Resource Value here, it should work.
                     # HOWEVER, ImageDesc needs access.
                     
                     # HACK/HEURISTIC: If socket name implies target/output, or if we can infer.
                     # Better: Create a RESOURCE value. The usage in the node determines the binding access (read vs write)
                     # BUT `builder.add_resource` takes an `ImageDesc` which requires `access`.
                     # Let's verify how `Image Input` does it -> Access READ.
                     # Let's verify how `Output Node` does it -> It expects a resource.
                     # The graph resource list stores descriptors.
                     # Problem: If we declare it READ here, but Output Node writes to it, is that a conflict?
                     # The `glsl.py` binding generator unites reads/writes.
                     # If we tag it READ here, `compute_pass.writes.add(res_idx)` will still happen in `image_store`.
                     # So it should be fine to default to READ.
                     
                     desc = ImageDesc(name=img.name, access=ResourceAccess.READ, format=fmt)
                     val = builder.add_resource(desc)
                     socket_value_map[key] = val
                     return val

                 # Determine type based on socket type
                 dtype = DataType.FLOAT 
                 if socket.type == 'VECTOR': dtype = DataType.VEC3
                 elif socket.type == 'RGBA': dtype = DataType.VEC4
                 elif socket.type == 'INT': dtype = DataType.INT
                 elif socket.type == 'BOOLEAN': dtype = DataType.BOOL
                 
                 const_val = builder.constant(socket.default_value, dtype)
                 socket_value_map[key] = const_val
                 return const_val
             
             # Unlinked non-value socket (e.g. image input not connected)
             return None 

    def process_node(node, output_socket_needed=None) -> Value:
        node_key = get_node_key(node)
        if node_key in recursion_stack:
            raise RecursionError(f"Cycle detected at node {node.name}")
        
        recursion_stack.add(node_key)
        
        try:
            # 1. Image Input (Read)
            if node.bl_idname == 'ComputeNodeImageInput':
                img = node.image
                if not img:
                    # Fallback
                    val = builder.constant(0.0, DataType.FLOAT)
                else:
                    # Detect format
                    fmt = "rgba32f" if img.is_float else "rgba8"
                    desc = ImageDesc(name=img.name, access=ResourceAccess.READ, format=fmt)
                    val = builder.add_resource(desc)
                
                # Cache output
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val
                return val

            # 1b. Image Write (Storage)
            elif node.bl_idname == 'ComputeNodeImageWrite':
                img = node.image
                if not img:
                    val = builder.constant(0.0, DataType.FLOAT) # Error state?
                else:
                    fmt = "rgba32f" if img.is_float else "rgba8"
                    desc = ImageDesc(name=img.name, access=ResourceAccess.WRITE, format=fmt)
                    val = builder.add_resource(desc)
                
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val
                return val

            # 2. Math
            elif node.bl_idname == 'ComputeNodeMath':
                # Inputs
                val_a = get_socket_value(node.inputs[0])
                val_b = get_socket_value(node.inputs[1])
                
                # Validation: None check
                if val_a is None: val_a = builder.constant(0.0, DataType.FLOAT)
                if val_b is None: val_b = builder.constant(0.0, DataType.FLOAT)

                # Enforce FLOAT type for Scalar Math
                if val_a.type != DataType.FLOAT: val_a = builder.cast(val_a, DataType.FLOAT)
                if val_b.type != DataType.FLOAT: val_b = builder.cast(val_b, DataType.FLOAT)
                
                if val_b.type != DataType.FLOAT: val_b = builder.cast(val_b, DataType.FLOAT)
                
                op_str = node.operation
                
                # Manual Mapping for mismatches
                op_map = {
                    'LESS_THAN': OpCode.LT,
                    'GREATER_THAN': OpCode.GT,
                    'MODULO': OpCode.MOD,
                }
                
                opcode = op_map.get(op_str)
                if opcode is None:
                     opcode = getattr(OpCode, op_str, OpCode.ADD)
                
                # Check for 3rd input (Ternary)
                val_c = None
                if opcode in {OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.COMPARE, OpCode.SMOOTH_MIN, OpCode.SMOOTH_MAX, OpCode.CLAMP, OpCode.MIX}:
                    # Inputs: 0, 1, 2
                    if len(node.inputs) > 2:
                        val_c = get_socket_value(node.inputs[2])
                
                # Clamp often uses min/max, but here it's 3 args
                
                inputs = [val_a, val_b]
                if val_c:
                    if val_c.type != DataType.FLOAT: val_c = builder.cast(val_c, DataType.FLOAT)
                    inputs.append(val_c)
                elif opcode == OpCode.COMPARE:
                     # Compare needs epsilon if not provided?
                     # If only 2 inputs linked, but Compare, defaults to 0? 
                     # Should implement check.
                     # But graph extract just uses what's there.
                     if len(inputs) < 3:
                         inputs.append(builder.constant(0.00001, DataType.FLOAT))

                val_out = None
                try:
                    # Generic Add Op
                    op = builder.add_op(opcode, inputs)
                    val_out = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                    op.add_output(val_out)
                except TypeError as e:
                    # Provide context about which node failed
                    raise TypeError(f"Node '{node.name}': {e}") from e
                
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val_out
                return val_out

            # 3. Image Info (Size)
            elif node.bl_idname == 'ComputeNodeImageInfo':
                # Input Image
                val_img = get_socket_value(node.inputs[0])
                if not val_img:
                    # Fallback default size? Or (0,0)?
                    val_size = builder.constant((0,0), DataType.IVEC2)
                else:
                    if val_img.type != DataType.HANDLE:
                         raise TypeError(f"Node '{node.name}': Input must be an Image (got {val_img.type.name})")
                    val_size = builder.image_size(val_img)
                
                # Output
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val_size
                return val_size
                
            # 4. Position
            elif node.bl_idname == 'ComputeNodePosition':
                # Builtin: gl_GlobalInvocationID -> uvec3
                val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
                # Cast to VEC3 (Coordinate for generic use)
                # vec3(uvec3) works in GLSL
                val_pos = builder.cast(val_gid, DataType.VEC3)
                
                out_key = get_socket_key(node.outputs[0]) # "Coordinate"
                socket_value_map[out_key] = val_pos

                # Normalized Output
                if len(node.outputs) > 1:
                    val_num_wg = builder.builtin("gl_NumWorkGroups", DataType.UVEC3)
                    val_wg_size = builder.builtin("gl_WorkGroupSize", DataType.UVEC3)
                    
                    # Total Size = NumWG * WGSize
                    op_size = builder.add_op(OpCode.MUL, [val_num_wg, val_wg_size])
                    val_size = builder._new_value(ValueKind.SSA, DataType.UVEC3, origin=op_size)
                    op_size.add_output(val_size)
                    
                    val_size_f = builder.cast(val_size, DataType.VEC3)
                    
                    op_div = builder.add_op(OpCode.DIV, [val_pos, val_size_f])
                    val_norm = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op_div)
                    op_div.add_output(val_norm)
                    
                    out_key_norm = get_socket_key(node.outputs[1])
                    socket_value_map[out_key_norm] = val_norm

                # Global Index Output
                if len(node.outputs) > 2:
                    # Index = y * width + x
                    # We need Width (Total Size X)
                    # We already computed val_size (UVEC3) above if Normalized is used.
                    # But we can't guarantee Normalized is connected/processed.
                    # Safest is to re-fetch size or cache it.
                    # For simplicity/robustness, we re-fetch builtins specific for this calc.
                    
                    # Ensure we have what we need
                    val_gid_uvec = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
                    val_num_wg = builder.builtin("gl_NumWorkGroups", DataType.UVEC3)
                    val_wg_size = builder.builtin("gl_WorkGroupSize", DataType.UVEC3)
                    
                    # Calculate Width (Size.x)
                    op_size = builder.add_op(OpCode.MUL, [val_num_wg, val_wg_size])
                    val_size = builder._new_value(ValueKind.SSA, DataType.UVEC3, origin=op_size)
                    op_size.add_output(val_size)
                    
                    # Extract Components
                    val_x = builder.swizzle(val_gid_uvec, "x")
                    val_y = builder.swizzle(val_gid_uvec, "y")
                    val_width = builder.swizzle(val_size, "x")
                    
                    # We need UINT or INT math. GLSL supports uint fine.
                    # Index = y * width + x
                    op_mul_idx = builder.add_op(OpCode.MUL, [val_y, val_width])
                    val_y_w = builder._new_value(ValueKind.SSA, DataType.UINT, origin=op_mul_idx)
                    op_mul_idx.add_output(val_y_w)
                    
                    op_add_idx = builder.add_op(OpCode.ADD, [val_y_w, val_x])
                    val_idx_uint = builder._new_value(ValueKind.SSA, DataType.UINT, origin=op_add_idx)
                    op_add_idx.add_output(val_idx_uint)
                    
                    # Cast to INT for standard socket
                    val_idx_int = builder.cast(val_idx_uint, DataType.INT)
                    
                    out_key_idx = get_socket_key(node.outputs[2])
                    socket_value_map[out_key_idx] = val_idx_int

                if output_socket_needed:
                    req_key = get_socket_key(output_socket_needed)
                    if req_key in socket_value_map:
                        return socket_value_map[req_key]
                return val_pos

            # 5. Sample
            elif node.bl_idname == 'ComputeNodeSample':
                # Inputs
                val_img = get_socket_value(node.inputs[0])
                val_coord = get_socket_value(node.inputs[1])
                
                if val_img is None:
                    # Fallback black
                    val_out = builder.constant((0.0,0.0,0.0,0.0), DataType.VEC4)
                else:
                    if val_coord is None:
                        # Fallback coord (0,0)
                        val_coord = builder.constant((0,0), DataType.IVEC2)
                    
                    # Ensure coord is IVEC2 (for imageLoad/texelFetch)
                    # If it's VEC3/VEC2, cast to IVEC2
                    if val_coord.type != DataType.IVEC2:
                        val_coord = builder.cast(val_coord, DataType.IVEC2)
                        
                    val_out = builder.image_load(val_img, val_coord)
                    
                out_key = get_socket_key(node.outputs[0]) # "Color"
                socket_value_map[out_key] = val_out
                return val_out

            # 6. Vector Math
            elif node.bl_idname == 'ComputeNodeVectorMath':
                val_a = get_socket_value(node.inputs[0])
                val_b = get_socket_value(node.inputs[1])
                
                if val_a is None: val_a = builder.constant((0.0,0.0,0.0), DataType.VEC3)
                if val_b is None: val_b = builder.constant((0.0,0.0,0.0), DataType.VEC3)

                # Enforce VEC3 type for Vector Math
                if val_a.type != DataType.VEC3: val_a = builder.cast(val_a, DataType.VEC3)
                if val_b.type != DataType.VEC3: val_b = builder.cast(val_b, DataType.VEC3)
                
                if val_b.type != DataType.VEC3: val_b = builder.cast(val_b, DataType.VEC3)
                
                op_str = node.operation
                
                op_map = {
                    'MINIMUM': OpCode.MIN,
                    'MAXIMUM': OpCode.MAX,
                    'MODULO': OpCode.MOD,
                    'SINE': OpCode.SIN,
                    'COSINE': OpCode.COS,
                    'TANGENT': OpCode.TAN,
                    'FRACTION': OpCode.FRACT,
                }
                opcode = op_map.get(op_str)
                if opcode is None:
                    opcode = getattr(OpCode, op_str, OpCode.ADD)
                
                res_type = DataType.VEC3
                is_float_out = False
                
                inputs = [val_a, val_b]
                
                # Unary
                if opcode in {OpCode.LENGTH, OpCode.NORMALIZE, OpCode.ABS, OpCode.FLOOR, OpCode.CEIL, OpCode.FRACT, OpCode.SIN, OpCode.COS, OpCode.TAN}:
                    inputs = [val_a]
                
                # Ternary
                if opcode in {OpCode.MULTIPLY_ADD, OpCode.WRAP, OpCode.REFRACT, OpCode.FACEFORWARD}:
                    if len(node.inputs) > 2:
                        val_c = get_socket_value(node.inputs[2])
                        if val_c is None: val_c = builder.constant((0,0,0), DataType.VEC3) # Default
                        # Check type? Usually VEC3
                        inputs.append(val_c)
                
                # Mixed Inputs (Scale, FaceForward params?)
                if opcode == OpCode.SCALE:
                    # Inputs[0] (Vector), Inputs[3] (Scale)
                    # Note: We hardcoded input indices in 'get_socket_value' calls above.
                    # val_a is inputs[0], val_b is inputs[1].
                    # For Scale, val_b is irrelevant? 
                    # We need inputs[3]
                    if len(node.inputs) > 3:
                        val_scale = get_socket_value(node.inputs[3])
                        if val_scale is None: val_scale = builder.constant(1.0, DataType.FLOAT)
                        inputs = [val_a, val_scale] # Vec, Float
                    else:
                        inputs = [val_a, builder.constant(1.0, DataType.FLOAT)]
                        
                elif opcode == OpCode.REFRACT:
                     # Inputs: Vec(0), Normal(? 1), IOR(3) ??
                     # My Node: Vector(0), Vector(1), Scale(3) [Renamed IOR]
                     # So inputs = [val_a, val_b, val_ior]
                     if len(node.inputs) > 3:
                        val_ior = get_socket_value(node.inputs[3])
                        if val_ior is None: val_ior = builder.constant(1.45, DataType.FLOAT)
                        inputs = [val_a, val_b, val_ior]
                
                
                
                res_type = DataType.VEC3
                is_float_out = False
                
                if opcode in {OpCode.DOT, OpCode.DISTANCE}:
                    res_type = DataType.FLOAT
                    is_float_out = True
                elif opcode == OpCode.LENGTH: # Unary
                    res_type = DataType.FLOAT
                    is_float_out = True
                elif opcode == OpCode.NORMALIZE: # Unary
                    res_type = DataType.VEC3
                elif opcode == OpCode.CROSS:
                    res_type = DataType.VEC3
                elif opcode == OpCode.REFLECT:
                    res_type = DataType.VEC3
                
                # Unary check
                inputs = [val_a, val_b]
                if opcode in {OpCode.LENGTH, OpCode.NORMALIZE}:
                    inputs = [val_a] # Unary
                    
                # Create Op
                op = builder.add_op(opcode, inputs)
                val_res = builder._new_value(ValueKind.SSA, res_type, origin=op)
                op.add_output(val_res)
                
                if is_float_out:
                    # Result is Float -> "Value" socket (Index 1)
                    out_key_val = get_socket_key(node.outputs[1])
                    socket_value_map[out_key_val] = val_res
                    
                    # Map "Vector" to splatted float (for safety)
                    val_vec = builder.cast(val_res, DataType.VEC3)
                    out_key_vec = get_socket_key(node.outputs[0])
                    socket_value_map[out_key_vec] = val_vec
                else:
                    # Result is Vector -> "Vector" socket (Index 0)
                    out_key_vec = get_socket_key(node.outputs[0])
                    socket_value_map[out_key_vec] = val_res
                    
                    # Map "Value" to 0.0 (for safety)
                    out_key_val = get_socket_key(node.outputs[1])
                    socket_value_map[out_key_val] = builder.constant(0.0, DataType.FLOAT)
                    
                if output_socket_needed:
                    req_key = get_socket_key(output_socket_needed)
                    if req_key in socket_value_map:
                        return socket_value_map[req_key]
                return val_res
            
            # 7. Switch (If/Else)
            elif node.bl_idname == 'ComputeNodeSwitch':
                # Inputs: Switch (Bool), False, True
                # Output: Output
                val_sw = get_socket_value(node.inputs[0]) # Bool/Float 0-1
                val_false = get_socket_value(node.inputs[1])
                val_true = get_socket_value(node.inputs[2])
                
                # Defaults
                if val_sw is None: val_sw = builder.constant(0.0, DataType.FLOAT)
                if val_false is None: val_false = builder.constant(0.0, DataType.FLOAT)
                if val_true is None: val_true = builder.constant(0.0, DataType.FLOAT)
                
                target_type = DataType.FLOAT
                if node.data_type == 'VEC3': target_type = DataType.VEC3
                elif node.data_type == 'RGBA': target_type = DataType.VEC4
                
                # Casts
                val_sw = builder.cast(val_sw, DataType.FLOAT)
                val_false = builder.cast(val_false, target_type)
                val_true = builder.cast(val_true, target_type)
                
                # GLSL mix(x, y, a) => x*(1-a) + y*a
                # Blender Switch: False is input 0 (x), True is input 1 (y).
                # So mix(False, True, Switch)
                
                op = builder.add_op(OpCode.SELECT, [val_false, val_true, val_sw])
                val_res = builder._new_value(ValueKind.SSA, target_type, origin=op)
                op.add_output(val_res)
                
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val_res
                return val_res

            # 7b. Mix
            elif node.bl_idname == 'ComputeNodeMix':
                # Inputs: Factor, A, B
                # Output: Result
                val_fac = get_socket_value(node.inputs[0])
                val_a = get_socket_value(node.inputs[1]) # Base
                val_b = get_socket_value(node.inputs[2]) # Blend input
                
                if val_fac is None: val_fac = builder.constant(0.5, DataType.FLOAT)
                if val_a is None: val_a = builder.constant(0.0, DataType.FLOAT)
                if val_b is None: val_b = builder.constant(0.0, DataType.FLOAT)
                
                target_type = DataType.FLOAT
                if node.data_type == 'VEC3': target_type = DataType.VEC3
                elif node.data_type == 'RGBA': target_type = DataType.VEC4
                
                val_fac = builder.cast(val_fac, DataType.FLOAT)
                val_a = builder.cast(val_a, target_type)
                val_b = builder.cast(val_b, target_type)
                
                # Determine Blend logic
                # Result = mix(A, BlendFunc(A, B), Factor)
                
                val_blend = val_b # Default for MIX mode (B)
                
                mode = 'MIX'
                if hasattr(node, "blend_type") and node.data_type == 'RGBA':
                    mode = node.blend_type
                    
                if mode == 'ADD':
                    # Blend = A + B
                    op_add = builder.add_op(OpCode.ADD, [val_a, val_b])
                    val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_add)
                    op_add.add_output(val_blend)
                elif mode == 'MULTIPLY':
                    # Blend = A * B
                    op_mul = builder.add_op(OpCode.MUL, [val_a, val_b])
                    val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_mul)
                    op_mul.add_output(val_blend)
                elif mode == 'SUBTRACT':
                    # Blend = A - B
                    op_sub = builder.add_op(OpCode.SUB, [val_a, val_b])
                    val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_sub)
                    op_sub.add_output(val_blend)
                elif mode == 'DIVIDE':
                    # Blend = A / B
                    op_div = builder.add_op(OpCode.DIV, [val_a, val_b])
                    val_blend = builder._new_value(ValueKind.SSA, target_type, origin=op_div)
                    op_div.add_output(val_blend)
                
                # Final Mix
                # mix(A, Blend, Factor)
                op_mix = builder.add_op(OpCode.SELECT, [val_a, val_blend, val_fac])
                val_res = builder._new_value(ValueKind.SSA, target_type, origin=op_mix)
                op_mix.add_output(val_res)
                
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val_res
                return val_res

            # 8. Noise Texture
            elif node.bl_idname == 'ComputeNodeNoiseTexture':
                # Inputs: [Vector, W, Scale, Detail, Roughness, Lacunarity, Offset]
                val_vec = get_socket_value(node.inputs[0]) 
                val_w = get_socket_value(node.inputs[1])
                val_scale = get_socket_value(node.inputs[2])
                val_detail = get_socket_value(node.inputs[3])
                val_rough = get_socket_value(node.inputs[4])
                val_lacu = get_socket_value(node.inputs[5])
                val_offset = get_socket_value(node.inputs[6])
                
                # Check Vector Input (Map coords)
                if val_vec is None:
                     # Default to Position/Coordinate
                     # We reuse the logic from ComputeNodePosition essentially, or assume generic coord.
                     # But IRBuilder.add_op(NOISE) expects a value.
                     # Let's create a temporary Position value if not linked.
                     val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
                     val_vec = builder.cast(val_gid, DataType.VEC3)
                
                # Defaults for others
                if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
                if val_scale is None: val_scale = builder.constant(5.0, DataType.FLOAT)
                if val_detail is None: val_detail = builder.constant(2.0, DataType.FLOAT)
                if val_rough is None: val_rough = builder.constant(0.5, DataType.FLOAT)
                if val_lacu is None: val_lacu = builder.constant(2.0, DataType.FLOAT)
                if val_offset is None: val_offset = builder.constant(0.0, DataType.FLOAT)
                
                # Ensure types
                if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
                if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
                # ... others are floats ...
                
                inputs = [val_vec, val_w, val_scale, val_detail, val_rough, val_lacu, val_offset]
                
                attrs = {
                    'dimensions': node.dimensions,
                    'normalize': node.normalize
                }
                
                op = builder.add_op(OpCode.NOISE, inputs, attrs)
                
                # Outputs: Fac (Float), Color (Color/Vec4)
                val_fac = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
                op.add_output(val_fac)
                op.add_output(val_col)
                
                # Map Sockets
                key_fac = get_socket_key(node.outputs[0])
                socket_value_map[key_fac] = val_fac
                
                key_col = get_socket_key(node.outputs[1])
                socket_value_map[key_col] = val_col
                
                if output_socket_needed:
                    req_key = get_socket_key(output_socket_needed)
                    if req_key in socket_value_map:
                        return socket_value_map[req_key]
                return val_fac

            # 9b. White Noise
            elif node.bl_idname == 'ComputeNodeWhiteNoise':
                val_vec = get_socket_value(node.inputs[0]) 
                val_w = get_socket_value(node.inputs[1])
                
                # Defaults
                if val_vec is None:
                     val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
                     val_vec = builder.cast(val_gid, DataType.VEC3)
                
                if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
                
                if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
                if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
                
                inputs = [val_vec, val_w]
                attrs = {'dimensions': node.dimensions}
                
                op = builder.add_op(OpCode.WHITE_NOISE, inputs, attrs)
                
                # Outputs
                val_val = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
                op.add_output(val_val)
                op.add_output(val_col)
                
                key_val = get_socket_key(node.outputs[0])
                socket_value_map[key_val] = val_val
                
                key_col = get_socket_key(node.outputs[1])
                socket_value_map[key_col] = val_col
                

                if output_socket_needed:
                    req_key = get_socket_key(output_socket_needed)
                    if req_key in socket_value_map:
                        return socket_value_map[req_key]
                return val_val

            # 9c. Voronoi Texture
            elif node.bl_idname == 'ComputeNodeVoronoiTexture':
                # Inputs
                val_vec = get_socket_value(node.inputs[0])
                val_w = get_socket_value(node.inputs[1])
                val_scale = get_socket_value(node.inputs[2])
                val_detail = get_socket_value(node.inputs[3])
                val_rough = get_socket_value(node.inputs[4])
                val_lacu = get_socket_value(node.inputs[5])
                val_smooth = get_socket_value(node.inputs[6])
                val_exp = get_socket_value(node.inputs[7])
                val_rand = get_socket_value(node.inputs[8])
                
                # Defaults
                if val_vec is None:
                     val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
                     val_vec = builder.cast(val_gid, DataType.VEC3)
                
                if val_w is None: val_w = builder.constant(0.0, DataType.FLOAT)
                if val_scale is None: val_scale = builder.constant(5.0, DataType.FLOAT)
                if val_detail is None: val_detail = builder.constant(0.0, DataType.FLOAT)
                if val_rough is None: val_rough = builder.constant(0.5, DataType.FLOAT)
                if val_lacu is None: val_lacu = builder.constant(2.0, DataType.FLOAT)
                if val_smooth is None: val_smooth = builder.constant(1.0, DataType.FLOAT)
                if val_exp is None: val_exp = builder.constant(1.0, DataType.FLOAT)
                if val_rand is None: val_rand = builder.constant(1.0, DataType.FLOAT)

                # Type Casting
                if val_vec.type != DataType.VEC3: val_vec = builder.cast(val_vec, DataType.VEC3)
                if val_w.type != DataType.FLOAT: val_w = builder.cast(val_w, DataType.FLOAT)
                if val_scale.type != DataType.FLOAT: val_scale = builder.cast(val_scale, DataType.FLOAT)
                if val_detail.type != DataType.FLOAT: val_detail = builder.cast(val_detail, DataType.FLOAT)
                if val_rough.type != DataType.FLOAT: val_rough = builder.cast(val_rough, DataType.FLOAT)
                if val_lacu.type != DataType.FLOAT: val_lacu = builder.cast(val_lacu, DataType.FLOAT)
                if val_smooth.type != DataType.FLOAT: val_smooth = builder.cast(val_smooth, DataType.FLOAT)
                if val_exp.type != DataType.FLOAT: val_exp = builder.cast(val_exp, DataType.FLOAT)
                if val_rand.type != DataType.FLOAT: val_rand = builder.cast(val_rand, DataType.FLOAT)
                
                inputs = [val_vec, val_w, val_scale, val_detail, val_rough, val_lacu, val_smooth, val_exp, val_rand]
                
                attrs = {
                    'dimensions': node.dimensions,
                    'feature': node.feature,
                    'metric': node.metric,
                    'normalize': node.normalize
                }
                
                op = builder.add_op(OpCode.VORONOI, inputs, attrs)
                
                # Outputs: Distance, Color, Position, W, Radius
                # Note: Not all are valid for all features, but we create them conceptually
                val_dist = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                val_col = builder._new_value(ValueKind.SSA, DataType.VEC4, origin=op)
                val_pos = builder._new_value(ValueKind.SSA, DataType.VEC3, origin=op)
                val_out_w = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                val_rad = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op)
                
                op.add_output(val_dist)
                op.add_output(val_col)
                op.add_output(val_pos)
                op.add_output(val_out_w)
                op.add_output(val_rad)
                
                socket_value_map[get_socket_key(node.outputs[0])] = val_dist
                socket_value_map[get_socket_key(node.outputs[1])] = val_col
                socket_value_map[get_socket_key(node.outputs[2])] = val_pos
                socket_value_map[get_socket_key(node.outputs[3])] = val_out_w
                socket_value_map[get_socket_key(node.outputs[4])] = val_rad
                
                if output_socket_needed:
                    req_key = get_socket_key(output_socket_needed)
                    if req_key in socket_value_map:
                        return socket_value_map[req_key]
                return val_dist


            # 9. Repeat Zone (Naive Loop Extraction)
            elif node.bl_idname == 'ComputeNodeRepeatOutput':
                # Inputs: Next Value
                # Outputs: Final Result (this is what we are computing now)
                
                # 1. Find our paired Input node
                # We assume simple topology: Trace back from "Next Value" input? 
                # No, that traces the loop BODY. We need to find the Loop Header.
                # Since we don't have explicit pairing IDs, we have to search the graph or assume topological connection?
                # BETTER: Traverse the entire graph to find which RepeatInput feeds us? 
                # OR: Backtrack from 'Next Value' until we hit a RepeatInput?
                # Issue: Multiple Repeat Zones.
                # STRATEGY: Find the unique RepeatInput that is reachable from 'Next Value' AND has 'Iterations' linked/set.
                # Actually, simpler: Search all nodes in tree, find paired RepeatInput.
                # For MVP, assume Single Repeat Zone or use name matching?
                # Let's search upstream recursively for a RepeatInput.
                
                def find_repeat_input(start_socket) -> Optional[Any]:
                    # DFS to find RepeatInput
                    stack = [start_socket]
                    visited = set()
                    while stack:
                        sock = stack.pop()
                        if sock in visited: continue
                        visited.add(sock)
                        
                        if sock.is_linked:
                            link = sock.links[0]
                            node = link.from_node
                            if node.bl_idname == 'ComputeNodeRepeatInput':
                                return node
                            # Add inputs of this node to stack
                            for inp in node.inputs:
                                stack.append(inp)
                    return None

                repeat_input_node = find_repeat_input(node.inputs[0])
                
                if not repeat_input_node:
                    logger.warning(f"Repeat Output {node.name} has no upstream Repeat Input connected.")
                    return builder.constant(0.0, DataType.FLOAT) # Error fix
                
                # 2. Extract Loop Parameters (Iterations, Initial Value)
                # Ensure we haven't processed RepeatInput yet? 
                # Actually, RepeatInput might be processed later if we recurse blindly.
                # We need to extract its inputs NOW.
                
                val_iters = get_socket_value(repeat_input_node.inputs[0]) # Iterations
                val_init = get_socket_value(repeat_input_node.inputs[1])  # Initial Value
                
                if val_iters is None: val_iters = builder.constant(1, DataType.INT)
                if val_init is None: val_init = builder.constant(0.0, DataType.FLOAT)
                
                # Casts
                val_iters = builder.cast(val_iters, DataType.INT)
                val_init = builder.cast(val_init, DataType.FLOAT)
                
                # 3. Emit Loop Shell
                # Define Accumulator (SSA) initialized to Initial Value
                # We need a Mutable Variable in GLSL? 
                # SSA form doesn't really support mutation easily without Phi nodes.
                # GLSL generator needs to handle this.
                # HACK: Use specific OpCode.LOOP_START that returns the 'current' value (as a var).
                
                # Op: LOOP_START(iters, init_val) -> returns [current_val_ssa]
                op_start = builder.add_op(OpCode.LOOP_START, [val_iters, val_init])
                val_curr = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op_start)
                op_start.add_output(val_curr)
                
                # 4. OVERRIDE Cache for RepeatInput
                # When the loop body asks for "RepeatInput.Current Value", we must return 'val_curr'.
                # We inject this into socket_value_map.
                # Note: RepeatInput has 2 outputs: Iteration, Current Value.
                # We should also support Iteration (loop index).
                
                # Iteration Output (Index 1 is 'Current Value', Index 0 is 'Iteration')
                # We need a value for Iteration too.
                # Let's say LOOP_START returns [current_val, loop_index].
                val_idx = builder._new_value(ValueKind.SSA, DataType.INT, origin=op_start)
                op_start.add_output(val_idx) # Add second output
                
                # Map them
                key_iter = get_socket_key(repeat_input_node.outputs[0])
                key_curr = get_socket_key(repeat_input_node.outputs[1])
                
                socket_value_map[key_iter] = val_idx
                socket_value_map[key_curr] = val_curr
                
                # 5. Extract Loop Body
                # Now we recurse on RepeatOutput's Input ("Next Value")
                # This will traverse the body, using the overridden values when hitting RepeatInput.
                val_next = get_socket_value(node.inputs[0]) 
                
                if val_next is None:
                    # Body broken?
                    val_next = val_curr # No-op loop
                    
                # Ensure type match (Float)
                val_next = builder.cast(val_next, DataType.FLOAT)
                
                # 6. Emit Loop End
                # Op: LOOP_END(next_val, accumulator) -> returns [final_result]
                # It consumes the body's result and updates the accumulator.
                op_end = builder.add_op(OpCode.LOOP_END, [val_next, val_curr])
                val_final = builder._new_value(ValueKind.SSA, DataType.FLOAT, origin=op_end)
                op_end.add_output(val_final)
                
                # Cache our own output
                out_key = get_socket_key(node.outputs[0])
                socket_value_map[out_key] = val_final
                
                # Clean up overrides? 
                # If dependencies are shared, this stays in cache. 
                # Since typical extraction is once per graph, this is fine.
                
                return val_final

            elif node.bl_idname == 'ComputeNodeRepeatInput':
                # If reached normally (e.g. Iterations check), default extraction.
                # But if we are inside loop extraction, it should be in cache!
                # If we are here, it means we reached it WITHOUT via RepeatOutput (impossible for loop body)
                # OR we are extracting the RepeatInput inputs themselves (handled above).
                
                # Check cache one last time
                key_curr = get_socket_key(node.outputs[1])
                if key_curr in socket_value_map:
                    return socket_value_map[key_curr]
                    
                # Fallback (Outside loop usage? Invalid)
                return builder.constant(0.0, DataType.FLOAT)



            return None
            
        finally:
            recursion_stack.remove(node_key)

    # Process all output nodes
    for output_node in output_nodes:
        # Start from Output
        target_socket = output_node.inputs[0]
        data_socket = output_node.inputs[1]
        
        # Target Image
        val_target = get_socket_value(target_socket)
        if val_target is None:
            logger.warning(f"Output node {output_node.name} has no target image")
            continue

        # Validation: Ensure target is Writable
        valid_target = False
        if val_target.kind == ValueKind.ARGUMENT and val_target.resource_index is not None:
            res = graph.resources[val_target.resource_index]
            
            # Checking if it's writable.
            if res.access == ResourceAccess.WRITE or res.access == ResourceAccess.READ_WRITE:
                valid_target = True
            elif res.access == ResourceAccess.READ:
                # Upgrade to READ_WRITE (or WRITE)
                res.access = ResourceAccess.READ_WRITE
                valid_target = True
                
        if not valid_target:
            logger.warning(f"Output Target for {output_node.name} must be a Writable Image (got {val_target})")
            continue
        
        # Data to Write
        val_data = get_socket_value(data_socket)
        if val_data is None:
            logger.warning(f"Output node {output_node.name} has no data to write")
            continue
            
        # Ensure VEC4 for RGBA32F
        if val_data.type == DataType.VEC3:
            val_data = builder.cast(val_data, DataType.VEC4)
        if val_data.type == DataType.IVEC2:
            val_data = builder.cast(val_data, DataType.VEC4)
        if val_data.type == DataType.FLOAT:
            val_data = builder.cast(val_data, DataType.VEC4)
        
        # Coord construction using Builders (Re-use per output if checking optimization, but builder deduplicates)
        val_gid = builder.builtin("gl_GlobalInvocationID", DataType.UVEC3)
        val_coord_uvec = builder.swizzle(val_gid, "xy")
        val_coord_ivec = builder.cast(val_coord_uvec, DataType.IVEC2)
        
        # Image Store
        builder.image_store(val_target, val_coord_ivec, val_data)
    
    return graph
