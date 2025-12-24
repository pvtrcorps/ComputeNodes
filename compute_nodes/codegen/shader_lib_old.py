
# GLSL Source Code from Blender (Ported)
# Source: https://github.com/blender/blender/tree/main/source/blender/gpu/shaders

# -----------------------------------------------------------------------------
# gpu_shader_common_hash.glsl
# -----------------------------------------------------------------------------
HASH_GLSL = """
uint rot(uint x, uint k) {
    return (x << k) | (x >> (32u - k));
}

void mix(inout uint a, inout uint b, inout uint c) {
    a -= c; a ^= rot(c, 4u); c += b;
    b -= a; b ^= rot(a, 6u); a += c;
    c -= b; c ^= rot(b, 8u); b += a;
    a -= c; a ^= rot(c, 16u); c += b;
    b -= a; b ^= rot(a, 19u); a += c;
    c -= b; c ^= rot(b, 4u); b += a;
}

void final(inout uint a, inout uint b, inout uint c) {
    c ^= b; c -= rot(b, 14u);
    a ^= c; a -= rot(c, 11u);
    b ^= a; b -= rot(a, 25u);
    c ^= b; c -= rot(b, 16u);
    a ^= c; a -= rot(c, 4u);
    b ^= a; b -= rot(a, 14u);
    c ^= b; c -= rot(b, 24u);
}

uint hash_int(uint k)
{
  uint a, b, c;
  a = b = c = 0xdeadbeefu + (1u << 2u) + 13u;
  a += k;
  final(a, b, c);
  return c;
}

uint hash_int2(uint kx, uint ky)
{
  uint a, b, c;
  a = b = c = 0xdeadbeefu + (2u << 2u) + 13u;
  b += ky;
  a += kx;
  final(a, b, c);
  return c;
}

uint hash_int3(uint kx, uint ky, uint kz)
{
  uint a, b, c;
  a = b = c = 0xdeadbeefu + (3u << 2u) + 13u;
  c += kz;
  b += ky;
  a += kx;
  final(a, b, c);
  return c;
}

uint hash_int4(uint kx, uint ky, uint kz, uint kw)
{
  uint a, b, c;
  a = b = c = 0xdeadbeefu + (4u << 2u) + 13u;
  a += kx;
  b += ky;
  c += kz;
  mix(a, b, c);
  a += kw;
  final(a, b, c);
  return c;
}

float hash_uint_to_float(uint k)
{
  return float(k) * (1.0f / float(0xFFFFFFFFu));
}

float hash_float_to_float(float k)
{
  return hash_uint_to_float(hash_int(floatBitsToUint(k)));
}

float hash_vec2_to_float(float2 k)
{
  return hash_uint_to_float(hash_int2(floatBitsToUint(k.x), floatBitsToUint(k.y)));
}

float hash_vec3_to_float(float3 k)
{
  return hash_uint_to_float(
      hash_int3(floatBitsToUint(k.x), floatBitsToUint(k.y), floatBitsToUint(k.z)));
}

float hash_vec4_to_float(float4 k)
{
  return hash_uint_to_float(hash_int4(
      floatBitsToUint(k.x), floatBitsToUint(k.y), floatBitsToUint(k.z), floatBitsToUint(k.w)));
}

float3 hash_float_to_vec3(float k)
{
  return float3(hash_float_to_float(k),
                hash_vec2_to_float(float2(k, 1.0f)),
                hash_vec2_to_float(float2(k, 2.0f)));
}

float3 hash_vec2_to_vec3(float2 k)
{
  return float3(hash_vec2_to_float(k),
                hash_vec3_to_float(float3(k, 1.0f)),
                hash_vec3_to_float(float3(k, 2.0f)));
}

float3 hash_vec3_to_vec3(float3 k)
{
  return float3(hash_vec3_to_float(k),
                hash_vec4_to_float(float4(k, 1.0f)),
                hash_vec4_to_float(float4(k, 2.0f)));
}

// Note: hash_vec4_to_vec3 requires swizzling which needs careful valid GLSL.
// Blender uses: hash_vec4_to_float(k.xyzw), hash_vec4_to_float(k.zxwy), ...
float3 hash_vec4_to_vec3(float4 k) 
{
  return float3(
      hash_vec4_to_float(k.xyzw), 
      hash_vec4_to_float(k.zxyw), 
      hash_vec4_to_float(k.wzyx)
  );
}

// Helper for Voronoi (Standard Blender implementation usually relies on hashing the integer coordinates)
// We implement it using the existing hash_vec3_to_float variant or similar logic.
// However, looking at Blender source, hash_int3_to_vec3 might be doing distinct hashes.
// Implementation:
/* PCG 2D, 3D and 4D hash functions */
int2 hash_pcg2d_i(int2 v) {
  v = v * 1664525 + 1013904223;
  v.x += v.y * 1664525;
  v.y += v.x * 1664525;
  v = v ^ (v >> 16);
  v.x += v.y * 1664525;
  v.y += v.x * 1664525;
  return v;
}

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
}

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
}

/* Hashing a number of integers into floats in [0..1] range. */

float2 hash_int2_to_vec2(int2 k) {
  int2 h = hash_pcg2d_i(k);
  return float2(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}

float3 hash_int3_to_vec3(int3 k) {
  int3 h = hash_pcg3d_i(k);
  return float3(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}

float4 hash_int4_to_vec4(int4 k) {
  int4 h = hash_pcg4d_i(k);
  return float4(h & 0x7fffffff) * (1.0 / float(0x7fffffff));
}

// Aliases for compatibility (uvec only, as ivec usually equals int)
float3 hash_int3_to_vec3(uvec3 k) { return hash_int3_to_vec3(int3(k)); }

float3 hash_int2_to_vec3(int2 k) {
  return hash_int3_to_vec3(int3(k.x, k.y, 0));
}

float3 hash_int4_to_vec3(int4 k) {
  return hash_int4_to_vec4(k).xyz;
}

// Helper definitions for 1D Voronoi (Updated to match Blender 1D logic which uses floats)
// Blender uses: hash_float_to_float(cellPosition + cellOffset)
// My code uses int cellPosition. Casting to float mimics Blender's behavior on integral floats.
float hash_int_to_float(int k) {
    return hash_float_to_float(float(k));
}


float3 hash_int_to_vec3(int k) {
    return hash_float_to_vec3(float(k));
}

"""

# -----------------------------------------------------------------------------
# gpu_shader_material_noise.glsl
# -----------------------------------------------------------------------------
NOISE_GLSL = """
/* Safe modulo that works for negative numbers */
float compatible_mod(float a, float b)
{
    return a - b * floor(a / b);
}

float2 compatible_mod(float2 a, float b)
{
    return a - b * floor(a / b);
}

float3 compatible_mod(float3 a, float b)
{
    return a - b * floor(a / b);
}

float4 compatible_mod(float4 a, float b)
{
    return a - b * floor(a / b);
}

#define FLOORFRAC(x, x_int, x_fract) { float x_floor = floor(x); x_int = int(x_floor); x_fract = x - x_floor; }

float bi_mix(float v0, float v1, float v2, float v3, float x, float y)
{
  float x1 = 1.0f - x;
  return (1.0f - y) * (v0 * x1 + v1 * x) + y * (v2 * x1 + v3 * x);
}

float tri_mix(float v0,
              float v1,
              float v2,
              float v3,
              float v4,
              float v5,
              float v6,
              float v7,
              float x,
              float y,
              float z)
{
  float x1 = 1.0f - x;
  float y1 = 1.0f - y;
  float z1 = 1.0f - z;
  return z1 * (y1 * (v0 * x1 + v1 * x) + y * (v2 * x1 + v3 * x)) +
         z * (y1 * (v4 * x1 + v5 * x) + y * (v6 * x1 + v7 * x));
}

float quad_mix(float v0,
               float v1,
               float v2,
               float v3,
               float v4,
               float v5,
               float v6,
               float v7,
               float v8,
               float v9,
               float v10,
               float v11,
               float v12,
               float v13,
               float v14,
               float v15,
               float x,
               float y,
               float z,
               float w)
{
  return mix(tri_mix(v0, v1, v2, v3, v4, v5, v6, v7, x, y, z),
             tri_mix(v8, v9, v10, v11, v12, v13, v14, v15, x, y, z),
             w);
}

float fade(float t)
{
  return t * t * t * (t * (t * 6.0f - 15.0f) + 10.0f);
}

float negate_if(float value, uint condition)
{
  return (condition != 0u) ? -value : value;
}

float noise_grad(uint hash, float x)
{
  uint h = hash & 15u;
  float g = 1u + (h & 7u);
  return negate_if(g, h & 8u) * x;
}

float noise_grad(uint hash, float x, float y)
{
  uint h = hash & 7u;
  float u = h < 4u ? x : y;
  float v = 2.0f * (h < 4u ? y : x);
  return negate_if(u, h & 1u) + negate_if(v, h & 2u);
}

float noise_grad(uint hash, float x, float y, float z)
{
  uint h = hash & 15u;
  float u = h < 8u ? x : y;
  float vt = ((h == 12u) || (h == 14u)) ? x : z;
  float v = h < 4u ? y : vt;
  return negate_if(u, h & 1u) + negate_if(v, h & 2u);
}

float noise_grad(uint hash, float x, float y, float z, float w)
{
  uint h = hash & 31u;
  float u = h < 24u ? x : y;
  float v = h < 16u ? y : z;
  float s = h < 8u ? z : w;
  return negate_if(u, h & 1u) + negate_if(v, h & 2u) + negate_if(s, h & 4u);
}

float noise_perlin(float x)
{
  int X;
  float fx;

  FLOORFRAC(x, X, fx);

  float u = fade(fx);

  float r = mix(noise_grad(hash_int(X), fx), noise_grad(hash_int(X + 1), fx - 1.0f), u);

  return r;
}

float noise_perlin(float2 vec)
{
  int X, Y;
  float fx, fy;

  FLOORFRAC(vec.x, X, fx);
  FLOORFRAC(vec.y, Y, fy);

  float u = fade(fx);
  float v = fade(fy);

  float r = bi_mix(noise_grad(hash_int2(X, Y), fx, fy),
                   noise_grad(hash_int2(X + 1, Y), fx - 1.0f, fy),
                   noise_grad(hash_int2(X, Y + 1), fx, fy - 1.0f),
                   noise_grad(hash_int2(X + 1, Y + 1), fx - 1.0f, fy - 1.0f),
                   u,
                   v);

  return r;
}

float noise_perlin(float3 vec)
{
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
                    noise_grad(hash_int3(X + 1, Y + 1, Z + 1), fx - 1, fy - 1, fz - 1),
                    u,
                    v,
                    w);

  return r;
}

float noise_perlin(float4 vec)
{
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
      noise_grad(
          hash_int4(X + 1, Y + 1, Z + 1, W + 1), fx - 1.0f, fy - 1.0f, fz - 1.0f, fw - 1.0f),
      u,
      v,
      t,
      s);

  return r;
}

float noise_scale1(float result) { return 0.2500f * result; }
float noise_scale2(float result) { return 0.6616f * result; }
float noise_scale3(float result) { return 0.9820f * result; }
float noise_scale4(float result) { return 0.8344f * result; }

float snoise(float p)
{
  float precision_correction = 0.5f * float(abs(p) >= 1000000.0f);
  p = compatible_mod(p, 100000.0f) + precision_correction;
  return noise_scale1(noise_perlin(p));
}

float snoise(float2 p)
{
  float2 precision_correction = 0.5f * float2(float(abs(p.x) >= 1000000.0f),
                                              float(abs(p.y) >= 1000000.0f));
  p = compatible_mod(p, 100000.0f) + precision_correction;
  return noise_scale2(noise_perlin(p));
}

float snoise(float3 p)
{
  float3 precision_correction = 0.5f * float3(float(abs(p.x) >= 1000000.0f),
                                              float(abs(p.y) >= 1000000.0f),
                                              float(abs(p.z) >= 1000000.0f));
  p = compatible_mod(p, 100000.0f) + precision_correction;
  return noise_scale3(noise_perlin(p));
}

float snoise(float4 p)
{
  float4 precision_correction = 0.5f * float4(float(abs(p.x) >= 1000000.0f),
                                              float(abs(p.y) >= 1000000.0f),
                                              float(abs(p.z) >= 1000000.0f),
                                              float(abs(p.w) >= 1000000.0f));
  p = compatible_mod(p, 100000.0f) + precision_correction;
  return noise_scale4(noise_perlin(p));
}
"""

# -----------------------------------------------------------------------------
# gpu_shader_material_white_noise.glsl
# -----------------------------------------------------------------------------
WHITE_NOISE_GLSL = """
void node_white_noise_1d(float w, out float value, out vec4 color)
{
  value = hash_float_to_float(w);
  color = vec4(hash_float_to_vec3(w), 1.0f);
}

void node_white_noise_2d(vec3 vector, float w, out float value, out vec4 color)
{
  value = hash_vec2_to_float(vector.xy);
  color = vec4(hash_vec2_to_vec3(vector.xy), 1.0f);
}

void node_white_noise_3d(vec3 vector, float w, out float value, out vec4 color)
{
  value = hash_vec3_to_float(vector);
  color = vec4(hash_vec3_to_vec3(vector), 1.0f);
}

void node_white_noise_4d(vec3 vector, float w, out float value, out vec4 color)
{
  value = hash_vec4_to_float(vec4(vector, w));
  // Requires hash_vec4_to_vec3 implementation which we added
  color = vec4(hash_vec4_to_vec3(vec4(vector, w)), 1.0f);
}
"""

# -----------------------------------------------------------------------------
# gpu_shader_material_fractal_noise.glsl
# -----------------------------------------------------------------------------
FRACTAL_GLSL = """
# define NOISE_FBM(T) \\
float noise_fbm(T co, \\
                  float detail, \\
                  float roughness, \\
                  float lacunarity, \\
                  float offset, \\
                  float gain, \\
                  bool normalize) \\
  { \\
    T p = co; \\
    float fscale = 1.0f; \\
    float amp = 1.0f; \\
    float maxamp = 0.0f; \\
    float sum = 0.0f; \\
\\
    for (int i = 0; i <= int(detail); i++) { \\
      float t = snoise(fscale * p); \\
      sum += t * amp; \\
      maxamp += amp; \\
      amp *= roughness; \\
      fscale *= lacunarity; \\
    } \\
    float rmd = detail - floor(detail); \\
    if (rmd != 0.0f) { \\
      float t = snoise(fscale * p); \\
      float sum2 = sum + t * amp; \\
      return normalize ? \\
                 mix(0.5f * sum / maxamp + 0.5f, 0.5f * sum2 / (maxamp + amp) + 0.5f, rmd) : \\
                 mix(sum, sum2, rmd); \\
    } \\
    else { \\
      return normalize ? 0.5f * sum / maxamp + 0.5f : sum; \\
    } \\
  }

NOISE_FBM(float)
NOISE_FBM(float2)
NOISE_FBM(float3)
NOISE_FBM(float4)
"""

# -----------------------------------------------------------------------------
# gpu_shader_material_tex_noise.glsl
# -----------------------------------------------------------------------------
TEX_NOISE_GLSL = """
float random_float_offset(float seed)
{
  return 100.0f + hash_float_to_float(seed) * 100.0f;
}

float2 random_vec2_offset(float seed)
{
  return float2(100.0f + hash_vec2_to_float(float2(seed, 0.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 1.0f)) * 100.0f);
}

float3 random_vec3_offset(float seed)
{
  return float3(100.0f + hash_vec2_to_float(float2(seed, 0.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 1.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 2.0f)) * 100.0f);
}

float4 random_vec4_offset(float seed)
{
  return float4(100.0f + hash_vec2_to_float(float2(seed, 0.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 1.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 2.0f)) * 100.0f,
                100.0f + hash_vec2_to_float(float2(seed, 3.0f)) * 100.0f);
}

# define NOISE_FRACTAL_STD_1D(NOISE_TYPE) \\
  value = NOISE_TYPE(p, detail, roughness, lacunarity, offset, 0.0f, normalize != 0.0f); \\
  color = float4(value, \\
                 NOISE_TYPE(p + random_float_offset(1.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 NOISE_TYPE(p + random_float_offset(2.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 1.0f);

# define NOISE_FRACTAL_STD_2D(NOISE_TYPE) \\
  value = NOISE_TYPE(p, detail, roughness, lacunarity, offset, 0.0f, normalize != 0.0f); \\
  color = float4(value, \\
                 NOISE_TYPE(p + random_vec2_offset(2.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 NOISE_TYPE(p + random_vec2_offset(3.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 1.0f);

# define NOISE_FRACTAL_STD_3D(NOISE_TYPE) \\
  value = NOISE_TYPE(p, detail, roughness, lacunarity, offset, 0.0f, normalize != 0.0f); \\
  color = float4(value, \\
                 NOISE_TYPE(p + random_vec3_offset(3.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 NOISE_TYPE(p + random_vec3_offset(4.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 1.0f);

# define NOISE_FRACTAL_STD_4D(NOISE_TYPE) \\
  value = NOISE_TYPE(p, detail, roughness, lacunarity, offset, 0.0f, normalize != 0.0f); \\
  color = float4(value, \\
                 NOISE_TYPE(p + random_vec4_offset(4.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 NOISE_TYPE(p + random_vec4_offset(5.0f), \\
                            detail, \\
                            roughness, \\
                            lacunarity, \\
                            offset, \\
                            0.0f, \\
                            normalize != 0.0f), \\
                 1.0f);

void node_noise_tex_fbm_1d(float3 co,
                           float w,
                           float scale,
                           float detail,
                           float roughness,
                           float lacunarity,
                           float offset,
                           float normalize,
                           out float value,
                           out float4 color)
{
  detail = clamp(detail, 0.0f, 15.0f);
  roughness = max(roughness, 0.0f);

  float p = w * scale;

  NOISE_FRACTAL_STD_1D(noise_fbm)
}

void node_noise_tex_fbm_2d(float3 co,
                           float w,
                           float scale,
                           float detail,
                           float roughness,
                           float lacunarity,
                           float offset,
                           float normalize,
                           out float value,
                           out float4 color)
{
  detail = clamp(detail, 0.0f, 15.0f);
  roughness = max(roughness, 0.0f);

  float2 p = co.xy * scale;

  NOISE_FRACTAL_STD_2D(noise_fbm)
}

void node_noise_tex_fbm_3d(float3 co,
                           float w,
                           float scale,
                           float detail,
                           float roughness,
                           float lacunarity,
                           float offset,
                           float normalize,
                           out float value,
                           out float4 color)
{
  detail = clamp(detail, 0.0f, 15.0f);
  roughness = max(roughness, 0.0f);

  float3 p = co * scale;

  NOISE_FRACTAL_STD_3D(noise_fbm)
}

void node_noise_tex_fbm_4d(float3 co,
                           float w,
                           float scale,
                           float detail,
                           float roughness,
                           float lacunarity,
                           float offset,
                           float normalize,
                           out float value,
                           out float4 color)
{
  detail = clamp(detail, 0.0f, 15.0f);
  roughness = max(roughness, 0.0f);

  float4 p = float4(co, w) * scale;

  NOISE_FRACTAL_STD_4D(noise_fbm)
}
"""

# -----------------------------------------------------------------------------
# Voronoi Dependencies
# -----------------------------------------------------------------------------
SAFE_MATH_GLSL = """
float safe_divide(float a, float b) { return (b != 0.0) ? a / b : 0.0; }
float2 safe_divide(float2 a, float2 b) { return float2((b.x != 0.0) ? a.x / b.x : 0.0, (b.y != 0.0) ? a.y / b.y : 0.0); }
float3 safe_divide(float3 a, float3 b) { return float3((b.x != 0.0) ? a.x / b.x : 0.0, (b.y != 0.0) ? a.y / b.y : 0.0, (b.z != 0.0) ? a.z / b.z : 0.0); }
float4 safe_divide(float4 a, float4 b) { return float4((b.x != 0.0) ? a.x / b.x : 0.0, (b.y != 0.0) ? a.y / b.y : 0.0, (b.z != 0.0) ? a.z / b.z : 0.0, (b.w != 0.0) ? a.w / b.w : 0.0); }
float3 safe_divide(float3 a, float b) { return (b != 0.0) ? a / b : float3(0.0); }
float4 safe_divide(float4 a, float b) { return (b != 0.0) ? a / b : float4(0.0); }
"""

VORONOI_DEFINES_GLSL = """
#define SHD_VORONOI_EUCLIDEAN 0
#define SHD_VORONOI_MANHATTAN 1
#define SHD_VORONOI_CHEBYCHEV 2
#define SHD_VORONOI_MINKOWSKI 3
#define SHD_VORONOI_F1 0
#define SHD_VORONOI_F2 1
#define SHD_VORONOI_SMOOTH_F1 2
#define SHD_VORONOI_DISTANCE_TO_EDGE 3
#define SHD_VORONOI_N_SPHERE_RADIUS 4
#define FLT_MAX 3.402823466e+38
"""

VORONOI_CORE_GLSL = """
struct VoronoiParams {
  float scale;
  float detail;
  float roughness;
  float lacunarity;
  float smoothness;
  float exponent;
  float randomness;
  float max_distance;
  bool normalize;
  int feature;
  int metric;
};
struct VoronoiOutput {
  float Distance;
  float3 Color;
  float4 Position;
};
float voronoi_distance(float a, float b, VoronoiParams params) { return abs(a - b); }
float voronoi_distance(float2 a, float2 b, VoronoiParams params) {
  if (params.metric == SHD_VORONOI_EUCLIDEAN) return distance(a, b);
  else if (params.metric == SHD_VORONOI_MANHATTAN) return abs(a.x - b.x) + abs(a.y - b.y);
  else if (params.metric == SHD_VORONOI_CHEBYCHEV) return max(abs(a.x - b.x), abs(a.y - b.y));
  else if (params.metric == SHD_VORONOI_MINKOWSKI) return pow(pow(abs(a.x - b.x), params.exponent) + pow(abs(a.y - b.y), params.exponent), 1.0f / params.exponent);
  else return 0.0f;
}
float voronoi_distance(float3 a, float3 b, VoronoiParams params) {
  if (params.metric == SHD_VORONOI_EUCLIDEAN) return distance(a, b);
  else if (params.metric == SHD_VORONOI_MANHATTAN) return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.z - b.z);
  else if (params.metric == SHD_VORONOI_CHEBYCHEV) return max(abs(a.x - b.x), max(abs(a.y - b.y), abs(a.z - b.z)));
  else if (params.metric == SHD_VORONOI_MINKOWSKI) return pow(pow(abs(a.x - b.x), params.exponent) + pow(abs(a.y - b.y), params.exponent) + pow(abs(a.z - b.z), params.exponent), 1.0f / params.exponent);
  else return 0.0f;
}
float voronoi_distance(float4 a, float4 b, VoronoiParams params) {
  if (params.metric == SHD_VORONOI_EUCLIDEAN) return distance(a, b);
  else if (params.metric == SHD_VORONOI_MANHATTAN) return abs(a.x - b.x) + abs(a.y - b.y) + abs(a.z - b.z) + abs(a.w - b.w);
  else if (params.metric == SHD_VORONOI_CHEBYCHEV) return max(abs(a.x - b.x), max(abs(a.y - b.y), max(abs(a.z - b.z), abs(a.w - b.w))));
  else if (params.metric == SHD_VORONOI_MINKOWSKI) return pow(pow(abs(a.x - b.x), params.exponent) + pow(abs(a.y - b.y), params.exponent) + pow(abs(a.z - b.z), params.exponent) + pow(abs(a.w - b.w), params.exponent), 1.0f / params.exponent);
  else return 0.0f;
}

float4 voronoi_position(float coord) { return float4(0.0f, 0.0f, 0.0f, coord); }
float4 voronoi_position(float2 coord) { return float4(coord.x, coord.y, 0.0f, 0.0f); }
float4 voronoi_position(float3 coord) { return float4(coord.x, coord.y, coord.z, 0.0f); }
float4 voronoi_position(float4 coord) { return coord; }

// ---- 1D Voronoi ----
VoronoiOutput voronoi_f1(VoronoiParams params, float coord) {
  float cellPosition_f = floor(coord); float localPosition = coord - cellPosition_f; int cellPosition = int(cellPosition_f);
  float minDistance = FLT_MAX; int targetOffset = 0; float targetPosition = 0.0f;
  for (int i = -1; i <= 1; i++) {
        int cellOffset = i; float p = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < minDistance) { targetOffset = cellOffset; minDistance = d; targetPosition = p; }
  }
  VoronoiOutput octave; octave.Distance = minDistance; octave.Color = hash_int_to_vec3(cellPosition + targetOffset); octave.Position = voronoi_position(targetPosition + cellPosition_f); return octave;
}
VoronoiOutput voronoi_smooth_f1(VoronoiParams params, float coord) {
  float cellPosition_f = floor(coord); float localPosition = coord - cellPosition_f; int cellPosition = int(cellPosition_f);
  float smoothDistance = 0.0f; float3 smoothColor = float3(0.0f); float4 smoothPosition = float4(0.0f); float h = -1.0f;
  for (int i = -2; i <= 2; i++) {
        int cellOffset = i; float p = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        h = h == -1.0f ? 1.0f : smoothstep(0.0f, 1.0f, 0.5f + 0.5f * (smoothDistance - d) / params.smoothness);
        float correctionFactor = params.smoothness * h * (1.0f - h);
        smoothDistance = mix(smoothDistance, d, h) - correctionFactor; correctionFactor /= 1.0f + 3.0f * params.smoothness;
        smoothColor = mix(smoothColor, hash_int_to_vec3(cellPosition + cellOffset), h) - correctionFactor;
        smoothPosition = mix(smoothPosition, float4(0,0,0,p), h) - correctionFactor; 
  }
  VoronoiOutput octave; octave.Distance = smoothDistance; octave.Color = smoothColor; octave.Position = voronoi_position(cellPosition_f) + smoothPosition; return octave;
}
VoronoiOutput voronoi_f2(VoronoiParams params, float coord) {
  float cellPosition_f = floor(coord); float localPosition = coord - cellPosition_f; int cellPosition = int(cellPosition_f);
  float d1 = FLT_MAX; float d2 = FLT_MAX; int o1 = 0; float p1 = 0.0f; int o2 = 0; float p2 = 0.0f;
  for (int i = -1; i <= 1; i++) {
        int cellOffset = i; float p = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < d1) { d2 = d1; d1 = d; o2 = o1; o1 = cellOffset; p2 = p1; p1 = p; } else if (d < d2) { d2 = d; o2 = cellOffset; p2 = p; }
  }
  VoronoiOutput octave; octave.Distance = d2; octave.Color = hash_int_to_vec3(cellPosition + o2); octave.Position = voronoi_position(p2 + cellPosition_f); return octave;
}
float voronoi_distance_to_edge(VoronoiParams params, float coord) {
  float cellPosition_f = floor(coord); float localPosition = coord - cellPosition_f; int cellPosition = int(cellPosition_f);
  float closest = 0.0f; float minD = FLT_MAX;
  for (int i = -1; i <= 1; i++) {
          int cellOffset = i; float v = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness - localPosition;
          float d = v * v; if (d < minD) { minD = d; closest = v; }
  }
  minD = FLT_MAX;
  for (int i = -1; i <= 1; i++) {
          int cellOffset = i; float v = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness - localPosition;
          float perp = v - closest; if (abs(perp) > 0.0001f) { float d = (closest + v) / 2.0f; minD = min(minD, abs(d)); }
  }
  return minD;
}
float voronoi_n_sphere_radius(VoronoiParams params, float coord) {
  float cellPosition_f = floor(coord); float localPosition = coord - cellPosition_f; int cellPosition = int(cellPosition_f);
  float closest = 0.0f; float minD = FLT_MAX; int closestOffset = 0;
  for (int i = -1; i <= 1; i++) {
          int cellOffset = i; float p = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness;
          float d = abs(p - localPosition); if (d < minD) { minD = d; closest = p; closestOffset = cellOffset; }
  }
  minD = FLT_MAX; float c2c = 0.0f;
  for (int i = -1; i <= 1; i++) {
           if (i == 0) continue;
           int cellOffset = i + closestOffset; float p = float(cellOffset) + hash_int_to_float(cellPosition + cellOffset) * params.randomness;
           float d = abs(closest - p); if (d < minD) { minD = d; c2c = p; }
  }
  return abs(c2c - closest) / 2.0f;
}

// ---- 2D Voronoi ----
VoronoiOutput voronoi_f1(VoronoiParams params, float2 coord) {
  float2 cellPosition_f = floor(coord); float2 localPosition = coord - cellPosition_f; int2 cellPosition = int2(cellPosition_f);
  float minDistance = FLT_MAX; int2 targetOffset = int2(0); float2 targetPosition = float2(0.0f);
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int2 cellOffset = int2(i, j); float2 p = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < minDistance) { targetOffset = cellOffset; minDistance = d; targetPosition = p; }
  }}
  VoronoiOutput octave; octave.Distance = minDistance; octave.Color = hash_int2_to_vec3(cellPosition + targetOffset); octave.Position = voronoi_position(targetPosition + cellPosition_f); return octave;
}
VoronoiOutput voronoi_smooth_f1(VoronoiParams params, float2 coord) {
  float2 cellPosition_f = floor(coord); float2 localPosition = coord - cellPosition_f; int2 cellPosition = int2(cellPosition_f);
  float smoothDistance = 0.0f; float3 smoothColor = float3(0.0f); float4 smoothPosition = float4(0.0f); float h = -1.0f;
  for (int j = -2; j <= 2; j++) { for (int i = -2; i <= 2; i++) {
        int2 cellOffset = int2(i, j); float2 p = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        h = h == -1.0f ? 1.0f : smoothstep(0.0f, 1.0f, 0.5f + 0.5f * (smoothDistance - d) / params.smoothness);
        float correctionFactor = params.smoothness * h * (1.0f - h);
        smoothDistance = mix(smoothDistance, d, h) - correctionFactor; correctionFactor /= 1.0f + 3.0f * params.smoothness;
        smoothColor = mix(smoothColor, hash_int2_to_vec3(cellPosition + cellOffset), h) - correctionFactor;
        smoothPosition = mix(smoothPosition, float4(p, 0.0, 0.0), h) - correctionFactor;
  }}
  VoronoiOutput octave; octave.Distance = smoothDistance; octave.Color = smoothColor; octave.Position = voronoi_position(cellPosition_f) + smoothPosition; return octave;
}
VoronoiOutput voronoi_f2(VoronoiParams params, float2 coord) {
  float2 cellPosition_f = floor(coord); float2 localPosition = coord - cellPosition_f; int2 cellPosition = int2(cellPosition_f);
  float d1 = FLT_MAX; float d2 = FLT_MAX; int2 o1 = int2(0); float2 p1 = float2(0.0f); int2 o2 = int2(0); float2 p2 = float2(0.0f);
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int2 cellOffset = int2(i, j); float2 p = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < d1) { d2 = d1; d1 = d; o2 = o1; o1 = cellOffset; p2 = p1; p1 = p; } else if (d < d2) { d2 = d; o2 = cellOffset; p2 = p; }
  }}
  VoronoiOutput octave; octave.Distance = d2; octave.Color = hash_int2_to_vec3(cellPosition + o2); octave.Position = voronoi_position(p2 + cellPosition_f); return octave;
}
float voronoi_distance_to_edge(VoronoiParams params, float2 coord) {
  float2 cellPosition_f = floor(coord); float2 localPosition = coord - cellPosition_f; int2 cellPosition = int2(cellPosition_f);
  float2 closest = float2(0.0f); float minD = FLT_MAX;
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int2 cellOffset = int2(i, j); float2 v = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness - localPosition;
          float d = dot(v, v); if (d < minD) { minD = d; closest = v; }
  }}
  minD = FLT_MAX;
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int2 cellOffset = int2(i, j); float2 v = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness - localPosition;
          float2 perp = v - closest; if (dot(perp, perp) > 0.0001f) { float d = dot((closest + v) / 2.0f, normalize(perp)); minD = min(minD, d); }
  }}
  return minD;
}
float voronoi_n_sphere_radius(VoronoiParams params, float2 coord) {
  float2 cellPosition_f = floor(coord); float2 localPosition = coord - cellPosition_f; int2 cellPosition = int2(cellPosition_f);
  float2 closest = float2(0.0f); float minD = FLT_MAX; int2 closestOffset = int2(0);
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int2 cellOffset = int2(i, j); float2 p = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness;
          float d = distance(p, localPosition); if (d < minD) { minD = d; closest = p; closestOffset = cellOffset; }
  }}
  minD = FLT_MAX; float2 c2c = float2(0.0f);
  for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
           if (i == 0 && j == 0) continue;
           int2 cellOffset = int2(i, j) + closestOffset; float2 p = float2(cellOffset) + hash_int2_to_vec2(cellPosition + cellOffset) * params.randomness;
           float d = distance(closest, p); if (d < minD) { minD = d; c2c = p; }
  }}
  return distance(c2c, closest) / 2.0f;
}

// ---- 3D Voronoi ----
VoronoiOutput voronoi_f1(VoronoiParams params, float3 coord) {
  float3 cellPosition_f = floor(coord); float3 localPosition = coord - cellPosition_f; int3 cellPosition = int3(cellPosition_f);
  float minDistance = FLT_MAX; int3 targetOffset = int3(0); float3 targetPosition = float3(0.0f);
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int3 cellOffset = int3(i, j, k); float3 pointPosition = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness;
        float distanceToPoint = voronoi_distance(pointPosition, localPosition, params);
        if (distanceToPoint < minDistance) { targetOffset = cellOffset; minDistance = distanceToPoint; targetPosition = pointPosition; }
  }}}
  VoronoiOutput octave; octave.Distance = minDistance; octave.Color = hash_int3_to_vec3(cellPosition + targetOffset); octave.Position = voronoi_position(targetPosition + cellPosition_f); return octave;
}
VoronoiOutput voronoi_smooth_f1(VoronoiParams params, float3 coord) {
  float3 cellPosition_f = floor(coord); float3 localPosition = coord - cellPosition_f; int3 cellPosition = int3(cellPosition_f);
  float smoothDistance = 0.0f; float3 smoothColor = float3(0.0f); float4 smoothPosition = float4(0.0f); float h = -1.0f;
  for (int k = -2; k <= 2; k++) { for (int j = -2; j <= 2; j++) { for (int i = -2; i <= 2; i++) {
        int3 cellOffset = int3(i, j, k); float3 p = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        h = h == -1.0f ? 1.0f : smoothstep(0.0f, 1.0f, 0.5f + 0.5f * (smoothDistance - d) / params.smoothness);
        float correctionFactor = params.smoothness * h * (1.0f - h);
        smoothDistance = mix(smoothDistance, d, h) - correctionFactor; correctionFactor /= 1.0f + 3.0f * params.smoothness;
        smoothColor = mix(smoothColor, hash_int3_to_vec3(cellPosition + cellOffset), h) - correctionFactor;
        smoothPosition = mix(smoothPosition, float4(p, 0.0f), h) - correctionFactor;
  }}}
  VoronoiOutput octave; octave.Distance = smoothDistance; octave.Color = smoothColor; octave.Position = voronoi_position(cellPosition_f) + smoothPosition; return octave;
}
VoronoiOutput voronoi_f2(VoronoiParams params, float3 coord) {
  float3 cellPosition_f = floor(coord); float3 localPosition = coord - cellPosition_f; int3 cellPosition = int3(cellPosition_f);
  float d1 = FLT_MAX; float d2 = FLT_MAX; int3 o1 = int3(0); float3 p1 = float3(0.0f); int3 o2 = int3(0); float3 p2 = float3(0.0f);
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int3 cellOffset = int3(i, j, k); float3 p = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < d1) { d2 = d1; d1 = d; o2 = o1; o1 = cellOffset; p2 = p1; p1 = p; } else if (d < d2) { d2 = d; o2 = cellOffset; p2 = p; }
  }}}
  VoronoiOutput octave; octave.Distance = d2; octave.Color = hash_int3_to_vec3(cellPosition + o2); octave.Position = voronoi_position(p2 + cellPosition_f); return octave;
}
float voronoi_distance_to_edge(VoronoiParams params, float3 coord) {
  float3 cellPosition_f = floor(coord); float3 localPosition = coord - cellPosition_f; int3 cellPosition = int3(cellPosition_f);
  float3 closest = float3(0.0f); float minD = FLT_MAX;
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int3 cellOffset = int3(i, j, k); float3 v = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness - localPosition;
        float d = dot(v, v); if (d < minD) { minD = d; closest = v; }
  }}}
  minD = FLT_MAX;
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int3 cellOffset = int3(i, j, k); float3 v = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness - localPosition;
        float3 perp = v - closest; if (dot(perp, perp) > 0.0001f) { float d = dot((closest + v) / 2.0f, normalize(perp)); minD = min(minD, d); }
  }}}
  return minD;
}
float voronoi_n_sphere_radius(VoronoiParams params, float3 coord) {
  float3 cellPosition_f = floor(coord); float3 localPosition = coord - cellPosition_f; int3 cellPosition = int3(cellPosition_f);
  float3 closest = float3(0.0f); float minD = FLT_MAX; int3 closestOffset = int3(0);
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int3 cellOffset = int3(i, j, k); float3 p = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness;
        float d = distance(p, localPosition); if (d < minD) { minD = d; closest = p; closestOffset = cellOffset; }
  }}}
  minD = FLT_MAX; float3 c2c = float3(0.0f);
  for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        if (i == 0 && j == 0 && k == 0) continue;
        int3 cellOffset = int3(i, j, k) + closestOffset; float3 p = float3(cellOffset) + hash_int3_to_vec3(cellPosition + cellOffset) * params.randomness;
        float d = distance(closest, p); if (d < minD) { minD = d; c2c = p; }
  }}}
  return distance(c2c, closest) / 2.0f;
}
"""

VORONOI_CORE_4D_GLSL = """
// ---- 4D Voronoi ----
VoronoiOutput voronoi_f1(VoronoiParams params, float4 coord) {
  float4 cellPosition_f = floor(coord); float4 localPosition = coord - cellPosition_f; int4 cellPosition = int4(cellPosition_f);
  float minDistance = FLT_MAX; int4 targetOffset = int4(0); float4 targetPosition = float4(0.0f);
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int4 cellOffset = int4(i, j, k, u); float4 p = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < minDistance) { targetOffset = cellOffset; minDistance = d; targetPosition = p; }
  }}}}
  VoronoiOutput octave; octave.Distance = minDistance; octave.Color = hash_int4_to_vec3(cellPosition + targetOffset); octave.Position = voronoi_position(targetPosition + cellPosition_f); return octave;
}
VoronoiOutput voronoi_smooth_f1(VoronoiParams params, float4 coord) {
  float4 cellPosition_f = floor(coord); float4 localPosition = coord - cellPosition_f; int4 cellPosition = int4(cellPosition_f);
  float smoothDistance = 0.0f; float3 smoothColor = float3(0.0f); float4 smoothPosition = float4(0.0f); float h = -1.0f;
  for (int u = -2; u <= 2; u++) { for (int k = -2; k <= 2; k++) { for (int j = -2; j <= 2; j++) { for (int i = -2; i <= 2; i++) {
        int4 cellOffset = int4(i, j, k, u); float4 p = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        h = h == -1.0f ? 1.0f : smoothstep(0.0f, 1.0f, 0.5f + 0.5f * (smoothDistance - d) / params.smoothness);
        float correctionFactor = params.smoothness * h * (1.0f - h);
        smoothDistance = mix(smoothDistance, d, h) - correctionFactor; correctionFactor /= 1.0f + 3.0f * params.smoothness;
        smoothColor = mix(smoothColor, hash_int4_to_vec3(cellPosition + cellOffset), h) - correctionFactor;
        smoothPosition = mix(smoothPosition, p, h) - correctionFactor;
  }}}}
  VoronoiOutput octave; octave.Distance = smoothDistance; octave.Color = smoothColor; octave.Position = voronoi_position(cellPosition_f + smoothPosition); return octave;
}
VoronoiOutput voronoi_f2(VoronoiParams params, float4 coord) {
  float4 cellPosition_f = floor(coord); float4 localPosition = coord - cellPosition_f; int4 cellPosition = int4(cellPosition_f);
  float d1 = FLT_MAX; float d2 = FLT_MAX; int4 o1 = int4(0); float4 p1 = float4(0.0f); int4 o2 = int4(0); float4 p2 = float4(0.0f);
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
        int4 cellOffset = int4(i, j, k, u); float4 p = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness;
        float d = voronoi_distance(p, localPosition, params);
        if (d < d1) { d2 = d1; d1 = d; o2 = o1; o1 = cellOffset; p2 = p1; p1 = p; } else if (d < d2) { d2 = d; o2 = cellOffset; p2 = p; }
  }}}}
  VoronoiOutput octave; octave.Distance = d2; octave.Color = hash_int4_to_vec3(cellPosition + o2); octave.Position = voronoi_position(p2 + cellPosition_f); return octave;
}
float voronoi_distance_to_edge(VoronoiParams params, float4 coord) {
  float4 cellPosition_f = floor(coord); float4 localPosition = coord - cellPosition_f; int4 cellPosition = int4(cellPosition_f);
  float4 closest = float4(0.0f); float minD = FLT_MAX;
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int4 cellOffset = int4(i, j, k, u); float4 v = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness - localPosition;
          float d = dot(v, v); if (d < minD) { minD = d; closest = v; }
  }}}}
  minD = FLT_MAX;
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int4 cellOffset = int4(i, j, k, u); float4 v = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness - localPosition;
          float4 perp = v - closest; if (dot(perp, perp) > 0.0001f) { float d = dot((closest + v) / 2.0f, normalize(perp)); minD = min(minD, d); }
  }}}}
  return minD;
}
float voronoi_n_sphere_radius(VoronoiParams params, float4 coord) {
  float4 cellPosition_f = floor(coord); float4 localPosition = coord - cellPosition_f; int4 cellPosition = int4(cellPosition_f);
  float4 closest = float4(0.0f); float minD = FLT_MAX; int4 closestOffset = int4(0);
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
          int4 cellOffset = int4(i, j, k, u); float4 p = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness;
          float d = distance(p, localPosition); if (d < minD) { minD = d; closest = p; closestOffset = cellOffset; }
  }}}}
  minD = FLT_MAX; float4 c2c = float4(0.0f);
  for (int u = -1; u <= 1; u++) { for (int k = -1; k <= 1; k++) { for (int j = -1; j <= 1; j++) { for (int i = -1; i <= 1; i++) {
           if (i == 0 && j == 0 && k == 0 && u == 0) continue;
           int4 cellOffset = int4(i, j, k, u) + closestOffset; float4 p = float4(cellOffset) + hash_int4_to_vec4(cellPosition + cellOffset) * params.randomness;
           float d = distance(closest, p); if (d < minD) { minD = d; c2c = p; }
  }}}}
  return distance(c2c, closest) / 2.0f;
}
"""

VORONOI_FRACTAL_GLSL = """
#define FRACTAL_VORONOI_DISTANCE_TO_EDGE_FUNCTION(T) \\
float fractal_voronoi_distance_to_edge(VoronoiParams params, T coord) { \\
    float amplitude = 1.0f; float max_amplitude = params.max_distance; float scale = 1.0f; float distance = 8.0f; \\
    bool zero_input = params.detail == 0.0f || params.roughness == 0.0f; \\
    for (int i = 0; i <= ceil(params.detail); ++i) { \\
      float octave_distance = voronoi_distance_to_edge(params, coord * scale); \\
      if (zero_input) { distance = octave_distance; break; } \\
      else if (i <= params.detail) { \\
        max_amplitude = mix(max_amplitude, params.max_distance / scale, amplitude); \\
        distance = mix(distance, min(distance, octave_distance / scale), amplitude); \\
        scale *= params.lacunarity; amplitude *= params.roughness; \\
      } else { \\
        float remainder = params.detail - floor(params.detail); \\
        if (remainder != 0.0f) { \\
          float lerp_amplitude = mix(max_amplitude, params.max_distance / scale, amplitude); \\
          max_amplitude = mix(max_amplitude, lerp_amplitude, remainder); \\
          float lerp_distance = mix(distance, min(distance, octave_distance / scale), amplitude); \\
          distance = mix(distance, min(distance, lerp_distance), remainder); \\
        } \\
      } \\
    } \\
    if (params.normalize) distance /= max_amplitude; \\
    return distance; \\
}

#define FRACTAL_VORONOI_X_FX_FUNCTION(T) \\
VoronoiOutput fractal_voronoi_x_fx(VoronoiParams params, T coord) { \\
  float amplitude = 1.0f; float max_amplitude = 0.0f; float scale = 1.0f; \\
  VoronoiOutput Output; Output.Distance = 0.0f; Output.Color = float3(0.0f); Output.Position = float4(0.0f); \\
  bool zero_input = params.detail == 0.0f || params.roughness == 0.0f; \\
  for (int i = 0; i <= ceil(params.detail); ++i) { \\
    VoronoiOutput octave; \\
    if (params.feature == SHD_VORONOI_F2) octave = voronoi_f2(params, coord * scale); \\
    else if (params.feature == SHD_VORONOI_SMOOTH_F1 && params.smoothness != 0.0f) octave = voronoi_smooth_f1(params, coord * scale); \\
    else octave = voronoi_f1(params, coord * scale); \\
    if (zero_input) { max_amplitude = 1.0f; Output = octave; break; } \\
    else if (i <= params.detail) { \\
      max_amplitude += amplitude; \\
      Output.Distance += octave.Distance * amplitude; Output.Color += octave.Color * amplitude; \\
      Output.Position = mix(Output.Position, octave.Position / scale, amplitude); \\
      scale *= params.lacunarity; amplitude *= params.roughness; \\
    } else { \\
      float remainder = params.detail - floor(params.detail); \\
      if (remainder != 0.0f) { \\
        max_amplitude = mix(max_amplitude, max_amplitude + amplitude, remainder); \\
        Output.Distance = mix(Output.Distance, Output.Distance + octave.Distance * amplitude, remainder); \\
        Output.Color = mix(Output.Color, Output.Color + octave.Color * amplitude, remainder); \\
        Output.Position = mix(Output.Position, mix(Output.Position, octave.Position / scale, amplitude), remainder); \\
      } \\
    } \\
  } \\
  if (params.normalize) { Output.Distance /= max_amplitude * params.max_distance; Output.Color /= max_amplitude; } \\
  Output.Position = safe_divide(Output.Position, params.scale); \\
  return Output; \\
}

FRACTAL_VORONOI_DISTANCE_TO_EDGE_FUNCTION(float)
FRACTAL_VORONOI_DISTANCE_TO_EDGE_FUNCTION(float2)
FRACTAL_VORONOI_DISTANCE_TO_EDGE_FUNCTION(float3)
FRACTAL_VORONOI_DISTANCE_TO_EDGE_FUNCTION(float4)

FRACTAL_VORONOI_X_FX_FUNCTION(float)
FRACTAL_VORONOI_X_FX_FUNCTION(float2)
FRACTAL_VORONOI_X_FX_FUNCTION(float3)
FRACTAL_VORONOI_X_FX_FUNCTION(float4)
"""

VORONOI_TEX_GLSL = """
# define INITIALIZE_VORONOIPARAMS(FEATURE) \\
  params.feature = FEATURE; params.metric = int(metric); params.scale = scale; params.detail = clamp(detail, 0.0f, 15.0f); \\
  params.roughness = clamp(roughness, 0.0f, 1.0f); params.lacunarity = lacunarity; params.smoothness = clamp(smoothness / 2.0f, 0.0f, 0.5f); \\
  params.exponent = exponent; params.randomness = clamp(randomness, 0.0f, 1.0f); params.max_distance = 0.0f; params.normalize = bool(normalize);

#define DEFINE_NODE_TEX_VORONOI(dims, T, SUFFIX) \\
void node_tex_voronoi_f1_##SUFFIX(T coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, \\
                            float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) { \\
  VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_F1) \\
  coord *= scale; \\
  params.max_distance = voronoi_distance(T(0.0f), T(0.5f + 0.5f * params.randomness), params); \\
  VoronoiOutput Output = fractal_voronoi_x_fx(params, coord); \\
  outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; \\
} \\
void node_tex_voronoi_smooth_f1_##SUFFIX(T coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, \\
                                   float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) { \\
  VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_SMOOTH_F1) \\
  coord *= scale; \\
  params.max_distance = voronoi_distance(T(0.0f), T(0.5f + 0.5f * params.randomness), params); \\
  VoronoiOutput Output = fractal_voronoi_x_fx(params, coord); \\
  outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; \\
} \\
void node_tex_voronoi_f2_##SUFFIX(T coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, \\
                            float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) { \\
  VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_F2) \\
  coord *= scale; \\
  params.max_distance = voronoi_distance(T(0.0f), T(0.5f + 0.5f * params.randomness), params) * 2.0f; \\
  VoronoiOutput Output = fractal_voronoi_x_fx(params, coord); \\
  outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; \\
} \\
void node_tex_voronoi_distance_to_edge_##SUFFIX(T coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, \\
                                          float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) { \\
  VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_DISTANCE_TO_EDGE) \\
  coord *= scale; \\
  params.max_distance = 0.5f + 0.5f * params.randomness; \\
  outDistance = fractal_voronoi_distance_to_edge(params, coord); \\
} \\
void node_tex_voronoi_n_sphere_radius_##SUFFIX(T coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, \\
                                         float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) { \\
  VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_N_SPHERE_RADIUS) \\
  coord *= scale; \\
  outRadius = voronoi_n_sphere_radius(params, coord); \\
}

DEFINE_NODE_TEX_VORONOI(1D, float, 1d)
DEFINE_NODE_TEX_VORONOI(2D, float2, 2d)
DEFINE_NODE_TEX_VORONOI(3D, float3, 3d)

// 4D Wrapper handling (vec3 + w -> float4)
void node_tex_voronoi_f1_4d(float3 coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) {   VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_F1)   float4 p = float4(coord, w) * scale;   params.max_distance = voronoi_distance(float4(0.0f), float4(0.5f + 0.5f * params.randomness), params);   VoronoiOutput Output = fractal_voronoi_x_fx(params, p);   outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; }
void node_tex_voronoi_smooth_f1_4d(float3 coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) {   VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_SMOOTH_F1)   float4 p = float4(coord, w) * scale;   params.max_distance = voronoi_distance(float4(0.0f), float4(0.5f + 0.5f * params.randomness), params);   VoronoiOutput Output = fractal_voronoi_x_fx(params, p);   outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; }
void node_tex_voronoi_f2_4d(float3 coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) {   VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_F2)   float4 p = float4(coord, w) * scale;   params.max_distance = voronoi_distance(float4(0.0f), float4(0.5f + 0.5f * params.randomness), params) * 2.0f;   VoronoiOutput Output = fractal_voronoi_x_fx(params, p);   outDistance = Output.Distance; outColor = float4(Output.Color, 1.0f); outPosition = Output.Position.xyz; }
void node_tex_voronoi_distance_to_edge_4d(float3 coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) {   VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_DISTANCE_TO_EDGE)   float4 p = float4(coord, w) * scale;   params.max_distance = 0.5f + 0.5f * params.randomness;   outDistance = fractal_voronoi_distance_to_edge(params, p); }
void node_tex_voronoi_n_sphere_radius_4d(float3 coord, float w, float scale, float detail, float roughness, float lacunarity, float smoothness, float exponent, float randomness, float metric, float normalize, out float outDistance, out float4 outColor, out float3 outPosition, out float outW, out float outRadius) {   VoronoiParams params; INITIALIZE_VORONOIPARAMS(SHD_VORONOI_N_SPHERE_RADIUS)   float4 p = float4(coord, w) * scale;   outRadius = voronoi_n_sphere_radius(params, p); }
"""

VORONOI_GLSL = SAFE_MATH_GLSL + VORONOI_DEFINES_GLSL + VORONOI_CORE_GLSL + VORONOI_CORE_4D_GLSL + VORONOI_FRACTAL_GLSL + VORONOI_TEX_GLSL

