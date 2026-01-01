# Hoja de diseño — Compute Graph Engine para Blender (2D + 1D)

> [!CAUTION]
> ## ⚠️ DEPRECATED — See [GEMINI.md](./GEMINI.md)
> This document is outdated. The authoritative design documentation is now in **GEMINI.md**.
> This file is kept for historical reference only.

---

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

## 2.5 Paradigma Field-Based (Nuevo - Diciembre 2025)

> **ARQUITECTURA FUNDAMENTAL** inspirada en Geometry Nodes Fields.

### Conceptos Clave

| Concepto | Geometry Nodes | Compute Nodes |
|----------|----------------|---------------|
| Contexto (define dominio) | Geometry | **Texture** (resolución, dimensiones) |
| Funciones lazy | Fields (Position, Normal...) | **Fields** (Position, Noise, Math...) |
| Materialización | Realize Instances | **Rasterize** (evalúa fields en contexto texture) |

### Reglas de Diseño

1. **Fields** son funciones lazy que NO conocen su contexto de evaluación
   - `Position`, `Noise`, `Math`, `VectorMath`, etc.
   - Sockets: `NodeSocketColor` (amarillo), `NodeSocketFloat`, `NodeSocketVector`

2. **Textures** son datos concretos en GPU con resolución definida
   - Tienen width×height (o depth para 3D)
   - Socket: `ComputeSocketTexture` (cyan)

3. **Rasterize** es el ÚNICO nodo que convierte Field→Texture
   - Define el dominio (resolución)
   - Los fields conectados se evalúan en ESE contexto

4. **Output** NO tiene resolución - solo recibe Texture y escribe a Image datablock

5. **Resize** opera Texture→Texture (reescala con bilinear)

6. **Sample** convierte Texture→Field (lee de textura, retorna a field-space)

### Flujo Típico

```
Position ──► Noise ──► Rasterize(512×512) ──► Output
  (field)    (field)      (define domain)     (escribe)
                              ↓
                         [Texture 512×512]
```

### Conversiones

```
Field → Texture : SOLO via Rasterize
Texture → Field : SOLO via Sample
Texture → Texture : Resize
Field → Output : ERROR (requiere Rasterize primero)
```



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

1.  **Implementar Node Resize**: Habilitar texturas intermedias de distinta resolución. ✅ DONE
2.  **Sistema de Bridges**: Implementar rasterización básica de atributos de malla (UV Space).
3.  **Soporte 1D**: Habilitar buffers para cómputo general no-imagen (partículas, datos).
4.  **UX**: Mejorar visualización de errores de compilación en el editor.

---

## 8. Grid Architecture Update (Diciembre 2025)

> **RENAMING IMPORTANTE** para evitar colisiones con terminología de Blender.

### Cambios de Naming

| Antes | Ahora | Razón |
|-------|-------|-------|
| `ComputeSocketTexture` | `ComputeSocketGrid` | Evita colisión con Blender Texture datablocks |
| `ComputeNodeRasterize` | `ComputeNodeCapture` | Más descriptivo (GN: "Capture Attribute") |
| `ComputeNodeOutput` | `ComputeNodeOutputImage` | Específico para Grid2D→Image |

### Grid Architecture

Todos los Grids son internamente 3D:
- **Grid2D** = Grid(W, H, 1) donde depth=1
- **Grid3D** = Grid(W, H, D) donde todos >1
- **Grid1D** = Grid(W, 1, 1) donde height=1, depth=1 (futuro)

### Future Output Nodes

| Nodo | Entrada | Salida | Formato |
|------|---------|--------|---------|
| **Output Image** | Grid2D | bpy.data.images | PNG/EXR/HDR |
| **Output Volume** | Grid3D | OpenVDB | .vdb |
| **Output Sequence** | Grid2D[] | Image sequence | Frame $F.png |
| **Output Attribute** | Grid* | Mesh attribute | Named attribute |

