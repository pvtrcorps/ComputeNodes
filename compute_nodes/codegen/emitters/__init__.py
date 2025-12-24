# GLSL Emitters Package
# Modular handlers for emitting GLSL code per OpCode

from .registry import get_emitter

__all__ = ['get_emitter']
