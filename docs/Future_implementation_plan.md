# 🛠️ Compute Nodes Refactoring Plan

> **Para desarrolladores de todos los niveles**
> 
> Plan detallado para transformar el addon en un sistema robusto y preparado para el futuro.

---

## 📋 Tabla de Contenidos

1. [Visión y Objetivos](#visión-y-objetivos)
2. [Estado Actual vs Deseado](#estado-actual-vs-deseado)
3. [Fase 1: Tests e Infraestructura](#fase-1-tests-e-infraestructura-semana-1-2)
4. [Fase 2: Executor Decomposition](#fase-2-descomponer-executor-semana-2-3)
5. [Fase 3: Loop Consolidation](#fase-3-consolidar-loops-semana-3-4)
6. [Fase 4: Scheduler Refactor](#fase-4-refactorizar-scheduler-semana-4-5)
7. [Fase 5: Code Quality](#fase-5-calidad-de-código-semana-5-6)
8. [Fase 6: Future-Proofing](#fase-6-preparar-para-el-futuro-semana-6-8)
9. [Análisis de Compatibilidad con Features Futuras](#análisis-de-compatibilidad-futura)

---

## Visión y Objetivos

### ¿Por qué refactorizar?

| Problema Actual | Impacto | Solución |
|-----------------|---------|----------|
| [executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) tiene 458 líneas | Difícil de entender/modificar | Dividir en módulos pequeños |
| Lógica de loops dispersa en 6 archivos | Cambios requieren tocar muchos archivos | Consolidar en un módulo |
| Sin tests automatizados | Bugs al modificar | Suite de tests |
| Mix de `print()` y `logger` | Output inconsistente | Logging estándar |

### Métricas de Éxito

✅ **Ningún archivo > 300 líneas**  
✅ **Test coverage > 80% en runtime/**  
✅ **Cada clase = 1 responsabilidad**  
✅ **Type hints en todas las funciones públicas**  
✅ **Zero `print()` en producción**

---

## Estado Actual vs Deseado

### Estructura de Archivos Actual

```
compute_nodes/
├── runtime/
│   ├── executor.py         ← 458 líneas, hace TODO
│   ├── resource_resolver.py
│   ├── scalar_evaluator.py
│   └── ...
├── planner/
│   ├── scheduler.py        ← 336 líneas, 5 fases inline
│   ├── loops.py            ← 340 líneas
│   └── ...
└── graph_extract/
    └── handlers/
        └── repeat.py       ← Más lógica de loops
```

### Estructura Después de Refactorizar

```
compute_nodes/
├── runtime/
│   ├── executor.py         ← ~100 líneas, solo orquestación
│   ├── pass_runner.py      ← NUEVO: ejecuta un pass
│   ├── loop_executor.py    ← NUEVO: ejecuta loops
│   ├── binding_manager.py  ← NUEVO: bindings de GPU
│   └── ...
├── planner/
│   ├── scheduler.py        ← Refactored: clase con métodos por fase
│   └── ...
├── loops/                   ← NUEVO: módulo unificado
│   ├── planning.py
│   ├── execution.py
│   ├── buffers.py
│   └── ...
└── tests/                   ← NUEVO: tests automatizados
    ├── test_scheduler.py
    ├── test_loops.py
    └── ...
```

---

## Fase 1: Tests e Infraestructura (Semana 1-2)

### 1.1 ¿Por qué tests primero?

> ⚠️ **REGLA DE ORO:** Nunca refactorizar sin tests que verifiquen el comportamiento actual.

Los tests capturan "cómo funciona ahora" antes de cambiar nada. Si un test falla después del refactor, sabemos que rompimos algo.

### 1.2 Crear estructura de tests

**Paso a paso:**

```bash
# 1. Crear directorio de tests
mkdir tests
cd tests

# 2. Crear archivos base
touch __init__.py
touch conftest.py
touch test_scheduler.py
touch test_executor.py
touch test_loops.py
```

### 1.3 Archivo conftest.py (Fixtures de Pytest)

```python
# tests/conftest.py
"""
Fixtures compartidas para tests de Compute Nodes.

¿Qué es un fixture?
Un fixture es código que se ejecuta ANTES de cada test para preparar
el entorno. Por ejemplo, crear un grafo de prueba.
"""

import pytest
import bpy
from compute_nodes.ir.graph import Graph, Op
from compute_nodes.ir.ops import OpCode
from compute_nodes.ir.resources import ImageDesc


@pytest.fixture
def empty_graph():
    """
    Crea un grafo vacío para tests.
    
    Uso en test:
        def test_algo(empty_graph):
            empty_graph.add_op(...)
    """
    return Graph()


@pytest.fixture
def simple_capture_graph():
    """
    Crea un grafo con: Position → Capture → Output
    
    Este es el caso más simple: un field que se materializa.
    """
    graph = Graph()
    
    # Recurso de salida
    output = ImageDesc(
        name="Output",
        size=(512, 512),
        format='RGBA32F',
        access='WRITE'
    )
    graph.resources.append(output)
    
    # TODO: Añadir ops
    return graph


@pytest.fixture
def loop_graph():
    """
    Crea un grafo con un Repeat Zone de 3 iteraciones.
    
    Útil para tests de loops.
    """
    # TODO: Implementar
    pass
```

### 1.4 Test de Scheduler (Ejemplo Completo)

```python
# tests/test_scheduler.py
"""
Tests para el scheduler de passes.

¿Qué testear?
1. Que las operaciones se dividan correctamente en passes
2. Que los hazards (leer después de escribir) creen nuevos passes
3. Que el splitting por tamaño funcione
"""

import pytest
from compute_nodes.planner.scheduler import schedule_passes
from compute_nodes.ir.graph import Graph
from compute_nodes.ir.ops import OpCode


def test_empty_graph_returns_empty_passes():
    """Un grafo vacío debería retornar 0 passes."""
    graph = Graph()
    passes = schedule_passes(graph)
    assert len(passes) == 0


def test_single_capture_creates_one_pass(simple_capture_graph):
    """Un Capture simple debería crear exactamente 1 pass."""
    passes = schedule_passes(simple_capture_graph)
    assert len(passes) == 1


def test_read_after_write_creates_new_pass():
    """
    Si un op lee un recurso que otro op escribió,
    deben estar en passes diferentes.
    
    Ejemplo:
    - Pass 1: Capture escribe a textura A
    - Pass 2: Sample lee de textura A
    """
    # TODO: Implementar
    pass


def test_different_output_sizes_split_passes():
    """
    Cuando un pass escribe a texturas de diferentes tamaños,
    debe dividirse en múltiples passes.
    
    Esto evita problemas de dispatch_size.
    """
    # TODO: Implementar
    pass
```

### 1.5 Ejecutar Tests

```bash
# Desde el directorio del addon
cd "c:\Users\anton\Desktop\addon\addons\Compute Nodes"

# Ejecutar todos los tests
python -m pytest tests/ -v

# Ejecutar solo tests de scheduler
python -m pytest tests/test_scheduler.py -v

# Con coverage (ver qué código se ejecuta)
python -m pytest tests/ --cov=compute_nodes --cov-report=html
```

---

## Fase 2: Descomponer Executor (Semana 2-3)

### 2.1 Problema Actual

[executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) tiene **7 responsabilidades**:

| Responsabilidad | Líneas | Debería estar en |
|-----------------|--------|------------------|
| Orquestación general | 20 | [executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) |
| Compilar shaders | 30 | `pass_runner.py` |
| Bind texturas/uniforms | 50 | `binding_manager.py` |
| Calcular dispatch | 40 | `pass_runner.py` |
| Ejecutar dispatch | 20 | `pass_runner.py` |
| Loop iteration | 150 | `loop_executor.py` |
| Ping-pong buffers | 80 | `loop_executor.py` |

### 2.2 Crear PassRunner (Paso a Paso)

**Archivo:** `runtime/pass_runner.py`

```python
"""
PassRunner - Ejecuta un único ComputePass.

¿Qué es un ComputePass?
Un ComputePass representa una llamada a shader. Contiene:
- Los ops (operaciones) a ejecutar
- Qué recursos lee (reads_idx)
- Qué recursos escribe (writes_idx)
- El código GLSL generado

¿Qué hace PassRunner?
1. Compila el shader (si no está cacheado)
2. Bind texturas y uniforms
3. Calcula el tamaño del dispatch
4. Ejecuta el compute dispatch
5. Inserta memory barrier
"""

import logging
import math
import gpu

from ..planner.passes import ComputePass
from .shaders import ShaderManager
from .gpu_ops import GPUOps

logger = logging.getLogger(__name__)


class PassRunner:
    """
    Ejecuta un único compute pass.
    
    Attributes:
        shader_mgr: Gestor de shaders (cache, compilación)
        gpu_ops: Operaciones GPU de bajo nivel
    
    Example:
        runner = PassRunner(shader_mgr, gpu_ops)
        runner.run(graph, pass_, texture_map, context)
    """
    
    def __init__(self, shader_mgr: ShaderManager, gpu_ops: GPUOps):
        self.shader_mgr = shader_mgr
        self.gpu_ops = gpu_ops
        
        # Contexto del loop (para uniforms u_loop_iteration, etc.)
        self._loop_context = {
            'iteration': 0,
            'read_width': 0,
            'read_height': 0,
            'write_width': 0,
            'write_height': 0,
        }
    
    def set_loop_context(self, **kwargs):
        """
        Actualiza el contexto del loop.
        
        Llamado por LoopExecutor antes de cada dispatch.
        """
        self._loop_context.update(kwargs)
    
    def run(
        self, 
        graph, 
        compute_pass: ComputePass, 
        texture_map: dict, 
        context_width: int,
        context_height: int
    ) -> None:
        """
        Ejecuta un compute pass.
        
        Args:
            graph: El grafo IR completo
            compute_pass: El pass a ejecutar
            texture_map: Mapping idx -> GPUTexture
            context_width: Ancho por defecto si el pass no tiene tamaño
            context_height: Alto por defecto
        """
        # 1. COMPILAR SHADER
        shader = self._compile_shader(graph, compute_pass)
        if not shader:
            logger.error(f"Failed to compile pass {compute_pass.id}")
            return
        
        # 2. BIND TEXTURAS
        self._bind_textures(shader, graph, compute_pass, texture_map)
        
        # 3. CALCULAR DISPATCH SIZE
        dispatch_w, dispatch_h, dispatch_d = self._calculate_dispatch(
            compute_pass, texture_map, context_width, context_height
        )
        
        # 4. SET UNIFORMS
        self._set_uniforms(shader, dispatch_w, dispatch_h, dispatch_d)
        
        # 5. DISPATCH
        self._dispatch(shader, dispatch_w, dispatch_h, dispatch_d)
        
        # 6. MEMORY BARRIER
        self.gpu_ops.memory_barrier()
        
        logger.debug(f"Pass {compute_pass.id} completed: {dispatch_w}x{dispatch_h}")
    
    def _compile_shader(self, graph, compute_pass: ComputePass):
        """Compila o recupera shader del cache."""
        # Generar source si no existe
        src = compute_pass.display_source or compute_pass.source
        if not src:
            from ..codegen.glsl import ShaderGenerator
            generator = ShaderGenerator(graph)
            src = generator.generate(compute_pass)
            compute_pass.source = src
        
        # Compilar
        return self.shader_mgr.get_or_create(src, compute_pass)
    
    def _bind_textures(self, shader, graph, compute_pass, texture_map):
        """
        Bind texturas a slots del shader.
        
        Los samplers (READ) van a img_0, img_1, ...
        Las imágenes (WRITE) también, pero como image2D.
        """
        binding_map = {}
        slot = 0
        
        # Primero reads (samplers)
        for res_idx in sorted(compute_pass.reads_idx):
            if res_idx not in compute_pass.writes_idx:
                binding_map[res_idx] = slot
                slot += 1
        
        # Luego writes (images)
        for res_idx in sorted(compute_pass.writes_idx):
            binding_map[res_idx] = slot
            slot += 1
        
        # Bind cada uno
        for res_idx, bind_slot in binding_map.items():
            if res_idx in texture_map:
                tex = texture_map[res_idx]
                uniform_name = f"img_{bind_slot}"
                
                res = graph.resources[res_idx]
                is_write = res_idx in compute_pass.writes_idx
                
                try:
                    if is_write:
                        shader.image(uniform_name, tex)
                    else:
                        shader.sampler(uniform_name, tex)
                except Exception as e:
                    logger.error(f"Failed to bind {uniform_name}: {e}")
    
    def _calculate_dispatch(self, compute_pass, texture_map, ctx_w, ctx_h):
        """
        Calcula dimensiones del dispatch.
        
        Regla: El dispatch size es el MÁXIMO de las texturas de ESCRITURA.
        """
        dispatch_w, dispatch_h, dispatch_d = compute_pass.dispatch_size
        
        if dispatch_w == 0:
            dispatch_w = ctx_w
        if dispatch_h == 0:
            dispatch_h = ctx_h
        if dispatch_d == 0:
            dispatch_d = 1
        
        # Override con tamaño real de texturas de write
        for idx in compute_pass.writes_idx:
            if idx in texture_map:
                tex = texture_map[idx]
                dispatch_w = max(dispatch_w, tex.width)
                dispatch_h = max(dispatch_h, tex.height)
        
        return dispatch_w, dispatch_h, dispatch_d
    
    def _set_uniforms(self, shader, w, h, d):
        """Set uniforms estándar del shader."""
        try:
            shader.uniform_int("u_dispatch_width", w)
            shader.uniform_int("u_dispatch_height", h)
            shader.uniform_int("u_dispatch_depth", d)
            
            # Loop context
            shader.uniform_int("u_loop_iteration", self._loop_context['iteration'])
            shader.uniform_int("u_loop_read_width", self._loop_context['read_width'])
            shader.uniform_int("u_loop_read_height", self._loop_context['read_height'])
            shader.uniform_int("u_loop_write_width", self._loop_context['write_width'])
            shader.uniform_int("u_loop_write_height", self._loop_context['write_height'])
        except Exception as e:
            logger.debug(f"Could not set uniform: {e}")
    
    def _dispatch(self, shader, w, h, d):
        """Ejecuta el compute dispatch."""
        # Workgroup size
        if d > 1:
            local_x, local_y, local_z = 8, 8, 8
        else:
            local_x, local_y, local_z = 16, 16, 1
        
        group_x = math.ceil(w / local_x)
        group_y = math.ceil(h / local_y)
        group_z = math.ceil(d / local_z)
        
        try:
            gpu.compute.dispatch(shader, group_x, group_y, group_z)
        except Exception as e:
            logger.error(f"Dispatch failed: {e}")
```

### 2.3 Crear LoopExecutor (Paso a Paso)

**Archivo:** `runtime/loop_executor.py`

```python
"""
LoopExecutor - Ejecuta Repeat Zones con ping-pong buffering.

¿Qué es ping-pong buffering?
Cuando un shader lee Y escribe al mismo recurso, hay un problema:
¿Qué valor lee? ¿El viejo o el nuevo?

Solución: Usar DOS buffers y alternarlos:
- Iteración 0: Lee de PING, escribe a PONG
- Iteración 1: Lee de PONG, escribe a PING
- Iteración 2: Lee de PING, escribe a PONG
- ...

¿Qué hace LoopExecutor?
1. Prepara buffers ping-pong para cada estado del loop
2. Ejecuta N iteraciones, alternando buffers
3. Evalúa tamaños dinámicos al inicio de cada iteración
4. Al final, asegura que los outputs tengan el tamaño correcto
"""

import logging
from typing import Dict, Any

from ..planner.loops import PassLoop
from ..ir.state import StateVar
from .pass_runner import PassRunner
from .resource_resolver import ResourceResolver
from .scalar_evaluator import ScalarEvaluator

logger = logging.getLogger(__name__)


class LoopExecutor:
    """
    Ejecuta loops con ping-pong buffering automático.
    
    Example:
        loop_exec = LoopExecutor(pass_runner, resolver)
        loop_exec.execute(graph, loop, texture_map, 512, 512)
    """
    
    def __init__(self, pass_runner: PassRunner, resolver: ResourceResolver):
        self.pass_runner = pass_runner
        self.resolver = resolver
        self.evaluator = ScalarEvaluator()
    
    def execute(
        self,
        graph,
        loop: PassLoop,
        texture_map: dict,
        context_width: int,
        context_height: int
    ) -> None:
        """
        Ejecuta un loop completo.
        
        Args:
            graph: Grafo IR
            loop: El PassLoop a ejecutar
            texture_map: Mapping de texturas
            context_width/height: Tamaño por defecto
        """
        iterations = self._resolve_iterations(loop)
        logger.info(f"Executing loop: {iterations} iterations")
        
        # 1. PREPARAR PING-PONG BUFFERS
        ping_pong = self._setup_ping_pong(graph, loop, texture_map, context_width, context_height)
        dynamic_resources = self._find_dynamic_resources(graph)
        
        # 2. COPIAR DATOS INICIALES
        self._copy_initial_data(loop, texture_map, ping_pong)
        
        # 3. EJECUTAR ITERACIONES
        for i in range(iterations):
            self._execute_iteration(
                graph, loop, i, texture_map, ping_pong,
                dynamic_resources, context_width, context_height
            )
        
        # 4. FINALIZAR (asignar buffers finales, resize outputs)
        self._finalize(graph, loop, iterations, texture_map, ping_pong)
        
        logger.info(f"Loop completed: {iterations} iterations")
    
    def _resolve_iterations(self, loop: PassLoop) -> int:
        """Resuelve el número de iteraciones (puede ser Value o int)."""
        raw = loop.iterations
        if hasattr(raw, 'evaluate'):
            return int(raw.evaluate())
        return int(raw)
    
    def _setup_ping_pong(self, graph, loop, texture_map, ctx_w, ctx_h):
        """
        Crea buffers ping-pong para cada estado del loop.
        
        Returns:
            Dict mapping state name -> {
                'ping': texture, 'pong': texture,
                'ping_idx': int, 'pong_idx': int,
                'state': StateVar
            }
        """
        ping_pong = {}
        
        for state in loop.state_vars:
            # Obtener recursos
            ping_idx = state.ping_idx
            pong_idx = state.pong_idx
            
            ping_tex = texture_map.get(ping_idx)
            pong_tex = texture_map.get(pong_idx)
            
            # Si no existen, crearlos
            if not ping_tex:
                ping_tex = self.resolver.dynamic_pool.get_or_create(
                    (ctx_w, ctx_h), 'RGBA32F', 2
                )
                texture_map[ping_idx] = ping_tex
            
            if not pong_tex:
                pong_tex = self.resolver.dynamic_pool.get_or_create(
                    (ctx_w, ctx_h), 'RGBA32F', 2
                )
                texture_map[pong_idx] = pong_tex
            
            ping_pong[state.name] = {
                'ping': ping_tex,
                'pong': pong_tex,
                'ping_idx': ping_idx,
                'pong_idx': pong_idx,
                'state': state,
            }
        
        return ping_pong
    
    def _find_dynamic_resources(self, graph) -> Dict[int, Any]:
        """Encuentra recursos con tamaño dinámico."""
        dynamic = {}
        for idx, res in enumerate(graph.resources):
            if getattr(res, 'dynamic_size', False):
                dynamic[idx] = res
        return dynamic
    
    def _copy_initial_data(self, loop, texture_map, ping_pong):
        """Copia datos de input al buffer ping para iteración 0."""
        for state in loop.state_vars:
            copy_from = getattr(state, 'copy_from_resource', None)
            if copy_from is not None and copy_from in texture_map:
                src = texture_map[copy_from]
                dst = ping_pong[state.name]['ping']
                
                # TODO: Implementar copia GPU
                # self.gpu_ops.copy_texture(src, dst)
    
    def _execute_iteration(
        self, graph, loop, iter_idx, texture_map, ping_pong,
        dynamic_resources, ctx_w, ctx_h
    ):
        """Ejecuta una iteración del loop."""
        
        # 1. EVALUAR TAMAÑOS DINÁMICOS
        self._evaluate_dynamic_sizes(
            graph, iter_idx, texture_map, dynamic_resources, ctx_w, ctx_h
        )
        
        # 2. SWAP PING-PONG
        read_idx, write_idx = self._swap_buffers(iter_idx, ping_pong, texture_map)
        
        # 3. ACTUALIZAR CONTEXTO DEL LOOP
        read_tex = texture_map[read_idx]
        write_tex = texture_map[write_idx]
        
        self.pass_runner.set_loop_context(
            iteration=iter_idx,
            read_width=read_tex.width,
            read_height=read_tex.height,
            write_width=write_tex.width,
            write_height=write_tex.height,
        )
        
        # 4. EJECUTAR BODY PASSES
        for body_pass in loop.body_passes:
            if hasattr(body_pass, 'body_passes'):
                # Loop anidado (futuro)
                raise NotImplementedError("Nested loops not yet supported")
            else:
                self.pass_runner.run(
                    graph, body_pass, texture_map, ctx_w, ctx_h
                )
    
    def _evaluate_dynamic_sizes(self, graph, iter_idx, texture_map, dynamic_resources, ctx_w, ctx_h):
        """Evalúa y aplica tamaños dinámicos para esta iteración."""
        context = {
            'iteration': iter_idx + 1,  # 1-indexed
        }
        
        for res_idx, res_desc in dynamic_resources.items():
            size_expr = getattr(res_desc, 'size_expression', None)
            if not size_expr:
                continue
            
            # Evaluar expresión
            new_w = self.evaluator.evaluate(size_expr.get('width'), context)
            new_h = self.evaluator.evaluate(size_expr.get('height'), context)
            new_size = (int(new_w), int(new_h))
            
            # Obtener tamaño actual
            current_tex = texture_map.get(res_idx)
            current_size = (current_tex.width, current_tex.height) if current_tex else (0, 0)
            
            # Resize si cambió
            if new_size != current_size:
                new_tex = self.resolver.dynamic_pool.get_or_create(
                    new_size, 'RGBA32F', 2
                )
                texture_map[res_idx] = new_tex
                logger.debug(f"Dynamic resize: {res_desc.name} {current_size} -> {new_size}")
    
    def _swap_buffers(self, iter_idx, ping_pong, texture_map):
        """
        Swap ping-pong buffers para esta iteración.
        
        Returns:
            (read_idx, write_idx) para el primer estado
        """
        first_read = None
        first_write = None
        
        for state_name, buf_info in ping_pong.items():
            if iter_idx % 2 == 0:
                read_tex = buf_info['ping']
                write_tex = buf_info['pong']
                read_idx = buf_info['ping_idx']
                write_idx = buf_info['pong_idx']
            else:
                read_tex = buf_info['pong']
                write_tex = buf_info['ping']
                read_idx = buf_info['pong_idx']
                write_idx = buf_info['ping_idx']
            
            texture_map[read_idx] = read_tex
            texture_map[write_idx] = write_tex
            
            if first_read is None:
                first_read = read_idx
                first_write = write_idx
        
        return first_read, first_write
    
    def _finalize(self, graph, loop, iterations, texture_map, ping_pong):
        """
        Finaliza el loop:
        1. Asigna buffer final a ping y pong
        2. Resize outputs para que coincidan con el estado
        """
        pong_to_size = {}
        
        for buf_info in ping_pong.values():
            state = buf_info['state']
            
            # Determinar buffer final
            copy_from = getattr(state, 'copy_from_resource', None)
            if copy_from is not None and copy_from in texture_map:
                final_buf = texture_map[copy_from]
            else:
                if iterations % 2 == 1:
                    final_buf = buf_info['pong']
                else:
                    final_buf = buf_info['ping']
            
            # Actualizar texture_map
            texture_map[buf_info['ping_idx']] = final_buf
            texture_map[buf_info['pong_idx']] = final_buf
            pong_to_size[buf_info['pong_idx']] = (final_buf.width, final_buf.height)
        
        # Resize outputs
        self._resize_outputs(graph, texture_map, pong_to_size)
    
    def _resize_outputs(self, graph, texture_map, pong_to_size):
        """Resize outputs para que coincidan con sus estados."""
        pong_indices = sorted(pong_to_size.keys())
        output_indices = sorted([
            idx for idx, res in enumerate(graph.resources)
            if hasattr(res, 'is_internal') and not res.is_internal
        ])
        
        for pong_idx, output_idx in zip(pong_indices, output_indices):
            pong_size = pong_to_size[pong_idx]
            if output_idx in texture_map:
                current = texture_map[output_idx]
                if (current.width, current.height) != pong_size:
                    new_tex = self.resolver.dynamic_pool.get_or_create(
                        pong_size, 'RGBA32F', 2
                    )
                    texture_map[output_idx] = new_tex
                    logger.debug(f"Resized output[{output_idx}] to {pong_size}")
```

### 2.4 Executor Simplificado

Después de extraer PassRunner y LoopExecutor, [executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) queda así:

```python
"""
ComputeExecutor - Orquesta la ejecución de grafos.

Ahora es simple: solo conecta las piezas.
"""

import logging
from .pass_runner import PassRunner
from .loop_executor import LoopExecutor
from .textures import TextureManager
from .shaders import ShaderManager
from .resource_resolver import ResourceResolver
from .gpu_ops import GPUOps
from ..planner.loops import PassLoop

logger = logging.getLogger(__name__)


class ComputeExecutor:
    """Orquesta la ejecución de un compute graph."""
    
    def __init__(self, texture_mgr: TextureManager, shader_mgr: ShaderManager):
        self.texture_mgr = texture_mgr
        self.shader_mgr = shader_mgr
        self.gpu_ops = GPUOps()
        self.resolver = ResourceResolver(texture_mgr)
        
        self.pass_runner = PassRunner(shader_mgr, self.gpu_ops)
        self.loop_executor = LoopExecutor(self.pass_runner, self.resolver)
    
    def execute_graph(self, graph, passes, context_width=512, context_height=512):
        """Ejecuta el grafo completo."""
        
        # 1. Resolver recursos a texturas GPU
        texture_map = self.resolver.resolve_resources(graph, context_width, context_height)
        
        # 2. Ejecutar passes
        for item in passes:
            if isinstance(item, PassLoop) or hasattr(item, 'body_passes'):
                self.loop_executor.execute(
                    graph, item, texture_map, context_width, context_height
                )
            else:
                self.pass_runner.run(
                    graph, item, texture_map, context_width, context_height
                )
        
        # 3. Readback resultados
        self.resolver.readback_results(graph, texture_map)
        
        # 4. Cleanup
        self.resolver.cleanup()
        
        logger.debug("Graph execution completed")
```

**Resultado:** De 458 líneas → ~60 líneas ✅

---

## Fase 3: Consolidar Loops (Semana 3-4)

### 3.1 Problema Actual

La lógica de loops está dispersa en **6 archivos**:

| Archivo | Responsabilidad |
|---------|-----------------|
| [graph_extract/handlers/repeat.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/graph_extract/handlers/repeat.py) | Extraer nodos de loop |
| [planner/loops.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py) | Estructura PassLoop, wrap_passes |
| [planner/scheduler.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/scheduler.py) | Detectar regiones de loop |
| [runtime/executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) | Ejecutar loops |
| [runtime/state_manager.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/state_manager.py) | Tracking de estados |
| `ir/state.py` | Definición de StateVar |

### 3.2 Crear Módulo Unificado

```
compute_nodes/
└── loops/
    ├── __init__.py
    ├── types.py         # StateVar, LoopConfig
    ├── planning.py      # PassLoop, wrap_passes_in_loops
    ├── extraction.py    # Handlers de graph extraction
    ├── execution.py     # LoopExecutor (de fase 2)
    ├── buffers.py       # PingPongManager
    └── tests/
        └── test_loops.py
```

### 3.3 Beneficios

- ✅ Todo lo de loops en un lugar
- ✅ Imports claros: `from compute_nodes.loops import PassLoop, LoopExecutor`
- ✅ Fácil de navegar para nuevos desarrolladores
- ✅ Tests cohesivos

---

## Fase 4: Refactorizar Scheduler (Semana 4-5)

### 4.1 Problema Actual

[schedule_passes()](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/scheduler.py#43-162) tiene 161 líneas con 5 fases inline:

```python
def schedule_passes(graph):
    # Phase 1: 40 líneas
    # Phase 2: 30 líneas
    # Phase 2.5: 20 líneas
    # Phase 4: 20 líneas
    # Phase 5: 10 líneas
    return passes
```

### 4.2 Refactorizar a Clase

```python
class PassScheduler:
    """
    Scheduler basado en fases.
    
    Cada fase es un método separado, fácil de:
    - Entender individualmente
    - Testear en aislamiento
    - Extender
    """
    
    def __init__(self, graph: Graph):
        self.graph = graph
    
    def schedule(self) -> List[Pass]:
        """Ejecuta todas las fases en orden."""
        ops = self._phase1_topological_sort()
        passes = self._phase2_initial_partition(ops)
        passes = self._phase3_propagate_field_deps(passes)
        passes = self._phase4_recalculate_resources(passes)
        passes = self._phase5_wrap_loops(passes, ops)
        passes = self._phase6_split_by_size(passes)
        return passes
    
    def _phase1_topological_sort(self) -> List[Op]:
        """Ordena operaciones respetando dependencias."""
        ...
    
    def _phase2_initial_partition(self, ops) -> List[ComputePass]:
        """Divide ops en passes por hazards y límites de recursos."""
        ...
    
    # etc.
```

---

## Fase 5: Calidad de Código (Semana 5-6)

### 5.1 Type Hints Completas

```python
# ❌ Antes
def resolve_resources(self, graph, context_width, context_height):
    pass

# ✅ Después
def resolve_resources(
    self, 
    graph: Graph, 
    context_width: int, 
    context_height: int
) -> Dict[int, gpu.types.GPUTexture]:
    """
    Resuelve recursos del grafo a texturas GPU.
    
    Args:
        graph: El grafo IR con recursos definidos
        context_width: Ancho por defecto para recursos sin tamaño
        context_height: Alto por defecto
        
    Returns:
        Diccionario mapping índice de recurso -> textura GPU
        
    Raises:
        ResourceAllocationError: Si no se puede allocar textura
    """
    pass
```

### 5.2 Excepciones Personalizadas

```python
# errors.py

class ComputeNodeError(Exception):
    """Base para todas las excepciones de Compute Nodes."""
    pass


class ShaderCompileError(ComputeNodeError):
    """El shader no compiló."""
    
    def __init__(self, source: str, error: str):
        self.source = source
        self.error = error
        super().__init__(f"Shader compile failed: {error}")


class ResourceAllocationError(ComputeNodeError):
    """No se pudo allocar recurso GPU."""
    pass


class LoopExecutionError(ComputeNodeError):
    """Error durante ejecución de loop."""
    pass
```

### 5.3 Logging Consistente

```python
# ❌ Antes (inconsistente)
print(f"[DEBUG] Executing pass {pass_id}")
logger.info("Starting execution")

# ✅ Después
logger.debug(f"Executing pass {pass_id}")  # Solo desarrollo
logger.info("Starting execution")           # Usuario quiere ver
logger.warning("Texture pool nearly full")  # Potencial problema
logger.error("Shader compilation failed")   # Error
```

---

## Fase 6: Preparar para el Futuro (Semana 6-8)

### 6.1 Graph Cache

```python
class CompiledGraph:
    """Grafo pre-compilado listo para ejecutar."""
    passes: List[Pass]
    resources: List[ResourceDesc]
    shaders: Dict[str, str]  # source por pass ID
    

class GraphCompiler:
    """Compila y cachea grafos."""
    
    _cache: Dict[str, CompiledGraph] = {}
    
    def compile(self, tree: bpy.types.NodeTree) -> CompiledGraph:
        key = self._compute_key(tree)
        
        if key in self._cache:
            return self._cache[key]
        
        # Compilar
        graph = extract_graph(tree)
        passes = schedule_passes(graph)
        
        compiled = CompiledGraph(
            passes=passes,
            resources=graph.resources,
            shaders={}
        )
        
        self._cache[key] = compiled
        return compiled
```

### 6.2 Resource Pool Mejorado

```python
class TexturePool:
    """Pool de texturas con gestión de memoria."""
    
    def __init__(self, memory_budget_mb: int = 1024):
        self.budget = memory_budget_mb * 1024 * 1024
        self.used = 0
        self.textures: Dict[str, List[GPUTexture]] = {}
        self.lru: OrderedDict = OrderedDict()
    
    def acquire(self, size: tuple, format: str) -> GPUTexture:
        """Obtiene textura del pool o crea nueva."""
        key = f"{size}_{format}"
        
        # ¿Hay una disponible?
        if key in self.textures and self.textures[key]:
            tex = self.textures[key].pop()
            self._update_lru(tex)
            return tex
        
        # ¿Hay espacio?
        tex_size = self._calculate_size(size, format)
        if self.used + tex_size > self.budget:
            self._evict(tex_size)
        
        # Crear nueva
        tex = self._create_texture(size, format)
        self.used += tex_size
        return tex
    
    def release(self, tex: GPUTexture):
        """Devuelve textura al pool."""
        key = self._get_key(tex)
        if key not in self.textures:
            self.textures[key] = []
        self.textures[key].append(tex)
    
    def _evict(self, needed: int):
        """Libera texturas LRU hasta tener espacio."""
        while self.used + needed > self.budget and self.lru:
            oldest_key = next(iter(self.lru))
            self._free_texture(oldest_key)
```

---

## Análisis de Compatibilidad Futura

### ✅ GPU Particles

**Requisitos:**
- Buffer de posiciones (vec3 array)
- Buffer de velocidades
- Actualización iterativa

**¿El refactor lo soporta?**
- ✅ `LoopExecutor` maneja iteraciones
- ⚠️ Necesita: Soporte para **SSBO** (Shader Storage Buffer Objects)
- ⚠️ Necesita: Nuevo tipo de recurso `BufferDesc`

**Acción requerida:**
```python
# Añadir a ir/resources.py
@dataclass
class BufferDesc:
    """SSBO - array de datos arbitrarios."""
    name: str
    element_type: str  # 'vec3', 'vec4', 'float'
    element_count: int
    access: AccessMode
```

### ✅ Volumes (Grid3D)

**Requisitos:**
- Texturas 3D (image3D)
- Dispatch 3D
- Z-slice I/O

**¿El refactor lo soporta?**
- ✅ Ya existe soporte básico (`dimensions=3`)
- ✅ `PassRunner._dispatch` maneja 3D
- ✅ [sequence_exporter.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/sequence_exporter.py) escribe Z-slices

**Estado:** ✅ Compatible, ya soportado parcialmente

### ✅ Buffers (SSBO)

**Requisitos:**
- Binding como `buffer` en GLSL
- Acceso arbitrario (no solo pixel por pixel)
- Atómicos (atomic_add, etc.)

**¿El refactor lo soporta?**
- ⚠️ `PassRunner._bind_textures` solo maneja texturas
- ⚠️ Necesita: `_bind_buffers` separado
- ⚠️ Necesita: `BufferManager` análogo a [TextureManager](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/textures.py#16-160)

**Acción requerida:**
```python
# Añadir a pass_runner.py
def _bind_buffers(self, shader, graph, compute_pass, buffer_map):
    """Bind SSBOs a slots del shader."""
    for res_idx in compute_pass.buffer_reads | compute_pass.buffer_writes:
        buffer = buffer_map[res_idx]
        binding = self._get_buffer_binding(res_idx)
        shader.buffer(f"ssbo_{binding}", buffer)
```

### ✅ Mesh Bridges

**Requisitos:**
- Leer geometry attributes a Grid
- Escribir Grid a geometry attributes

**¿El refactor lo soporta?**
- ⚠️ Requiere nuevo tipo de nodo: `MeshInput`, `MeshOutput`
- ⚠️ Requiere: Transferencia CPU↔GPU de mesh data
- ✅ El pipeline IR→Pass→Execute es extensible

**Estado:** Arquitectura compatible, necesita nuevos nodos

### ✅ Node Groups (Nested Evaluation)

**Requisitos:**
- Grafos dentro de grafos
- Pasar parámetros
- Outputs múltiples

**¿El refactor lo soporta?**
- ✅ `graph_extract` puede ser recursivo
- ⚠️ `PassScheduler` necesita manejar sub-grafos
- ⚠️ UI necesita breadcrumbs (ya existe en `ui/breadcrumbs.py`)

**Estado:** Parcialmente compatible

### ✅ FFT / Histogram / Reduce

**Requisitos:**
- Operaciones multi-pass especiales
- Reducción paralela (sum, max, etc.)
- Algoritmos específicos (Cooley-Tukey)

**¿El refactor lo soporta?**
- ✅ `PassScheduler` puede insertar passes múltiples
- ⚠️ Necesita: Passes con dependencias específicas
- ⚠️ Necesita: Shaders especializados (no generados)

**Acción requerida:**
```python
# Nuevo módulo: compute_nodes/algorithms/
# algorithms/fft.py
# algorithms/reduce.py
# algorithms/histogram.py
```

---

## Resumen de Compatibilidad

| Feature | Arquitectura Compatible | Trabajo Adicional |
|---------|------------------------|-------------------|
| GPU Particles | ✅ | BufferDesc, SSBO binding |
| Volumes 3D | ✅ | Ya soportado |
| Buffers/SSBO | ⚠️ | BufferManager, bindings |
| Mesh Bridges | ✅ | Nuevos nodos |
| Node Groups | ⚠️ | Scheduling recursivo |
| FFT/Reduce | ✅ | Módulo algorithms/ |

---

## Cronograma Final

| Semana | Fase | Entregables |
|--------|------|-------------|
| 1 | Tests | `tests/` con fixtures y tests básicos |
| 2 | Tests + Executor | Tests de scheduler, inicio PassRunner |
| 3 | Executor | PassRunner y LoopExecutor completos |
| 4 | Loops | Módulo [loops/](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#77-339) consolidado |
| 5 | Scheduler | PassScheduler basado en clases |
| 6 | Quality | Type hints, excepciones, logging |
| 7 | Future | GraphCache, TexturePool mejorado |
| 8 | Polish | Documentación, GEMINI.md update |

---

## Checklist por Fase

### Fase 1
- [ ] Crear `tests/conftest.py`
- [ ] Crear `tests/test_scheduler.py` con 5+ tests
- [ ] Crear `tests/test_loops.py` con 3+ tests
- [ ] Configurar pytest en CI (si aplica)

### Fase 2
- [ ] Crear `runtime/pass_runner.py`
- [ ] Crear `runtime/loop_executor.py`
- [ ] Reducir [executor.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/executor.py) a <100 líneas
- [ ] Tests pasan después del refactor

### Fase 3
- [ ] Crear directorio [loops/](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py#77-339)
- [ ] Mover [planner/loops.py](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/loops.py) → `loops/planning.py`
- [ ] Mover loop code de executor → `loops/execution.py`
- [ ] Actualizar todos los imports

### Fase 4
- [ ] Convertir [schedule_passes](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/planner/scheduler.py#43-162) a clase `PassScheduler`
- [ ] Cada fase es un método separado
- [ ] Tests de scheduler siguen pasando

### Fase 5
- [ ] Type hints en todas las funciones públicas
- [ ] Crear `errors.py` con excepciones
- [ ] Eliminar todos los `print()`
- [ ] Logging consistente

### Fase 6
- [ ] Implementar `GraphCompiler` con cache
- [ ] Mejorar [TexturePool](file:///c:/Users/anton/Desktop/addon/addons/Compute%20Nodes/compute_nodes/runtime/textures.py#162-263) con LRU
- [ ] Actualizar GEMINI.md
- [ ] Documentar decisiones en ADR (Architecture Decision Records)
