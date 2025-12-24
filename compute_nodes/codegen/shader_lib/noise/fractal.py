# Fractal Noise GLSL Functions
# Ported from Blender's gpu_shader_material_fractal_noise.glsl and gpu_shader_material_tex_noise.glsl

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
