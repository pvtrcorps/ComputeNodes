# Voronoi Core GLSL Functions (1D, 2D, 3D)
# Ported from Blender's gpu_shader_material_tex_voronoi.glsl

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
