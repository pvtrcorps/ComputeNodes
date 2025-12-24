# Hoja de diseño — Compute Graph Engine para Blender (2D + 1D)

> **Documento Vivo - Actualizado: Diciembre 2025**
>
> **Estado:** En desarrollo activo (Fase Alpha).
> **Versión del Documento:** 1.1 (Revisión de Realidad)
>
> Este documento define el alcance, arquitectura y principios del sistema. Ha sido actualizado para reflejar el estado real de la implementación actual.

---

## 1. Visión del proyecto

Construir un **motor de cómputo en GPU basado en nodos**, integrado en Blender, que permita a artistas técnicos y TDs **describir cálculos complejos de forma declarativa** y ejecutarlos mediante **compute shaders modernos**, usando el `gpu` module de Blender como backend.

El sistema es **agnóstico de dominio**. No está diseñado específicamente para planetas, terrenos, erosión o simulaciones concretas. Esos sistemas deben **emerger por composición** a partir de **building blocks genéricos**.

---

## 2. Principios innegociables

1. **Declarativo y lazy**
   Los nodos describen un cálculo. Nada se ejecuta hasta que existe un Output.

2. **Compilación, no evaluación**
   El grafo completo se analiza, optimiza y compila a uno o varios kernels compute (GLSL).

3. **Core pequeño y estable**
   El núcleo expone pocos conceptos (Math, Vector, Sample, Control Flow).

4. **Composición sobre especialización**
   Sistemas complejos se construyen con Node Groups.

5. **Separación de responsabilidades**
   - Compute Graph → datos y campos (Imágenes/Buffers)
   - Geometry Nodes → espacio, geometría y visibilidad (Mesh/Instancing)

6. **Determinismo**
   Mismos inputs producen mismos outputs.

---

## 3. Arquitectura Implementada

```
NodeTree (UI)
   ↓
Graph Extractor (Python)
   ↓
IR (SSA - Intermediate Representation)
   ↓
Pass Planner / Scheduler
   ↓
GLSL Codegen
   ↓
Runtime (GPU module)
```

### Estado de la Arquitectura
- **IR**: Basada en SSA (`Value`, `OpCode`). Implementada en `ir/`.
- **Codegen**: Generación de GLSL funcional.
- **Runtime**: Ejecutor basado en `gpu.types.GPUShader`. Soporta imágenes 2D.

---

## 4. Nodos y Building Blocks (Estado Real)

### 4.1 Implementados (Core)

Estos nodos están funcionales en el código actual:

#### **Input / Output**
- **Image Input**: Carga datablocks `bpy.types.Image`.
- **Image Write**: Escribe a datablocks.
- **Image Info**: Obtiene dimensiones.
- **Output**: **Define la resolución y formato del grafo para este target**. Escribe el resultado final a una imagen de Blender.

#### **Espaciales y Acceso**
- **Position**: Coordenadas actuales (Pixel Index, Normalized UV, Global Index).
- **Sample**: Lee de una imagen en coordenadas arbitrarias.

#### **Matemáticas**
- **Math**: Operaciones escalares completas (Add, Sub, Mul, Sin, Cos, Pow, etc).
- **Vector Math**: Operaciones vectoriales (Dot, Cross, Reflect, Distance, etc).
- **Map Range**: Reasignación lineal/escalonada.
- **Clamp**: Limitación de valores.

#### **Control de Flujo**
- **Switch**: Condicional por píxel (If/Else).
- **Mix**: Mezcla lineal.
- **Repeat Zone**: Bucles iterativos explícitos (`Repeat Input` -> `Repeat Output`).

#### **Texturas Procedurales**
- **Noise Texture**: Fraccional Browniano (fBm) 1D/2D/3D/4D.
- **White Noise**: Ruido aleatorio blanco.
- **Voronoi**: Celdas, F1, F2, Smooth, Distance.

#### **Convertidores**
- **Separate/Combine XYZ**: Vector <-> Floats.
- **Separate/Combine Color**: Color <-> Floats (RGB, HSV, HSL).

---

### 4.2 Planificados / Pendientes (Roadmap)

Estos elementos estaban en el diseño original pero **no se encuentran implementados aún**:

- **[PLANIFICADO] Resize Node**: Crítico para cascadas y rendimiento. *Estado: No encontrado en codebase.*
- **[PLANIFICADO] Domain Node**: Alternativa para definir espacio sin depender de Output. *Estado: Funcionalidad parcialmente cubierta por Output Node.*
- **[PLANIFICADO] Buffer 1D Support**: Nodos para leer/escribir buffers lineales (Histogramas, LUTs). *Estado: OpCodes existen (`BUFFER_READ/WRITE`), Nodos UI faltan.*
- **[PLANIFICADO] Reducciones**: Nodos `Attribute Statistic` o `Image Statistic` (Sum, Min, Max de toda la imagen).
- **[PLANIFICADO] Ping-Pong Helper**: Abstracción para simulación temporal simple.

---

## 5. Modelo de Resolución (Situación Actual)

A diferencia del diseño original "Pull-based" complejo, el sistema actual opera mayormente de forma **Output-driven**:

1.  **Output Node**: Define explícitamente `Width`, `Height` y `Format` (e.g., `RGBA32F`, `1024x1024`).
2.  **Propagación**: El grafo se compila asumiendo estas dimensiones de despacho.
3.  **Inputs**: Las imágenes de entrada se samplean. Si no coinciden en tamaño, la operación `Sample` maneja la lectura (UV o Pixel coords), pero no redimensiona el flujo de ejecución principal implícitamente.

> **Nota sobre Resize**: La funcionalidad de "Cascadas" (cambiar resolución a mitad de grafo) requiere el nodo `Resize` que instancia un pase intermedio. Sin este nodo, todo el grafo se ejecuta a la resolución del Output.

---

## 6. Integración con Blender (Bridges)

*Estado: Carpeta `adapters/` vacía. Funcionalidad Pendiente.*

El diseño contempla "Puentes" para traer datos de la escena:
- **Mesh Attribute Bridge**: Rasterizar geometría a texturas.
- **Scene Capture**: Cámaras virtuales.

Actualmente, la entrada principal son **Imágenes de Blender** existentes y **Valores Uniforms** (nodos de input básicos).

---

## 7. Próximos Pasos Recomendados

Para alinear la implementación con la visión original y desbloquear el potencial completo:

1.  **Implementar Node Resize**: Habilitar texturas intermedias de distinta resolución.
2.  **Sistema de Bridges**: Implementar rasterización básica de atributos de malla (UV Space).
3.  **Soporte 1D**: Habilitar buffers para cómputo general no-imagen (partículas, datos).
4.  **UX**: Mejorar visualización de errores de compilación en el editor.
