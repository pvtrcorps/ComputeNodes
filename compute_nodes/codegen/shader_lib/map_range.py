# Map Range and Clamp GLSL functions

MAP_RANGE_GLSL = '''
// ============ Map Range Functions ============

// Linear map range
float map_range_linear(float value, float from_min, float from_max, float to_min, float to_max) {
    float factor = (from_max != from_min) ? (value - from_min) / (from_max - from_min) : 0.0;
    return to_min + factor * (to_max - to_min);
}

// Stepped map range
float map_range_stepped(float value, float from_min, float from_max, float to_min, float to_max, float steps) {
    float factor = (from_max != from_min) ? (value - from_min) / (from_max - from_min) : 0.0;
    factor = floor(factor * (steps + 1.0)) / steps;
    return to_min + factor * (to_max - to_min);
}

// Smoothstep map range (smooth Hermite interpolation)
float map_range_smoothstep(float value, float from_min, float from_max, float to_min, float to_max) {
    float factor = (from_max != from_min) ? clamp((value - from_min) / (from_max - from_min), 0.0, 1.0) : 0.0;
    factor = factor * factor * (3.0 - 2.0 * factor);
    return to_min + factor * (to_max - to_min);
}

// Smootherstep map range (Ken Perlin's improved smoothstep)
float map_range_smootherstep(float value, float from_min, float from_max, float to_min, float to_max) {
    float factor = (from_max != from_min) ? clamp((value - from_min) / (from_max - from_min), 0.0, 1.0) : 0.0;
    factor = factor * factor * factor * (factor * (factor * 6.0 - 15.0) + 10.0);
    return to_min + factor * (to_max - to_min);
}

// Vector versions
vec3 map_range_linear_vec3(vec3 value, vec3 from_min, vec3 from_max, vec3 to_min, vec3 to_max) {
    return vec3(
        map_range_linear(value.x, from_min.x, from_max.x, to_min.x, to_max.x),
        map_range_linear(value.y, from_min.y, from_max.y, to_min.y, to_max.y),
        map_range_linear(value.z, from_min.z, from_max.z, to_min.z, to_max.z)
    );
}

// ============ Clamp Functions ============

// Clamp MinMax mode (strict min < max)
float clamp_minmax(float value, float min_val, float max_val) {
    return clamp(value, min_val, max_val);
}

// Clamp Range mode (auto-swap if min > max)
float clamp_range(float value, float min_val, float max_val) {
    float actual_min = min(min_val, max_val);
    float actual_max = max(min_val, max_val);
    return clamp(value, actual_min, actual_max);
}
'''
