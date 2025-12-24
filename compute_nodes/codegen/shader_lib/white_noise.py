# White Noise GLSL Functions
# Ported from Blender's gpu_shader_material_white_noise.glsl

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
