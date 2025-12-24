# Voronoi Texture Node GLSL Functions

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
