# Hash GLSL Functions
# Ported from Blender's gpu_shader_common_hash.glsl
# Source: https://github.com/blender/blender/tree/main/source/blender/gpu/shaders

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
