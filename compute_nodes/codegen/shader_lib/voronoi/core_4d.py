# Voronoi 4D GLSL Functions
# 4D variants are separate due to their size

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
