# Voronoi GLSL Functions Package
# Re-exports all voronoi-related GLSL constants

from .core import SAFE_MATH_GLSL, VORONOI_DEFINES_GLSL, VORONOI_CORE_GLSL
from .core_4d import VORONOI_CORE_4D_GLSL
from .fractal import VORONOI_FRACTAL_GLSL
from .tex import VORONOI_TEX_GLSL

# Combined VORONOI_GLSL constant for backward compatibility
VORONOI_GLSL = (
    SAFE_MATH_GLSL + 
    VORONOI_DEFINES_GLSL + 
    VORONOI_CORE_GLSL + 
    VORONOI_CORE_4D_GLSL + 
    VORONOI_FRACTAL_GLSL + 
    VORONOI_TEX_GLSL
)

__all__ = [
    'SAFE_MATH_GLSL', 'VORONOI_DEFINES_GLSL', 'VORONOI_CORE_GLSL',
    'VORONOI_CORE_4D_GLSL', 'VORONOI_FRACTAL_GLSL', 'VORONOI_TEX_GLSL',
    'VORONOI_GLSL'
]
