# Color conversion GLSL functions
# RGB <-> HSV <-> HSL conversions

COLOR_GLSL = '''
// ============ Color Conversion Functions ============

// RGB to HSV conversion
// Based on Blender's internal implementation
vec3 rgb_to_hsv(vec3 rgb) {
    float cmax = max(rgb.r, max(rgb.g, rgb.b));
    float cmin = min(rgb.r, min(rgb.g, rgb.b));
    float delta = cmax - cmin;
    
    vec3 hsv;
    
    // Value
    hsv.z = cmax;
    
    // Saturation
    if (cmax > 0.0) {
        hsv.y = delta / cmax;
    } else {
        hsv.y = 0.0;
    }
    
    // Hue
    if (delta > 0.0) {
        if (cmax == rgb.r) {
            hsv.x = (rgb.g - rgb.b) / delta;
            if (hsv.x < 0.0) hsv.x += 6.0;
        } else if (cmax == rgb.g) {
            hsv.x = 2.0 + (rgb.b - rgb.r) / delta;
        } else {
            hsv.x = 4.0 + (rgb.r - rgb.g) / delta;
        }
        hsv.x /= 6.0;
    } else {
        hsv.x = 0.0;
    }
    
    return hsv;
}

// HSV to RGB conversion
vec3 hsv_to_rgb(vec3 hsv) {
    float h = hsv.x;
    float s = hsv.y;
    float v = hsv.z;
    
    if (s == 0.0) {
        return vec3(v, v, v);
    }
    
    h = mod(h, 1.0) * 6.0;
    int i = int(floor(h));
    float f = h - float(i);
    float p = v * (1.0 - s);
    float q = v * (1.0 - s * f);
    float t = v * (1.0 - s * (1.0 - f));
    
    vec3 rgb;
    if (i == 0) { rgb = vec3(v, t, p); }
    else if (i == 1) { rgb = vec3(q, v, p); }
    else if (i == 2) { rgb = vec3(p, v, t); }
    else if (i == 3) { rgb = vec3(p, q, v); }
    else if (i == 4) { rgb = vec3(t, p, v); }
    else { rgb = vec3(v, p, q); }
    
    return rgb;
}

// RGB to HSL conversion
vec3 rgb_to_hsl(vec3 rgb) {
    float cmax = max(rgb.r, max(rgb.g, rgb.b));
    float cmin = min(rgb.r, min(rgb.g, rgb.b));
    float delta = cmax - cmin;
    
    vec3 hsl;
    
    // Lightness
    hsl.z = (cmax + cmin) * 0.5;
    
    // Saturation
    if (delta > 0.0) {
        if (hsl.z < 0.5) {
            hsl.y = delta / (cmax + cmin);
        } else {
            hsl.y = delta / (2.0 - cmax - cmin);
        }
    } else {
        hsl.y = 0.0;
    }
    
    // Hue (same as HSV)
    if (delta > 0.0) {
        if (cmax == rgb.r) {
            hsl.x = (rgb.g - rgb.b) / delta;
            if (hsl.x < 0.0) hsl.x += 6.0;
        } else if (cmax == rgb.g) {
            hsl.x = 2.0 + (rgb.b - rgb.r) / delta;
        } else {
            hsl.x = 4.0 + (rgb.r - rgb.g) / delta;
        }
        hsl.x /= 6.0;
    } else {
        hsl.x = 0.0;
    }
    
    return hsl;
}

// Helper for HSL to RGB
float hsl_hue_to_rgb(float p, float q, float t) {
    if (t < 0.0) t += 1.0;
    if (t > 1.0) t -= 1.0;
    if (t < 1.0 / 6.0) return p + (q - p) * 6.0 * t;
    if (t < 0.5) return q;
    if (t < 2.0 / 3.0) return p + (q - p) * (2.0 / 3.0 - t) * 6.0;
    return p;
}

// HSL to RGB conversion
vec3 hsl_to_rgb(vec3 hsl) {
    float h = hsl.x;
    float s = hsl.y;
    float l = hsl.z;
    
    if (s == 0.0) {
        return vec3(l, l, l);
    }
    
    float q = (l < 0.5) ? (l * (1.0 + s)) : (l + s - l * s);
    float p = 2.0 * l - q;
    
    float r = hsl_hue_to_rgb(p, q, h + 1.0 / 3.0);
    float g = hsl_hue_to_rgb(p, q, h);
    float b = hsl_hue_to_rgb(p, q, h - 1.0 / 3.0);
    
    return vec3(r, g, b);
}
'''
