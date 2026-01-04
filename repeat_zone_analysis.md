# Repeat Zone Implementation Analysis & Redesign

> **Objetivo**: Rediseño completo del sistema de Repeat Zones para ser un núcleo confiable del addon, capaz de soportar miles de iteraciones, decenas de texturas, multiresoluciones y anidamientos.

---

## 1. Estado Actual — Análisis Crítico

### 1.1 Arquitectura Actual

La implementación actual se distribuye en múltiples componentes:

#### **A. Nodos UI ([nodes/repeat.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/nodes/repeat.py) — 860 líneas)**

**Fortalezas:**
- ✅ UX excelente con drag-to-add sockets (patrón extension socket)
- ✅ Sincronización automática entre Input/Output paired nodes
- ✅ PropertyGroup bien estructurado ([ComputeRepeatItem](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/nodes/repeat.py#128-150))
- ✅ Validación Grid-only en tiempo de conexión

**Debilidades críticas:**
- ❌ **Socket tipo mixto NO funcional**: Aunque el código define `NodeSocketFloat`, `Vector`, `Color` — solo Grid funciona en runtime
- ❌ No hay feedback visual de rendering/progreso
- ❌ No hay límites o warnings sobre número de iteraciones
- ❌ [repeat_items](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/nodes/repeat.py#749-763) almacena tipos que nunca se usan (Float, Vector, Color)

#### **B. Graph Extraction ([graph_extract/handlers/repeat.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/graph_extract/handlers/repeat.py) — 306 líneas)**

**Fortalezas:**
- ✅ Validación Grid-only explícita con mensajes de error claros
- ✅ Creación de `StateVar` objects (no dicts)
- ✅ Metadata completa en `PASS_LOOP_BEGIN/END`
- ✅ Manejo de initial_value, ping/pong resource allocation

**Debilidades:**
- ❌ **CRITICAL**: [_find_source_resource()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/graph_extract/handlers/repeat.py#31-39) puede fallar si resolution no está determinada → crea buffers 0x0
- ❌ No hay inferencia de formatos: siempre `RGBA32F` (desperdicio de memoria para masks/heightmaps)
- ❌ `PASS_LOOP_READ` crea Values pero no se usan efectivamente en codegen
- ❌ Hard-coded `is_internal=True` — no hay opción para exponer buffers intermedios

#### **C. Planificador ([planner/loops.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py) — 340 líneas)**

**Fortalezas:**
- ✅ Nested loop support con [parse_ops_recursive()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#114-157)
- ✅ Pass splitting inteligente por RAW hazards y resource limits (7 bindings)
- ✅ Deduplicación de ops para evitar duplicados de Phase 2 field deps
- ❌ **CRITICAL BUG**: `resolution_per_iteration` está definido pero **nunca se usa**

**Debilidades fundamentales:**
- ❌ **PassLoop solo almacena metadata**: No hay ejecución real diferenciada
- ❌ [iterations](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#103-113) puede ser `int | Value` — el scheduler no resuelve Values dynamic
- ❌ [wrap_passes_in_loops()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#77-339) es frágil: depende de que LOOP_BEGIN y LOOP_END estén en orden perfecto
- ❌ No hay soporte para BREAK/CONTINUE early-exit
- ❌ Nesting depth (`depth` field) se calcula pero no se usa

#### **D. Runtime Executor ([runtime/executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) — 1003 líneas)**

**FOR loops críticos:**

```python
# Línea 439-533: Loop principal
for iter_idx in range(iterations):
    # Swap ping-pong (líneas 442-450)
    # Update loop context (452-482)
    # Execute body passes (484-491)
    # Copy blur/filter outputs (495-533)
        # DYNAMIC SIZING (líneas 514-532)
```

**Fortalezas:**
- ✅ Ping-pong swapping automático basado en `iter_idx % 2`
- ✅ Dynamic texture pooling para Resize en loops
- ✅ `_loop_context` uniforms para shaders (iteration, read_width, etc.)
- ✅ [_copy_texture()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py#656-690) especializado por format/dimensions

**Debilidades GRAVES:**

1. **Inicialización ineficiente (líneas 426-437)**:
   - Mapea `ping_idx` directamente a textura inicial → **NO HAY COPIA**
   - Problema: Primera iteración lee datos "sucios" si la textura se reutiliza
   - Solución: SIEMPRE copiar initial → ping en iter 0

2. **Dynamic pool sin límites (líneas 520-528)**:
   - [get_or_create()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/textures.py#182-223) puede acumular cientos de texturas sin liberar
   - No hay [release()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/textures.py#224-233) al final del loop
   - Memory leak en escenarios multi-resolution

3. **Falta de memory barriers estratégicos**:
   - Barrier solo al final de iteración (línea 553)
   - ¿Qué pasa con loops anidados? → Race conditions

4. **[_evaluate_dynamic_size()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py#600-655) limitado (líneas 600-654)**:
   - Solo soporta patrón `MUL(base, POW(2, iter))`
   - No soporta expresiones arbitrarias (MAP_RANGE, condicionales, etc.)

5. **Final buffer logic frágil (líneas 556-597)**:
   - `copy_from_resource` hack para Resize outputs
   - Output size adjustment posterior (584-596) — debería calcularse antes

---

### 1.2 Blender EEVEE — Lecciones Clave

Basado en la investigación de las implementaciones de EEVEE:

#### **Key Insights:**

1. **Native GLSL Loops** (Proyecto #145269):
   - Blender genera `for(int i = 0; i < iterations; ++i) { ... }` directamente en GLSL
   - Ventajas:
     - ✅ No hay overhead de múltiples dispatches (1 shader, N iteraciones)
     - ✅ Iteration count dinámico (uniform)
     - ✅ Mejora compilación y runtime performance
   
2. **Constant Folding Requirement** (Proyecto #141936):
   - Para compatibilidad Cycles/EEVEE: iteration count debe ser constante post-folding
   - **Implicación para nosotros**: Si queremos dynamic iterations, GPU-only approach es OK

3. **Ping-Pong en GLSL**:
   - EEVEE probablemente usa [texture(buf[i % 2], uv)](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py#656-690) dentro del loop shader
   - Requiere array uniforms o bindless textures

4. **Memory Management**:
   - Geometry Nodes Repeat Zones: Admiten Grid (geometry) state con ping-pong CPU-side
   - Shader Repeat Zones: Limitados a valores escalares en shaders (no texturas)

---

## 2. Limitaciones Arquitecturales Fundamentales

### 2.1 Multi-Pass vs Single-Pass

**Nuestra implementación actual: MULTI-PASS**
```
Loop(10 iterations):
    Pass 1: Dispatch → Barrier
    Pass 2: Dispatch → Barrier
    ...
    Pass N: Dispatch → Barrier
```

**Problema:**
- Overhead de 10 dispatches para 10 iteraciones
- No aprovecha GPU parallelism intra-loop
- Imposible hacer early-exit (BRE AK basado en condición)

**EEVEE approach: SINGLE-PASS**
```glsl
for (int i = 0; i < u_iterations; ++i) {
    vec4 val = texture(states[i % 2], uv);
    // ... process ...
    imageStore(states[(i+1) % 2], coord, result);
}
```

**Ventaja:**
- 1 dispatch ejecuta N iteraciones
- GPU puede optimizar el loop
- Dynamic iteration count via uniform

**Desventaja para nuestro caso:**
- Requiere que TODO el loop body quepa en un shader
- Limitaciones de resource bindings (máx 8-16 images summed_READ+WRITE)
- No soporta loops con múltiples passes internos (e.g., Sample → Math → Capture en loop)

### 2.2 ¿Por qué NO podemos adoptarlo directamente?

**Nuestra filosofía de diseño**:
> "Building Blocks First" — Users construyen complejidad con primitivas simples

**Ejemplo típico de uso:**
```
Repeat Input (10)
  └─ Current → Sample(UV) → Noise → Math → Capture → Next
```

Esto genera **múltiples Ops** en el IR:
- `SAMPLE` (field op)
- `NOISE` (field op)
- `ADD` (field op)
- `IMAGE_STORE` (Capture)

**En scheduler** → Mínimo 2 passes:
1. Pass con field chain
2. Pass con IMAGE_STORE (boundary)

**→ Imposible fusionar en single-pass GLSL loop**

---

## 3. Propuesta de Rediseño — Hybrid Approach

### 3.1 Filosofía

**Meta:** Combinar lo mejor de ambos mundos:
- **Simple loops** (body = 1 pass) → Single-pass GLSL optimization
- **Complex loops** (body = N passes) → Multi-pass con mejoras


### 3.2 Componentes Clave

#### **A. IR — Nuevos Opcodes**

```python
# Estado actual
OpCode.PASS_LOOP_BEGIN  # Marker
OpCode.PASS_LOOP_END    # Marker
OpCode.PASS_LOOP_READ   # Unused

# Propuesta
OpCode.LOOP_BEGIN       # Marca inicio, almacena metadata
OpCode.LOOP_END         # Marca fin
OpCode.LOOP_STATE_READ  # Lee ping buffer (materializado en codegen)
OpCode.LOOP_STATE_WRITE # Escribe pong buffer (materializado en codegen)
OpCode.LOOP_ITERATION   # Uniform iteration index
OpCode.LOOP_BREAK       # Early exit (futuro)
```

**Metadata ampliada:**
```python
@dataclass
class LoopMetadata:
    iterations: int | Value  # Soporta dynamic
    state_vars: List[StateVar]
    
    # NUEVO: Flags para optimización
    is_simple: bool  # True si body = 1 pass sin hazards
    max_nesting_depth: int
    
    # NUEVO: Resolution management
    resolution_mode: Literal["static", "cascade", "custom"]
    resolution_expressions: Dict[str, Value]  # {"width": expr, "height": expr}
    
    # NUEVO: Format optimization
    infer_formats: bool  # Auto-detectar R8, RG16F, etc.
```

#### **B. Scheduler — Dos Pipeline**

```python
def schedule_loop(loop_region, ops, graph):
    # 1. Analizar complejidad del body
    body_analysis = analyze_loop_body(ops[begin:end])
    
    if body_analysis.is_simple:
        # OPTIMIZACIÓN: Single-pass GLSL loop
        return create_single_pass_loop(loop_region, graph)
    else:
        # LEGACY MEJORADO: Multi-pass con optimizaciones
        return create_multi_pass_loop(loop_region, ops, graph)
```

**`is_simple` criteria:**
- Exactamente 1 ComputePass en body
- Sin RAW hazards internos
- ≤ 4 Grid states (límite de texturas array)
- Sin loops anidados

#### **C. Codegen — Template-Based Generation**

**Single-pass template:**
```glsl
layout(binding=0) uniform sampler2D u_states_ping[4];
layout(binding=4, rgba32f) writeonly uniform image2D u_states_pong[4];
uniform int u_iterations;

void main() {
    ivec2 coord = ivec2(gl_GlobalInvocationID.xy);
    
    // Ping-pong array indices
    for (int iter = 0; iter < u_iterations; ++iter) {
        int read_idx = iter % 2;
        int write_idx = (iter + 1) % 2;
        
        // User code injection point
        {{LOOP_BODY}}
    }
}
```

**Multi-pass (actual):**
- Sin cambios en generación per-pass
- MEJORA: Reutilizar shaders via cache (hash de ops + resources)

#### **D. Runtime — Memory Management Robusto**

**Cambios clave:**

1. **Texture Pool con lifecycle tracking:**
```python
class ManagedTexturePool:
    def __init__(self):
        self._pool: Dict[Key, List[Texture]] = {}
        self._leases: Dict[int, Lease] = {}  # texture_id → lease
    
    def acquire(self, size, format, dims) -> Lease:
        tex = self._get_or_create(size, format, dims)
        lease = Lease(tex, self)
        self._leases[id(tex)] = lease
        return lease
    
    def release(self, lease: Lease):
        # Return to pool + clear tracking
        ...
```

2. **Loop Execution context:**
```python
@dataclass
class LoopContext:
    iteration: int
    state_buffers: Dict[str, PingPongPair]
    dynamic_sizes: Dict[str, Tuple[int, int, int]]
    
    def swap_buffers(self):
        for pair in self.state_buffers.values():
            pair.swap()
    
    def update_dynamic_sizes(self, iteration):
        for name, expr in self.resolution_expressions.items():
            self.dynamic_sizes[name] = self.evaluate_size(expr, iteration)
```

3. **Initialization Copy Strategy:**
```python
# SIEMPRE copiar en iteration 0
if iter_idx == 0:
    for state in loop.state_vars:
        if state.initial_value:
            copy_texture(
                src=texture_map[state.initial_value.resource_index],
                dst=ping_pong_pair.ping
            )
```

---

## 4. Multi-Resolution Support — Diseño Completo

### 4.1 Casos de Uso

1. **Mipmapping manual** (power-of-2 cascade):
   ```
   Loop(8): size = 512 >> iteration
   ```

2. **Progressive refinement**:
   ```
   Loop(10): size = 64 * (1 + iteration)
   ```

3. **Conditional resize**:
   ```
   Loop(100): if error > threshold → double resolution
   ```

### 4.2 Implementation Strategy

**Option A: Expression-Based (implemented partially)**
```python
# En graph extraction
width_expr = builder.mul(
    base_width_value,
    builder.emit(OpCode.POW, [const_2, iteration_value], DataType.INT)
)

state.size_expression = {"width": width_expr, "height": height_expr}
```

**Evaluación en runtime:**
- Requiere mini-interpreter para IR expressions
- Overhead por iteración

**Option B: Callback-Based (flexible)**
```python
def resize_callback(iteration: int, prev_size: Tuple) -> Tuple:
    return (prev_size[0] * 2, prev_size[1] * 2)

loop_metadata.resize_callback = resize_callback
```

**Ventajas**: Arbitrary logic, fácil debug
**Desventajas**: No serializable en graph

**Propuesta: Hybrid**
- Expression-based para casos comunes (GLSL-evaluable)
- Callback para casos edge (developer-only)

### 4.3 Texture Reallocation on Resize

**Problema actual:**
Línea 514-532 en executor.py reallocates en el middle del loop

**Mejora:**
```python
# PRE-ALLOCATE all sizes upfront
def pre_allocate_cascade(loop, max_iter):
    size_schedule = []
    for i in range(max_iter):
        size = evaluate_size_expr(loop.size_expr, i)
        size_schedule.append(size)
    
    # Allocate largest size needed
    max_size = max(size_schedule, key=lambda s: s[0]*s[1])
    
    # Option 1: Allocate max, use subregion
    tex = pool.acquire(max_size, format, dims)
    
    # Option 2: Pre-allocate all sizes
    textures_by_size = {size: pool.acquire(size, ...) for size in set(size_schedule)}
    
    return SizeCascade(schedule=size_schedule, textures=textures_by_size)
```

**Trade-off:**
- ✅ No mid-loop allocation (performance)
- ❌ Más memoria upfront
- ❌ No soporta data-dependent resize

---

## 5. Nested Loops — Stack-Based Execution

### 5.1 Current State

[parse_ops_recursive()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#114-157) en loops.py soporta parsing nested, pero executor solo maneja 1 nivel.

### 5.2 Propuesta

**Stack de LoopContexts:**
```python
class LoopExecutor:
    def __init__(self):
        self._context_stack: List[LoopContext] = []
    
    def execute_loop(self, loop: PassLoop, texture_map):
        # Push new context
        ctx = LoopContext(loop, parent=self._context_stack[-1] if self._context_stack else None)
        self._context_stack.append(ctx)
        
        try:
            for iter_idx in range(loop.iterations):
                ctx.iteration = iter_idx
                ctx.swap_buffers()
                
                for item in loop.body_passes:
                    if isinstance(item, PassLoop):
                        # RECURSION
                        self.execute_loop(item, texture_map)
                    else:
                        self._run_pass(item, texture_map, ctx)
        finally:
            self._context_stack.pop()
```

**Uniforms shader:**
```glsl
uniform int u_loop_depth;  // 0 = outer, 1 = inner, etc.
uniform int u_loop_iterations[4];  // Stack de iteration counts
uniform int u_current_iteration[4];  // [outer_iter, inner_iter, ...]
```

---

## 6. Extensibilidad — Soporte para Nuevos Tipos

### 6.1 Roadmap de Tipos

| Tipo | Representa | Ping-Pong? | Implementation |
|------|-----------|-----------|----------------|
| **Grid** (actual) | 2D/3D Texture | ✅ Sí | ImageDesc resources |
| **Field** (futuro) | Lazy expression | ❌ Serializar a GLSL string | StoredField opcode |
| **Scalar** (float/int) | Uniform value | ⚠️ Acumula en SSBO | Buffer<float> ping/pong |
| **MeshBuffer** (roadmap) | Vertex/Index data | ✅ Sí | SSBO ping/pong |

### 6.2 Abstracción

```python
@dataclass
class StateVar:
    name: str
    index: int
    data_type: DataType
    
    # Type-specific handlers
    allocate: Callable[[ctx], Resource]
    read: Callable[[resource, ctx], Value]
    write: Callable[[value, resource, ctx], None]
    swap: Callable[[ctx], None]
    
    # Grid-specific (legacy)
    @classmethod
    def create_grid(cls, name, size, format):
        return cls(
            name=name,
            data_type=DataType.HANDLE,
            allocate=lambda ctx: create_ping_pong_images(size, format),
            read=lambda res, ctx: sample_op(res.ping if ctx.iter % 2 == 0 else res.pong),
            write=lambda val, res, ctx: store_op(val, res.pong if ctx.iter % 2 == 0 else res.ping),
            swap=lambda ctx: None  # Automático via read/write logic
        )
```

---

## 7. Performance — Targets para 1000+ Iterations

### 7.1 Benchmarks Objetivo

| escenario | Iterations | Resolution | Target Time | Bottleneck Esperado |
|----------|-----------|-----------|-------------|---------------------|
| Simple blur | 1000 | 512x512 | < 100ms | Dispatch overhead |
| Erosion (multi-pass) | 100 | 1024x1024 | < 500ms | Texture reads |
| Mipmap cascade | 10 | 4096→4 | < 50ms | Dispatch + allocation |
| Nested (10x10) | 100 total | 256x256 | < 200ms | Context switching |

### 7.2 Optimizaciones Clave

1. **Shader Caching** (CRÍTICO):
   - Hash de (ops_sequence + resource_formats + dispatch_size)
   - Reuse compiled shaders entre iteraciones

2. **Batch Barriers**:
   - En vez de barrier per-iteration: batch cada N iterations
   - Trade-off: latency vs throughput

3. **Lazy Texture Allocation**:
   - Allocate solo sizes que efectivamente se usan
   - Track usage pattern primeras M iterations → optimize resto

4. **GPU Profiling Integration**:
   - `gpu.types.GPUTimerQuery` para medir cada pass
   - Mostrar breakdown por node en UI

---

## 8. Plan de Implementación — Fases

### Phase 1: Cleanup & Foundation (Week 1)
- [ ] Refactor `StateVar` → first-class type system
- [ ] Extract loop execution → `LoopExecutor` class
- [ ] Implement `ManagedTexturePool` con lifecycle
- [ ] Add shader caching layer
- [ ] Fix initialization copy (ALWAYS copy iter 0)

### Phase 2: Multi-Resolution (Week 2)
- [ ] Expression evaluator para size expressions
- [ ] Pre-allocation strategy para size cascades
- [ ] Dynamic pool release en loop end
- [ ] Test: Erosio Demo con 1000 iterations

### Phase 3: Single-Pass Optimization (Week 3)
- [ ] Implement `is_simple` analysis en scheduler
- [ ] GLSL loop template generator
- [ ] Codegen para single-pass loops
- [ ] Benchmark: Simple cases 10x faster vs multi-pass

### Phase 4: Nested Loops (Week 4)
- [ ] Stack-based execution context
- [ ] Uniform arrays para nested iteration indices
- [ ] Test: 10x10 nested erosion

### Phase 5: Extensibility (Week 5)
- [ ] Generic StateVar type handlers
- [ ] Float/Int scalar states (SSBO-based)
- [ ] Field serialization (stretch goal)
- [ ] Documentation para adding new types

---

## 9. Riesgos & Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|-----------|
| Single-pass no funciona para casos reales | Alta | Medio | Keep multi-pass como fallback robusto |
| Nested loops causan stack overflow GPU | Media | Alto | Limit depth=4, fail gracefully |
| Dynamic pool memory leak | Media | Alto | Mandatory release() + pool stats monitoring |
| Shader compilation time > execution time | Baja | Medio | Aggressive caching + async compilation |
| Expression evaluator bugs | Alta | Medio | Extensive unit tests + fallback to callback |

---

## 10. Preguntas Abiertas para Discusión

1. **¿Debemos eliminar soporte para Float/Vector/Color states?**
   - Actualmente NO funcionan
   - Mantenerlos implica SSBO complexity
   - Alternativa: "Use Capture para convertir scalar → Grid 1x1"

2. **¿Límite de iteraciones?**
   - Max recomendado: 10,000?
   - UI warning si >1000?

3. **¿Exponer buffers intermedios para debug?**
   - Opción "Save Iteration N" → Blender Image
   - Overhead de readback

4. **¿Soporte para data-dependent iteration count?**
   - Ejemplo: "Loop until convergence"
   - Requiere GPU→CPU readback por iteración (slow)

5. **¿Backwards compatibility?**
   - Graphs existentes: Mantener multi-pass behavior
   - Opt-in flag para single-pass optimization

---

## 11. Conclusiones

**Lo que funciona bien:**
- ✅ UX de paired nodes con drag-to-add
- ✅ Ping-pong buffering básico
- ✅ Dynamic texture pooling concept

**Lo que necesita rediseño fundamental:**
- ❌ Multi-pass overhead para loops simples
- ❌ Texture allocation/deallocation lifecycle
- ❌ Expression evaluation para dynamic sizes
- ❌ Nested loop execution stack

**Estrategia recomendada:**
1. **Short-term** (1-2 semanas):
   - Fix critical bugs (initialization copy, pool leaks)
   - Add shader caching
   - Improve error messages

2. **Mid-term** (1 mes):
   - Implement single-pass optimization para casos simples
   - Robust multi-resolution support
   - Nested loop stack

3. **Long-term** (3 meses):
   - Extensible type system
   - Field state serialization
   - BREAK/CONTINUE support

**El objetivo es hacer de Repeat Zones una pieza SÓLIDA y CONFIABLE, no solo funcional.**
