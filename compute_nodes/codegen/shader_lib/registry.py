"""
GLSL Function Registry for Tree-Shaking

Maps individual GLSL functions to their source code and dependencies.
Enables selective inclusion of only needed functions in shaders.
"""

from typing import Dict, Set, List

# =============================================================================
# INDIVIDUAL GLSL FUNCTIONS WITH DEPENDENCIES
# =============================================================================

GLSL_FUNCTIONS: Dict[str, Dict] = {
    # =========================================================================
    # HASH FUNCTIONS (Base Layer - No external deps)
    # =========================================================================
    'rot': {
        'code': '''
uint rot(uint x, uint k) {
    return (x << k) | (x >> (32u - k));
}''',
        'deps': []
    },
    'mix_hash': {
        'code': '''
void mix_hash(inout uint a, inout uint b, inout uint c) {
    a -= c; a ^= rot(c, 4u); c += b;
    b -= a; b ^= rot(a, 6u); a += c;
    c -= b; c ^= rot(b, 8u); b += a;
    a -= c; a ^= rot(c, 16u); c += b;
    b -= a; b ^= rot(a, 19u); a += c;
    c -= b; c ^= rot(b, 4u); b += a;
}''',
        'deps': ['rot']
    },
    'final_hash': {
        'code': '''
void final_hash(inout uint a, inout uint b, inout uint c) {
    c ^= b; c -= rot(b, 14u);
    a ^= c; a -= rot(c, 11u);
    b ^= a; b -= rot(a, 25u);
    c ^= b; c -= rot(b, 16u);
    a ^= c; a -= rot(c, 4u);
    b ^= a; b -= rot(a, 14u);
    c ^= b; c -= rot(b, 24u);
}''',
        'deps': ['rot']
    },
    'hash_int': {
        'code': '''
uint hash_int(uint k) {
    uint a, b, c;
    a = b = c = 0xdeadbeefu + (1u << 2u) + 13u;
    a += k;
    final_hash(a, b, c);
    return c;
}''',
        'deps': ['final_hash']
    },
    'hash_int2': {
        'code': '''
uint hash_int2(uint kx, uint ky) {
    uint a, b, c;
    a = b = c = 0xdeadbeefu + (2u << 2u) + 13u;
    b += ky;
    a += kx;
    final_hash(a, b, c);
    return c;
}''',
        'deps': ['final_hash']
    },
    'hash_int3': {
        'code': '''
uint hash_int3(uint kx, uint ky, uint kz) {
    uint a, b, c;
    a = b = c = 0xdeadbeefu + (3u << 2u) + 13u;
    c += kz;
    b += ky;
    a += kx;
    final_hash(a, b, c);
    return c;
}''',
        'deps': ['final_hash']
    },
    'hash_int4': {
        'code': '''
uint hash_int4(uint kx, uint ky, uint kz, uint kw) {
    uint a, b, c;
    a = b = c = 0xdeadbeefu + (4u << 2u) + 13u;
    a += kx;
    b += ky;
    c += kz;
    mix_hash(a, b, c);
    a += kw;
    final_hash(a, b, c);
    return c;
}''',
        'deps': ['mix_hash', 'final_hash']
    },
    'hash_uint_to_float': {
        'code': '''
float hash_uint_to_float(uint k) {
    return float(k) * (1.0f / float(0xFFFFFFFFu));
}''',
        'deps': []
    },
    'hash_float_to_float': {
        'code': '''
float hash_float_to_float(float k) {
    return hash_uint_to_float(hash_int(floatBitsToUint(k)));
}''',
        'deps': ['hash_uint_to_float', 'hash_int']
    },
    'hash_vec2_to_float': {
        'code': '''
float hash_vec2_to_float(float2 k) {
    return hash_uint_to_float(hash_int2(floatBitsToUint(k.x), floatBitsToUint(k.y)));
}''',
        'deps': ['hash_uint_to_float', 'hash_int2']
    },
    'hash_vec3_to_float': {
        'code': '''
float hash_vec3_to_float(float3 k) {
    return hash_uint_to_float(
        hash_int3(floatBitsToUint(k.x), floatBitsToUint(k.y), floatBitsToUint(k.z)));
}''',
        'deps': ['hash_uint_to_float', 'hash_int3']
    },
    'hash_vec4_to_float': {
        'code': '''
float hash_vec4_to_float(float4 k) {
    return hash_uint_to_float(hash_int4(
        floatBitsToUint(k.x), floatBitsToUint(k.y), floatBitsToUint(k.z), floatBitsToUint(k.w)));
}''',
        'deps': ['hash_uint_to_float', 'hash_int4']
    },
    'hash_float_to_vec3': {
        'code': '''
float3 hash_float_to_vec3(float k) {
    return float3(hash_float_to_float(k),
                  hash_vec2_to_float(float2(k, 1.0f)),
                  hash_vec2_to_float(float2(k, 2.0f)));
}''',
        'deps': ['hash_float_to_float', 'hash_vec2_to_float']
    },
    'hash_vec2_to_vec3': {
        'code': '''
float3 hash_vec2_to_vec3(float2 k) {
    return float3(hash_vec2_to_float(k),
                  hash_vec3_to_float(float3(k, 1.0f)),
                  hash_vec3_to_float(float3(k, 2.0f)));
}''',
        'deps': ['hash_vec2_to_float', 'hash_vec3_to_float']
    },
    'hash_vec3_to_vec3': {
        'code': '''
float3 hash_vec3_to_vec3(float3 k) {
    return float3(hash_vec3_to_float(k),
                  hash_vec4_to_float(float4(k, 1.0f)),
                  hash_vec4_to_float(float4(k, 2.0f)));
}''',
        'deps': ['hash_vec3_to_float', 'hash_vec4_to_float']
    },
    'hash_vec4_to_vec3': {
        'code': '''
float3 hash_vec4_to_vec3(float4 k) {
    return float3(
        hash_vec4_to_float(k.xyzw), 
        hash_vec4_to_float(k.zxyw), 
        hash_vec4_to_float(k.wzyx)
    );
}''',
        'deps': ['hash_vec4_to_float']
    },
    
    # PCG Hash functions
    'hash_pcg2d_i': {
        'code': '''
int2 hash_pcg2d_i(int2 v) {
    v = v * 1664525 + 1013904223;
    v.x += v.y * 1664525;
    v.y += v.x * 1664525;
    v = v ^ (v >> 16);
    v.x += v.y * 1664525;
    v.y += v.x * 1664525;
    return v;
}''',
        'deps': []
    },
    'hash_pcg3d_i': {
        'code': '''
int3 hash_pcg3d_i(int3 v) {
    v = v * 1664525 + 1013904223;
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    v = v ^ (v >> 16);
    v.x += v.y * v.z;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    return v;
}''',
        'deps': []
    },
    'hash_pcg4d_i': {
        'code': '''
int4 hash_pcg4d_i(int4 v) {
    v = v * 1664525 + 1013904223;
    v.x += v.y * v.w;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    v.w += v.y * v.z;
    v = v ^ (v >> 16);
    v.x += v.y * v.w;
    v.y += v.z * v.x;
    v.z += v.x * v.y;
    v.w += v.y * v.z;
    return v;
}''',
        'deps': []
    },
    'hash_int2_to_vec2': {
        'code': '''
float2 hash_int2_to_vec2(int2 k) {
    int2 h = hash_pcg2d_i(k);
    return float2(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}''',
        'deps': ['hash_pcg2d_i']
    },
    'hash_int3_to_vec3': {
        'code': '''
float3 hash_int3_to_vec3(int3 k) {
    int3 h = hash_pcg3d_i(k);
    return float3(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}''',
        'deps': ['hash_pcg3d_i']
    },
    'hash_int3_to_vec3_uvec': {
        'code': '''
float3 hash_int3_to_vec3(uvec3 k) { return hash_int3_to_vec3(int3(k)); }''',
        'deps': ['hash_int3_to_vec3']
    },
    'hash_int4_to_vec4': {
        'code': '''
float4 hash_int4_to_vec4(int4 k) {
    int4 h = hash_pcg4d_i(k);
    return float4(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}''',
        'deps': ['hash_pcg4d_i']
    },
    'hash_int2_to_vec3': {
        'code': '''
float3 hash_int2_to_vec3(int2 k) {
    return hash_int3_to_vec3(int3(k.x, k.y, 0));
}''',
        'deps': ['hash_int3_to_vec3']
    },
    'hash_int4_to_vec3': {
        'code': '''
float3 hash_int4_to_vec3(int4 k) {
    return hash_int4_to_vec4(k).xyz;
}''',
        'deps': ['hash_int4_to_vec4']
    },
    'hash_int_to_float': {
        'code': '''
float hash_int_to_float(int k) {
    return hash_float_to_float(float(k));
}''',
        'deps': ['hash_float_to_float']
    },
    'hash_int_to_vec3': {
        'code': '''
float3 hash_int_to_vec3(int k) {
    return hash_float_to_vec3(float(k));
}''',
        'deps': ['hash_float_to_vec3']
    },
    
    # =========================================================================
    # NOISE UTILITIES
    # =========================================================================
    'compatible_mod': {
        'code': '''
float compatible_mod(float a, float b) {
    return a - b * floor(a / b);
}
float2 compatible_mod(float2 a, float b) {
    return a - b * floor(a / b);
}
float3 compatible_mod(float3 a, float b) {
    return a - b * floor(a / b);
}
float4 compatible_mod(float4 a, float b) {
    return a - b * floor(a / b);
}''',
        'deps': []
    },
    'floorfrac_macro': {
        'code': '''
#define FLOORFRAC(x, x_int, x_fract) { float x_floor = floor(x); x_int = int(x_floor); x_fract = x - x_floor; }''',
        'deps': []
    },
    'bi_mix': {
        'code': '''
float bi_mix(float v0, float v1, float v2, float v3, float x, float y) {
    float x1 = 1.0f - x;
    return (1.0f - y) * (v0 * x1 + v1 * x) + y * (v2 * x1 + v3 * x);
}''',
        'deps': []
    },
    'tri_mix': {
        'code': '''
float tri_mix(float v0, float v1, float v2, float v3, float v4, float v5, float v6, float v7, float x, float y, float z) {
    float x1 = 1.0f - x;
    float y1 = 1.0f - y;
    float z1 = 1.0f - z;
    return z1 * (y1 * (v0 * x1 + v1 * x) + y * (v2 * x1 + v3 * x)) +
           z * (y1 * (v4 * x1 + v5 * x) + y * (v6 * x1 + v7 * x));
}''',
        'deps': []
    },
    'quad_mix': {
        'code': '''
float quad_mix(float v0, float v1, float v2, float v3, float v4, float v5, float v6, float v7,
               float v8, float v9, float v10, float v11, float v12, float v13, float v14, float v15,
               float x, float y, float z, float w) {
    return mix(tri_mix(v0, v1, v2, v3, v4, v5, v6, v7, x, y, z),
               tri_mix(v8, v9, v10, v11, v12, v13, v14, v15, x, y, z), w);
}''',
        'deps': ['tri_mix']
    },
    'fade': {
        'code': '''
float fade(float t) {
    return t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
}''',
        'deps': []
    },
    'negate_if': {
        'code': '''
float negate_if(float value, uint condition) {
    return (condition != 0u) ? -value : value;
}''',
        'deps': []
    },
    'noise_grad_1d': {
        'code': '''
float noise_grad(uint hash, float x) {
    uint h = hash & 15u;
    float g = 1u + (h & 7u);
    return negate_if(g, h & 8u) * x;
}''',
        'deps': ['negate_if']
    },
    'noise_grad_2d': {
        'code': '''
float noise_grad(uint hash, float x, float y) {
    uint h = hash & 7u;
    float u = h < 4u ? x : y;
    float v = 2.0f * (h < 4u ? y : x);
    return negate_if(u, h & 1u) + negate_if(v, h & 2u);
}''',
        'deps': ['negate_if']
    },
    'noise_grad_3d': {
        'code': '''
float noise_grad(uint hash, float x, float y, float z) {
    uint h = hash & 15u;
    float u = h < 8u ? x : y;
    float vt = ((h == 12u) || (h == 14u)) ? x : z;
    float v = h < 4u ? y : vt;
    return negate_if(u, h & 1u) + negate_if(v, h & 2u);
}''',
        'deps': ['negate_if']
    },
    'noise_grad_4d': {
        'code': '''
float noise_grad(uint hash, float x, float y, float z, float w) {
    uint h = hash & 31u;
    float u = h < 24u ? x : y;
    float v = h < 16u ? y : z;
    float s = h < 8u ? z : w;
    return negate_if(u, h & 1u) + negate_if(v, h & 2u) + negate_if(s, h & 4u);
}''',
        'deps': ['negate_if']
    },
    
    # =========================================================================
    # PERLIN NOISE
    # =========================================================================
    'noise_perlin_1d': {
        'code': '''
float noise_perlin(float x) {
    int X;
    float fx;
    FLOORFRAC(x, X, fx);
    float u = fade(fx);
    float r = mix(noise_grad(hash_int(X), fx), noise_grad(hash_int(X + 1), fx - 1.0f), u);
    return r;
}''',
        'deps': ['floorfrac_macro', 'fade', 'noise_grad_1d', 'hash_int']
    },
    'noise_perlin_2d': {
        'code': '''
float noise_perlin(float2 vec) {
    int X, Y;
    float fx, fy;
    FLOORFRAC(vec.x, X, fx);
    FLOORFRAC(vec.y, Y, fy);
    float u = fade(fx);
    float v = fade(fy);
    float r = bi_mix(noise_grad(hash_int2(X, Y), fx, fy),
                     noise_grad(hash_int2(X + 1, Y), fx - 1.0f, fy),
                     noise_grad(hash_int2(X, Y + 1), fx, fy - 1.0f),
                     noise_grad(hash_int2(X + 1, Y + 1), fx - 1.0f, fy - 1.0f), u, v);
    return r;
}''',
        'deps': ['floorfrac_macro', 'fade', 'bi_mix', 'noise_grad_2d', 'hash_int2']
    },
    'noise_perlin_3d': {
        'code': '''
float noise_perlin(float3 vec) {
    int X, Y, Z;
    float fx, fy, fz;
    FLOORFRAC(vec.x, X, fx);
    FLOORFRAC(vec.y, Y, fy);
    FLOORFRAC(vec.z, Z, fz);
    float u = fade(fx);
    float v = fade(fy);
    float w = fade(fz);
    float r = tri_mix(noise_grad(hash_int3(X, Y, Z), fx, fy, fz),
                      noise_grad(hash_int3(X + 1, Y, Z), fx - 1, fy, fz),
                      noise_grad(hash_int3(X, Y + 1, Z), fx, fy - 1, fz),
                      noise_grad(hash_int3(X + 1, Y + 1, Z), fx - 1, fy - 1, fz),
                      noise_grad(hash_int3(X, Y, Z + 1), fx, fy, fz - 1),
                      noise_grad(hash_int3(X + 1, Y, Z + 1), fx - 1, fy, fz - 1),
                      noise_grad(hash_int3(X, Y + 1, Z + 1), fx, fy - 1, fz - 1),
                      noise_grad(hash_int3(X + 1, Y + 1, Z + 1), fx - 1, fy - 1, fz - 1), u, v, w);
    return r;
}''',
        'deps': ['floorfrac_macro', 'fade', 'tri_mix', 'noise_grad_3d', 'hash_int3']
    },
    'noise_perlin_4d': {
        'code': '''
float noise_perlin(float4 vec) {
    int X, Y, Z, W;
    float fx, fy, fz, fw;
    FLOORFRAC(vec.x, X, fx);
    FLOORFRAC(vec.y, Y, fy);
    FLOORFRAC(vec.z, Z, fz);
    FLOORFRAC(vec.w, W, fw);
    float u = fade(fx);
    float v = fade(fy);
    float t = fade(fz);
    float s = fade(fw);
    float r = quad_mix(
        noise_grad(hash_int4(X, Y, Z, W), fx, fy, fz, fw),
        noise_grad(hash_int4(X + 1, Y, Z, W), fx - 1.0f, fy, fz, fw),
        noise_grad(hash_int4(X, Y + 1, Z, W), fx, fy - 1.0f, fz, fw),
        noise_grad(hash_int4(X + 1, Y + 1, Z, W), fx - 1.0f, fy - 1.0f, fz, fw),
        noise_grad(hash_int4(X, Y, Z + 1, W), fx, fy, fz - 1.0f, fw),
        noise_grad(hash_int4(X + 1, Y, Z + 1, W), fx - 1.0f, fy, fz - 1.0f, fw),
        noise_grad(hash_int4(X, Y + 1, Z + 1, W), fx, fy - 1.0f, fz - 1.0f, fw),
        noise_grad(hash_int4(X + 1, Y + 1, Z + 1, W), fx - 1.0f, fy - 1.0f, fz - 1.0f, fw),
        noise_grad(hash_int4(X, Y, Z, W + 1), fx, fy, fz, fw - 1.0f),
        noise_grad(hash_int4(X + 1, Y, Z, W + 1), fx - 1.0f, fy, fz, fw - 1.0f),
        noise_grad(hash_int4(X, Y + 1, Z, W + 1), fx, fy - 1.0f, fz, fw - 1.0f),
        noise_grad(hash_int4(X + 1, Y + 1, Z, W + 1), fx - 1.0f, fy - 1.0f, fz, fw - 1.0f),
        noise_grad(hash_int4(X, Y, Z + 1, W + 1), fx, fy, fz - 1.0f, fw - 1.0f),
        noise_grad(hash_int4(X + 1, Y, Z + 1, W + 1), fx - 1.0f, fy, fz - 1.0f, fw - 1.0f),
        noise_grad(hash_int4(X, Y + 1, Z + 1, W + 1), fx, fy - 1.0f, fz - 1.0f, fw - 1.0f),
        noise_grad(hash_int4(X + 1, Y + 1, Z + 1, W + 1), fx - 1.0f, fy - 1.0f, fz - 1.0f, fw - 1.0f),
        u, v, t, s);
    return r;
}''',
        'deps': ['floorfrac_macro', 'fade', 'quad_mix', 'noise_grad_4d', 'hash_int4']
    },
    'noise_scale': {
        'code': '''
float noise_scale1(float result) { return 0.2500f * result; }
float noise_scale2(float result) { return 0.6616f * result; }
float noise_scale3(float result) { return 0.9820f * result; }
float noise_scale4(float result) { return 0.8344f * result; }''',
        'deps': []
    },
    'snoise_1d': {
        'code': '''
float snoise(float p) {
    float precision_correction = 0.5f * float(abs(p) >= 1000000.0f);
    p = compatible_mod(p, 100000.0f) + precision_correction;
    return noise_scale1(noise_perlin(p));
}''',
        'deps': ['compatible_mod', 'noise_scale', 'noise_perlin_1d']
    },
    'snoise_2d': {
        'code': '''
float snoise(float2 p) {
    float2 precision_correction = 0.5f * float2(float(abs(p.x) >= 1000000.0f), float(abs(p.y) >= 1000000.0f));
    p = compatible_mod(p, 100000.0f) + precision_correction;
    return noise_scale2(noise_perlin(p));
}''',
        'deps': ['compatible_mod', 'noise_scale', 'noise_perlin_2d']
    },
    'snoise_3d': {
        'code': '''
float snoise(float3 p) {
    float3 precision_correction = 0.5f * float3(float(abs(p.x) >= 1000000.0f), float(abs(p.y) >= 1000000.0f), float(abs(p.z) >= 1000000.0f));
    p = compatible_mod(p, 100000.0f) + precision_correction;
    return noise_scale3(noise_perlin(p));
}''',
        'deps': ['compatible_mod', 'noise_scale', 'noise_perlin_3d']
    },
    'snoise_4d': {
        'code': '''
float snoise(float4 p) {
    float4 precision_correction = 0.5f * float4(float(abs(p.x) >= 1000000.0f), float(abs(p.y) >= 1000000.0f), float(abs(p.z) >= 1000000.0f), float(abs(p.w) >= 1000000.0f));
    p = compatible_mod(p, 100000.0f) + precision_correction;
    return noise_scale4(noise_perlin(p));
}''',
        'deps': ['compatible_mod', 'noise_scale', 'noise_perlin_4d']
    },
}


# =============================================================================
# DEPENDENCY RESOLUTION
# =============================================================================

def resolve_dependencies(func_names: Set[str]) -> List[str]:
    """
    Given a set of required function names, returns an ordered list
    including all transitive dependencies (dependencies first).
    """
    resolved: List[str] = []
    seen: Set[str] = set()
    
    def visit(name: str):
        if name in seen:
            return
        if name not in GLSL_FUNCTIONS:
            # Unknown function - skip (might be GLSL builtin)
            return
        seen.add(name)
        
        # Visit dependencies first
        for dep in GLSL_FUNCTIONS[name]['deps']:
            visit(dep)
        
        resolved.append(name)
    
    for name in func_names:
        visit(name)
    
    return resolved


def get_functions_code(func_names: Set[str]) -> str:
    """
    Given a set of required function names, returns GLSL code
    with all functions and their dependencies in correct order.
    """
    ordered = resolve_dependencies(func_names)
    
    code_parts = []
    for name in ordered:
        if name in GLSL_FUNCTIONS:
            code_parts.append(GLSL_FUNCTIONS[name]['code'])
    
    return '\n'.join(code_parts)


# =============================================================================
# OPCODE TO GLSL REQUIREMENTS MAPPING
# =============================================================================

# Maps high-level operation types to their required GLSL functions
OPCODE_GLSL_REQUIREMENTS = {
    # Noise textures
    'noise_1d': {'snoise_1d', 'hash_float_to_vec3'},
    'noise_2d': {'snoise_2d', 'hash_vec2_to_vec3'},
    'noise_3d': {'snoise_3d', 'hash_vec3_to_vec3'},
    'noise_4d': {'snoise_4d', 'hash_vec4_to_vec3'},
    
    # White noise
    'white_noise_1d': {'hash_float_to_float', 'hash_float_to_vec3'},
    'white_noise_2d': {'hash_vec2_to_float', 'hash_vec2_to_vec3'},
    'white_noise_3d': {'hash_vec3_to_float', 'hash_vec3_to_vec3'},
    'white_noise_4d': {'hash_vec4_to_float', 'hash_vec4_to_vec3'},
    
    # Voronoi uses separate includes (too complex to split)
    # Color conversion (too complex to split)
    # Map range (too complex to split)
}


def get_requirements_for_opcode(opcode_key: str) -> Set[str]:
    """Get required GLSL functions for an opcode key."""
    return OPCODE_GLSL_REQUIREMENTS.get(opcode_key, set())


# =============================================================================
# LIBRARY BUNDLES (for complex, macro-heavy libraries)
# =============================================================================
# These are included as complete units when needed

from .hash import HASH_GLSL
from .noise.perlin import NOISE_GLSL
from .noise.fractal import FRACTAL_GLSL, TEX_NOISE_GLSL
from .white_noise import WHITE_NOISE_GLSL
from .voronoi import VORONOI_GLSL
from .color import COLOR_GLSL
from .map_range import MAP_RANGE_GLSL

# Bundle definitions - each bundle has a key and full source
GLSL_BUNDLES = {
    'hash': HASH_GLSL,          # Base hash library (used by most)
    'noise_perlin': NOISE_GLSL, # Perlin noise
    'fractal': FRACTAL_GLSL,
    'tex_noise': TEX_NOISE_GLSL,
    'white_noise': WHITE_NOISE_GLSL,
    'voronoi': VORONOI_GLSL,
    'color': COLOR_GLSL,
    'map_range': MAP_RANGE_GLSL,
}

# Which bundles are needed for which OpCode types
OPCODE_BUNDLE_REQUIREMENTS = {
    # Noise needs hash + perlin + fractal + tex_noise
    'noise': {'hash', 'noise_perlin', 'fractal', 'tex_noise'},
    
    # White Noise needs hash
    'white_noise': {'hash', 'white_noise'},
    
    # Voronoi needs hash + voronoi
    'voronoi': {'hash', 'voronoi'},
    
    # Color conversion
    'separate_color': {'color'},
    'combine_color': {'color'},
    
    # Map range
    'map_range': {'map_range'},
}

# Hash functions from registry needed by bundles (only for tree-shaking ops)
BUNDLE_HASH_REQUIREMENTS = {
    'hash': set(),  # Full bundle, no tree-shaking
    'noise_perlin': set(),  # Uses hash bundle
    'fractal': set(),  # Uses hash bundle
    'tex_noise': set(),  # Uses hash bundle
    'white_noise': set(),  # Uses hash bundle
    'voronoi': set(),  # Uses hash bundle
    'color': set(),
    'map_range': set(),
}


def get_bundles_code(bundle_names: Set[str]) -> str:
    """Get combined code for requested bundles in correct order."""
    # Order matters: hash first, then perlin, then fractal, etc.
    order = ['hash', 'noise_perlin', 'fractal', 'tex_noise', 'white_noise', 'voronoi', 'color', 'map_range']
    code_parts = []
    for name in order:
        if name in bundle_names and name in GLSL_BUNDLES:
            code_parts.append(GLSL_BUNDLES[name])
    return '\n'.join(code_parts)


def get_bundle_requirements(opcode_key: str) -> Set[str]:
    """Get required bundle names for an opcode key."""
    return OPCODE_BUNDLE_REQUIREMENTS.get(opcode_key, set())


def get_hash_requirements_for_bundles(bundle_names: Set[str]) -> Set[str]:
    """Get hash function requirements for given bundles."""
    funcs = set()
    for bundle in bundle_names:
        funcs.update(BUNDLE_HASH_REQUIREMENTS.get(bundle, set()))
    return funcs


# =============================================================================
# MAIN API: Generate selective header
# =============================================================================

def generate_selective_header(required_funcs: Set[str], required_bundles: Set[str]) -> str:
    """
    Generate a minimal GLSL header with only needed functions and bundles.
    
    Args:
        required_funcs: Set of individual function names (for tree-shaking)
        required_bundles: Set of bundle names ('noise', 'voronoi', etc.)
    
    Returns:
        GLSL code string with minimal required functions
    """
    # 1. Get hash requirements from bundles
    bundle_hash_reqs = get_hash_requirements_for_bundles(required_bundles)
    all_funcs = required_funcs | bundle_hash_reqs
    
    # 2. Resolve individual function dependencies
    func_code = get_functions_code(all_funcs) if all_funcs else ""
    
    # 3. Get bundle code
    bundle_code = get_bundles_code(required_bundles) if required_bundles else ""
    
    return func_code + "\n" + bundle_code
