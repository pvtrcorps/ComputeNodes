# Compute Nodes — Design & Architecture

> **Single Source of Truth** — Updated December 2025
>
> This document defines the architecture, rules, and concepts for the Compute Nodes addon.

---

## 1. Vision

A **GPU compute node system** for Blender that lets users describe image/volume processing declaratively. The graph compiles to GLSL compute shaders and executes via Blender's `gpu` module.

**Core Principles:**
1. **Building Blocks First** — Native nodes are primitives; complex ops are Node Groups
2. **Explicit Control** — No hidden materializations, predictable behavior
3. **Compiled** — Graph → IR → GLSL → GPU execution
4. **Performant** — Minimize GPU passes and memory transfers

---

## 2. Architecture Philosophy: Building Blocks

> [!IMPORTANT]
> **Rule:** If an operation can be built from simpler nodes, it should be a **Node Group**, not a native node.

### 2.1 The Two Layers

```
┌──────────────────────────────────────────────────────────────┐
│  LAYER 1: BUILDING BLOCKS (Native Nodes)                     │
│                                                              │
│  Grid Operations:                                            │
│  • Sample(grid, uv) → Field                                  │
│  • Capture(field, w, h) → Grid                               │
│  • Resize(grid, w, h) → Grid                                 │
│  • ImageInput/Output                                         │
│  • Repeat (loops)                                            │
│                                                              │
│  Field Operations (mirror Blender Shading/GN):               │
│  • Math, VectorMath, Position                                │
│  • Noise, Voronoi, WhiteNoise                                │
│  • Mix, Switch, Clamp, MapRange                              │
│  • Separate/Combine XYZ/Color                                │
│                                                              │
│  RULE: Everything is explicit. No magic.                     │
└──────────────────────────────────────────────────────────────┘
                              ↑
                    Built from building blocks
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  LAYER 2: NODE GROUPS (High-Level Helpers)                   │
│                                                              │
│  • Gradient = Sample(x±1) + Math                             │
│  • Blur = Sample(neighbors) + weighted sum                   │
│  • Divergence, Curl = Sample + Math                          │
│  • Edge Detection, Sharpen, etc.                             │
│                                                              │
│  These are NOT native nodes. Users can:                      │
│  • Use them as-is                                            │
│  • Open and modify them                                      │
│  • Create their own                                          │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Why This Matters

| Approach | Pro | Con |
|----------|-----|-----|
| Many native high-level nodes | Easy for beginners | Black boxes, less control |
| **Building blocks + Node Groups** | Full transparency, extensible | Slightly more setup |

**We choose transparency over convenience.**

---

## 3. The Grid/Field Model

### 3.1 Definitions

| Concept | What it is | Socket Type | Color |
|---------|------------|-------------|-------|
| **Grid** | Materialized buffer in GPU memory (W×H×D) | `ComputeSocketGrid` | Cyan |
| **Field** | Lazy per-pixel expression | `NodeSocketFloat/Color/Vector` | Yellow/Gray/Purple |

### 3.2 The Primitives

| Node | Category | What it does |
|------|----------|--------------|
| **Sample** | Sampler | Grid → Field (read at UV) |
| **Capture** | Materializer | Field → Grid (evaluate at resolution) |
| **Resize** | Grid Op | Grid → Grid (change resolution) |
| **ImageInput** | I/O | External → Grid |
| **OutputImage** | I/O | Grid → External |
| **Repeat** | Control Flow | Iteration with state |

### 3.3 Connection Rules

| From | To | Behavior |
|------|-----|----------|
| Field | Field | ✅ Fused in one shader |
| Grid | Grid | ✅ Separate passes |
| Field | Grid input | ❌ Use Capture first |
| Grid | Field input | ⚡ Auto-Sample at UV |

---

## 4. Current Node Inventory

### 4.1 Field Nodes (Native — mirror Blender Shading/GN)

**Goal:** Implement ALL nodes from Blender's Shader Nodes and Geometry Nodes that make sense for 2D/3D grids.

| Category | Nodes |
|----------|-------|
| **Math** | `Math`, `VectorMath` |
| **Textures** | `NoiseTexture`, `WhiteNoise`, `VoronoiTexture` |
| **Color** | `Mix`, `SeparateColor`, `CombineColor` |
| **Vector** | `SeparateXYZ`, `CombineXYZ` |
| **Utility** | `Switch`, `Clamp`, `MapRange` |
| **Input** | `Position` |

### 4.2 Grid Nodes (Native — True Primitives Only)

| Node | Why it's primitive |
|------|-------------------|
| **Sample** | Fundamental: only way to read Grid data |
| **Capture** | Fundamental: only way to write Field to Grid |
| **Resize** | Changes topology (resolution) |
| **ImageInput** | External data source |
| **OutputImage** | External data sink |
| **Viewer** | Debug visualization |

### 4.3 Control Flow

| Node | Why it's primitive |
|------|-------------------|
| **Repeat Zone** | Multi-iteration execution (Grid state only) |

**Important: Repeat Zones only accept Grid state**

Due to the multi-pass GPU architecture, repeat zones can only pass Grid buffers between iterations via ping-pong buffering. Fields and scalar values cannot be serialized between separate shader programs.

```
✅ Correct Usage:
Noise → Capture → Repeat Input → Sample → Process → Capture → Repeat Output

❌ Incorrect Usage:
Noise → Repeat Input  (Field cannot pass between shader iterations)
Float → Repeat Input  (Scalar cannot pass between shader iterations)
```

**Why this limitation exists:**
- Each loop iteration runs as a **completely separate GPU shader**
- Grids use ping-pong buffers (img_0 ↔ img_1) to pass data between shaders
- Fields/scalars have no serialization mechanism between independent shaders
- This is fundamentally different from Blender's Geometry Nodes which runs in a unified CPU/GPU context

**Best Practice:** Always use Capture before Repeat Input to materialize Fields into Grids.

---

## 5. How Compilation Works

### 5.1 Pipeline

```
NodeTree (UI)
    ↓
Graph Extractor (handlers per node type)
    ↓
IR (SSA - Intermediate Representation)
    ↓
Pass Scheduler (splits by Grid boundaries)
    ↓
GLSL Codegen (emitters per opcode)
    ↓
Runtime Executor (gpu module)
```

### 5.2 Field Fusion

Multiple Field nodes compile to **one shader**:

```
[Position] → [Noise] → [Math: *2] → [Capture]
                   ↓
         ONE GLSL MAIN() — no intermediate textures
```

### 5.3 Pass Boundaries

New pass when:
1. **Capture** materializes a Field tree
2. **Sample** reads from a Grid

---

## 6. Resolution Model

| Node | Defines Resolution? |
|------|---------------------|
| **Capture** | ✅ Explicit (width, height, depth) |
| **OutputImage** | ✅ Explicit (width, height) |
| **Resize** | ✅ Explicit (changes resolution) |
| **ImageInput** | ✅ From source image |
| **Sample, Math, etc.** | ❌ No (context-dependent) |

---

## 7. Future Work

### 7.1 Grid Primitives (Multi-Pass Required)
- [ ] **Mipmap** — Generate LOD chain
- [ ] **Reduce** — Max/Min/Sum to scalar
- [ ] **Histogram** — Distribution to 1D buffer
- [ ] **FFT** — Frequency domain transform

### 7.2 Node Groups to Ship
- [ ] Gradient, Divergence, Curl
- [ ] Blur (Gaussian, Box)
- [ ] Edge Detection (Sobel, Laplacian)
- [ ] Distort/Displace

### 7.3 Infrastructure
- [ ] **Node Group support** — Load/save, nested evaluation
- [ ] **3D Volume I/O** — OpenVDB export
- [ ] **Mesh Bridges** — Geometry ↔ Grid

---

## 8. Deprecated

These files are historical only:
- `hoja_de_diseño_compute_nodes.md`
- `Actual State.md`

All authoritative information is in this file (GEMINI.md).
