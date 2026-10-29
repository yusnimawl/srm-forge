# EMDLAB teardown for srm-forge

Hand this file to a Claude Code session working in `D:\dev\srm-forge`. It records what the EMDLAB
package (`C:\emdlab-win64`, MATLAB + 133 MEX files) does for switched reluctance machines, why it
*looks* fast, what is inside the MEX files, and which ideas are worth porting into `srmcore` /
`srmweb`. Measurements were taken on 2026-10-30 on the same laptop as the
`bench/results/thinkpad-x1-yoga-i5` result (i5-1145G7, 4C/8T, Windows, MATLAB R2026b trial).

Every claim is tagged **[measured]**, **[observed]** (read in source or decompiled binary) or
**[inferred]**.

---

## 1. Bottom line

EMDLAB is **not faster per unknown** than srm-forge. It looks fast because it solves **far fewer
unknowns and far fewer points**:

| on the same i5-1145G7 | nodes | one static solve | notes |
|---|---|---|---|
| emdlab 8/6 example mesh | 11,130 | **1.25 s** (11 Newton it) | DistMesh, radial size function, 3 gap layers [measured] |
| emdlab 8/6, size × 0.5 | 40,044 | **4.90 s** (13 it) | [measured] |
| srm-forge 8/6 `screening` | 42,935 | **3.05 s** median, incl. mesh_at_angle + post | `bench/results/thinkpad-x1-yoga-i5` [measured by bench] |
| emdlab 8/6, size × 0.3 | 101,322 | 13.4 s (14 it) | [measured] |
| srm-forge 8/6 `full` | 81,984 | 7.34 s | bench [measured by bench] |
| emdlab 8/6, size × 0.2 | 224,296 | 38.8 s (14 it) | [measured] |

* At equal node count srm-forge is **~1.5× faster** per solve on the same machine.
* EMDLAB's examples solve **one point** and open a GUI. srm-forge builds a **360–1008 point map**
  with checks, L_inc, pole forces, HDF5 and provenance. That is a different job.
* The shipped 30-position static-torque sweep (`emdlab_examples_srm86_static_torque.m`) took
  **50.7 s ≈ 1.7 s/position** single-process, rebuilding geometry + mesh at every position [measured].
* MATLAB threading barely matters: `maxNumCompThreads(1)` gave 1.08 s vs 1.25 s at 11k nodes and
  13.43 s vs 13.41 s at 101k [measured].

### Accuracy of EMDLAB's coarse mesh (8/6, 3.6 A, θ = −15°) [measured]

| nodes | ψ (Wb-t) | Δψ vs 224k | T Arkkio (N·m) | ΔT vs 224k |
|---|---|---|---|---|
| 11,130 | 0.39981 | −0.45 % | 5.3694 | +0.17 % |
| 40,044 | 0.40123 | −0.10 % | 5.3572 | −0.06 % |
| 101,322 | 0.40152 | −0.02 % | 5.3631 | +0.05 % |
| 224,296 | 0.40162 | — | 5.3603 | — |

Compare srm-forge M5a (`docs/m5a-convergence.md`): `screening` worst ψ/W′ error is **0.46 %
against a 2 % target**, worst torque 0.64 % against 3 %. The screening preset is therefore about
4× more accurate than its own target asks for. That headroom is where EMDLAB's apparent speed comes
from. The low-current, high-saturation and corner points in the M5a study matter here; EMDLAB's
numbers above are one point at a low current.

---

## 2. What is inside the MEX files

### 2.1 Build facts [observed: PE import/export tables via REA]

* All MEX files export only `mexFunction` and `mexfilerequiredapiversion` (standard MEX ABI).
* The FE kernels import only `libmx.dll` / `libmex.dll` (`mxGetPr`, `mxGetM`, `mxGetN`,
  `mxCreateDoubleMatrix_730`, `mxIsDouble`, `mexErrMsgTxt`) and the MSVC CRT.
* **No OpenMP (`vcomp`), no Intel/LLVM OpenMP, no MKL, no BLAS, no TBB, no `CreateThread`** in any
  of the 133 files. Only `dellipse`/`dellipsoid` mention LAPACK.
* `emdlab_m2d_tl3_evalG` is 11 KB. Its whole kernel is one ~1 KB serial loop.
* `ext_dpoly2d` uses a different toolchain (MinGW-style image base `0x6db8…`) [observed].

The MEX files are plain single-threaded C element loops that replace MATLAB `for` loops. They are
equivalent to srm-forge's vectorised numpy einsums in `physics/fem.py`. **There is no hidden
solver, no reduced model and no skipped calculation inside them.**

### 2.2 Where the time actually goes (8/6, 40,044 nodes, MATLAB profiler) [measured]

```
solve() total 5.01 s
 3.126 s  62 %  13x  dU = K \ FF;                     <- MATLAB sparse direct solve (UMFPACK LU)
 0.375 s   7 %  13x  K += sparse(I,J, evalG(...))     <- MEX Jacobian term + sparse() assembly
 0.294 s   6 %  13x  K  = sparse(I,J, nu .* Ke)       <- secant stiffness assembly
 0.255 s   5 %  13x  evalTotalEnergyCoenergy          <- energy every iteration (for stopping)
 0.236 s   5 %   1x  A = K \ F                         <- initial linear solve
 0.113 s   2 %  13x  evalBe (MEX)
```

For comparison, srm-forge's M4 handoff records 0.100 s per UMFPACK factorisation at 42,935 nodes
(0.078 s with symbolic reuse). EMDLAB spends ~0.24 s per backslash at 40k nodes. EMDLAB's Dirichlet
handling replaces rows (`K(iD,:) = I`), which **breaks symmetry**, so MATLAB cannot use CHOLMOD and
falls back to LU [inferred from source + MATLAB's documented `\` dispatch].

### 2.3 Decompiled kernels as pseudocode [observed: Ghidra 12.1.4 via REA]

Index conventions: MATLAB column-major, `cl` is `[Ne×3]` 1-based, element arrays are `[k×Ne]`.

**`emdlab_m2d_tl3_evalKeMeFe(cl, p) -> Ke[9×Ne], Me[9×Ne], Fe[3×Ne], FeMx[3×Ne], FeMy[3×Ne]`**
```c
for e in 0..Ne-1:
    (x1,y1),(x2,y2),(x3,y3) = p[cl[e,:]-1]
    dx21=x2-x1; dx32=x3-x2; dx31=x3-x1    // edge vectors
    dy21=y2-y1; dy31=y3-y1; dy32=y3-y2
    A  = 0.5*(dy31*dx21 - dy21*dx31)        // signed area
    // geometric stiffness (no reluctivity): Ke_ij = (b_i b_j + c_i c_j)/(4A)
    Ke[0]=(dy32^2+dx32^2)/(4A); Ke[4]=(dy31^2+dx31^2)/(4A); Ke[8]=(dy21^2+dx21^2)/(4A)
    Ke[1]=Ke[3]=-(dy32*dy31+dx32*dx31)/(4A)
    Ke[2]=Ke[6]= (dy32*dy21+dx32*dx21)/(4A)
    Ke[5]=Ke[7]=-(dy31*dy21+dx31*dx21)/(4A)
    Me   = A/12 * [[2,1,1],[1,2,1],[1,1,2]]  // consistent P1 mass (eddy currents)
    Fe   = A/3  * [1,1,1]                     // load per unit current density
    FeMx = 0.5*[dx32, -dx31, dx21]            // magnetisation load, multiplied by Mx(e)
    FeMy = 0.5*[dy32, -dy31, dy21]            // magnetisation load, multiplied by My(e)
```
Called **once** per mesh. The reluctivity is applied later as `nu(e) .* Ke(:,e)`.

**`emdlab_m2d_tl3_evalB(cl, A, JIT) -> Bxg[1×Ne], Byg[1×Ne], Bxn[3×Ne], Byn[3×Ne]`**
```c
for e:
    a1,a2,a3 = A[cl[e,:]-1]
    J11,J21,J12,J22 = JIT[:,e]               // inverse-transpose Jacobian, 4 per element
    Bx = (a3-a1)*J22 + (a2-a1)*J12           //  dA/dy
    By = (a1-a3)*J21 + (a1-a2)*J11           // -dA/dx
    Bxg[e]=Bx; Byg[e]=By
    Bxn[:,e]=Bx; Byn[:,e]=By                 // "nodal" copy is the same constant 3 times
```

**`emdlab_m2d_tl3_evalG(cl, Ke, JIT, A, dnudB2) -> G[9×Ne]`** (Newton Jacobian extra term)
```c
for e:
    a = A[cl[e,:]-1]
    g = Ke(:,e) * a                          // 3-vector, Ke·a  (∝ ∇N·∇A·area)
    c = 2*(∂(B²)/∂a) from JIT and (a2-a1),(a3-a1)
    G(:,e)[i,j] = dnudB2[e] * c[j] * g[i]    // rank-1: 2·dν/dB²·(Ke a)(Ke a)ᵀ/area
```
This is the exact consistent tangent `ν∇N∇N + 2 dν/dB² (∇N·∇A)(∇N·∇A)`, the same as srm-forge's
`tangent_element_matrices`. The caller divides by `k_length²` (mm→m).

**`emdlab_m2d_tl3_evalJIT(cl, p) -> JIT[4×Ne], gea[1×Ne]`** [inferred from callers: not
decompiled] — per-element inverse-transpose of the affine map Jacobian and the element area.

**`ext_dpoly2d(P[Np×2], F[Nf×2], V[Nv×2]) -> d[Np×1]`** (DistMesh signed distance)
```c
for each point q:
    d = min over edges f of dist(q, segment V[f0]V[f1])     // brute force O(Np*Nf)
    tie on a shared vertex -> pick the edge by an angle/cross-product test
    sign: d = -d if q is left of the nearest edge (inside a CCW loop)
```

### 2.4 How the MEX files are wired in

```
assignEdata ─► m.evalKeMeFe_TL3 ─► ggmesh (concat zones, uniquetol node merge, ezi/emi masks)
                               ├─► evalJIT  (MEX) -> JIT, gea
                               └─► evalKeMeFe (MEX) -> Ke, Me, Fe, FeMx, FeMy  (cached on mesh)
solve:
  F = sparse(cl', 1, Fe .* Jint)                         % load
  K = sparse(I, J, nu .* Ke)                              % I,J from emdlab_flib_getij(3,1)
  rows of Dirichlet nodes replaced by identity; periodic rows combined (master ± slave)
  A = K \ F                                               % linear first guess, nu = nu0/500 in iron
  loop:
    evalBe (MEX) -> B²,  energy/coenergy (ppval of integrated B-H splines)
    nu = ppval(vB2, B²);  dnu = ppval(dvdB2, B²)          % PCHIP of nu(B²) and its derivative
    K  = sparse(I,J, nu.*Ke);  R = F - K*A
    K += sparse(I,J, evalG(cl,Ke,JIT,A,dnu)/k²)           % MEX
    BC rows; dA = K \ R
    A += alpha*dA      % alpha = 0.7, then 0.5+0.2*rand or 0.7+0.2*rand (random!)
  until  |dA|/|A| < 1e-8  AND  |ΔW|/W < 1e-3   (or 100 it)
```

---

## 3. EMDLAB SRM pipeline, script to GUI [observed]

```
script (examples/switched-reluctance-machine/*.m)
 │  dimensions in mm, angles in rad
 ├─ g = emdlab_g2d_db                         geometry database: points, edges (segment/arc), loops, faces
 │   └─ emdlab_g2d_lib_srm1 / lib_tc_srm*     builds ONE rotor pole sector and ONE stator half-tooth + half coil
 ├─ g.setMeshLengthByRadialFunction(f(r))     size field = interp1 over r: shaft→bore→OD (e.g. 3.8 / 0.4 / 3.9 mm)
 ├─ m = g.generateMesh('mg0')                 per face: DistMesh (rejection sampling + spring smoothing,
 │                                            ext_dpoly2d MEX, delaunay). Node count varies run to run.
 ├─ m.addMaterial / setMaterial               M530-50A B-H table -> PCHIP nu(B²), dnu/dB², energy splines
 ├─ m.aux_cmxjcrj('Rotor', Nr)                Copy-Mirror-X, Join, Copy-Rotate, Join: sector -> full machine
 ├─ m.aux_cmxcr('sca', Ns)                    coil halves copied but NOT joined -> zones sca11..sca2N (coil sides)
 ├─ m.rotateMeshZone('Rotor', θ)              rigid rotation of rotor zones
 ├─ m.aux_addCircularAirGap('ag', …, 3)       gap mesh between rotor ring and stator ring nodes, N layers
 ├─ s = emdlab_solvers_ms2d_tl3_ihnl(m)       ggmesh, default nu, units
 ├─ s.setLengthUnit('mm'); s.setDepth(70)
 ├─ s.defineCoil('phaseA'); s.addMeshZone2Coil('phaseA','sca11',278,+1) …   turns & direction per coil side
 ├─ s.setCoilCurrent('phaseA', 3.6)
 ├─ s.setAzBC(m.getfbn, 0)                    A=0 on every free-boundary node   (fraction model: getfbnioc +
 │                                            splitPeriodic + setOddPeriodicBC)
 ├─ s.solve                                   section 2.4
 ├─ post: evalCoilFluxLinkage, evalTorqueByArkkio('ag', gap), evalTorqueByMST3(r_mid), evalTotalEnergyCoenergy
 └─ s.gui                                     uitabgroup figure:
      Geometry | Mesh {Mesh Zones, Global Mesh, Wireframe, Free Boundary, Mesh Information table}
      Coils {All coil arms, one tab per coil, Flux Linkages table}
      Boundary Conditions {Vector Potential #k, Even/Odd Periodic #k: highlighted nodes}
      Field Plots {|B|, |B| smoothed, Flux Lines, |B| + flux lines, B arrows, M arrows, A}
      Solver Performance {Energy, Coenergy, Relative Error, Relative Energy Residual per iteration}
      About
```

Other SRM examples: 6/4, 12/8 (round and rectangular coils), 12/16 outer rotor (3 variants), 8/6
fraction (half model with odd-periodic BC), 8/6 static torque sweep compared against an ANSYS
Maxwell table (`srm-te-maxwell.tab`) with three torque methods (Arkkio, MST, coenergy derivative).

---

## 4. Side-by-side design differences

| aspect | EMDLAB | srm-forge (`srmcore`) |
|---|---|---|
| element | P1 triangles (TL3) and P2 (TL6) solvers | P1 only |
| geometry → mesh | mesh **one sector**, mirror + rotate copies, merge nodes by `uniquetol` | Gmsh OCC on the full machine, stator + rotor meshed once |
| mesh generator | DistMesh `mg0` (random sampling; not reproducible), or Gmsh via Python | Gmsh, deterministic, quality-gated |
| size field | 1-D function of radius | per-region sizes, tip/gap refinement, growth 1.3 (M5a presets) |
| air gap | `emdlab_mcs_circularAirGap`, 2–3 layers | moving band zipped from two rings with equal pitch, ≥ 4 layers (validator) |
| symmetry | optional fraction model with odd/even periodic BC (`srm86_fraction`) | full machine; `topology.radial.periodicity` reserved |
| element matrices | geometric Ke cached per zone once; ν applied per iteration | P1 gradients recomputed per angle in `_Discretisation` |
| rotation (transient solver) | rotate zones, recompute Ke **only for the gap interface** (`rotateMovingRegion`) | `mesh_at_angle` → new problem → new NGSolve discretisation (Netgen mesh, symbolic Assemble for sparsity, `searchsorted` scatter) |
| linear solver | MATLAB `\` on a row-replaced, nonsymmetric K (UMFPACK LU) | NGSolve UMFPACK on free DOFs (symmetric pattern), fresh `Inverse` every Newton step |
| Newton | consistent tangent, damping 0.5–0.9 with `rand`, stop on dA and energy | consistent tangent, backtracking line search, residual and dA < 1e-8, damped/ramp fallbacks |
| materials | PCHIP ν(B²) + analytic dν/dB²; linear extension to air | monotone Hermite H(B), C¹ tail to Js, stacking factor |
| torque | Arkkio, MST on a circle, surface MST, coenergy derivative | Arkkio + virtual work (nodal) + coenergy checks |
| scope | one point per script; GUI | maps, checks, provenance, web UI, losses, control SIL/HIL |
| determinism | no (DistMesh and Newton damping use `rand`) | yes (provenance hashing depends on it) |

---

## 5. What to port, ranked

Ranked by expected payoff for srm-forge's own goals (fast maps for an optimiser, a responsive web
UI). Speed estimates are [inferred] unless they cite a measurement.

### P1. A `preview` mesh preset for interactive single points
* **Why:** EMDLAB's 11k-node mesh is within 0.45 % ψ / 0.17 % T of a 224k-node mesh at one point
  [measured]. srm-forge `screening` (43k nodes) has 0.46 % worst error against a 2 % target.
* **What:** add `PRESETS["preview"]` (e.g. `scale≈2.0`, so about 4× fewer nodes) for the web UI's
  live field view and DXF before/after compare. Do **not** use it for maps or validation, and keep
  `screening` as the map default. A P1 h² error model predicts ~1.8 % at 4× fewer nodes, which is
  inside 2 % but fails the target/2 margin rule. Verify with the existing
  `examples/mesh_convergence.py run-presets` before deciding.
* **Expected:** ~3–4× faster per point (LU cost grows faster than linear in DOF).

### P2. Sector symmetry with anti-periodic BCs
* **Why:** `emdlab_examples_srm86_fraction.m` solves the 8/6 as a half model:
  `[km,ks] = m.splitPeriodic(fb_index, pi); s.setOddPeriodicBC(km,ks)` (A(θ+π) = −A(θ)).
* **What:** use `topology.radial.periodicity(p)` (gcd(Ns,Nr)) to mesh 1/k of the machine. Tie
  master/slave nodes on the cut lines with sign (−1)^(pole-pair parity of the excitation). In
  `physics/build.py` this is a DOF-elimination map P with A_full = P·A_reduced and
  K_r = Pᵀ K P. The band zipper must operate on the sector arc. Valid only when the excited circuits
  respect the symmetry (single-phase maps on 8/6, 12/8 and 24/16 do). The overlap map
  (two phases) may not, so fall back to the full model there.
* **Expected:** ~2× fewer DOF on 8/6, 4× on 12/8 (gcd 4), 8× on 24/16 (gcd 8), with superlinear
  factorisation savings.

### P3. Stop rebuilding the discretisation for every angle
* **Observed in srm-forge:** `NgsolveAdapter._bind` builds a new `_Discretisation` whenever the
  mesh arrays differ, which is every new angle: Netgen mesh, `H1`/`L2` spaces, a symbolic
  `Assemble()` to get the sparsity pattern, and a `searchsorted` over all `(e,i,j)` keys.
* **EMDLAB idea:** P1 element matrices are invariant under rigid rotation. Cache stator and rotor
  `grads`/`areas` (rotate gradients with R if needed: ∇N' = R∇N) and recompute only the band
  triangles. Build the CSR once for stator+rotor and merge the band block per angle with scipy, or
  keep NGSolve but cache the scatter index of the fixed blocks.
* **Expected:** unknown until measured. Time `_Discretisation.__init__` in `examples/solve_speed.py`
  first. M4a notes "first call includes the discretisation build".

### P4. Cheaper factorisation
* Already measured in srm-forge: symbolic reuse (`inverse.Update()`) 0.100 → 0.078 s per
  factorisation, about 8 % per solve (`docs/m4-handoff.md`).
* Further [inferred]: with Dirichlet DOFs eliminated (as srm-forge does) the Newton tangent is SPD
  for a monotone B-H law. Cholesky (CHOLMOD via `scikit-sparse`, or PARDISO SPD via `pypardiso`)
  is typically about 2× faster than LU and reuses the symbolic analysis across all Newton steps and
  all currents at one angle. Keep UMFPACK as the fallback when the factorisation reports non-SPD.
* Do **not** copy EMDLAB's row-replacement BC; it forces LU.

### P5. Sector-and-replicate meshing
* EMDLAB meshes one rotor pole and one half stator tooth, then mirrors and rotates
  (`aux_cmxjcrj`, `aux_cmxcr`). Benefits: meshing time ~1/(2N), and every pole gets an identical
  mesh, so aligned/unaligned torque is zero by construction and per-pole forces are not polluted by
  mesh asymmetry.
* In srm-forge: mesh the sector in Gmsh, then replicate nodes and triangles in numpy
  (rotate + mirror, merge coincident boundary nodes with a KD-tree or rounding). This feeds P2 directly.
* Watch out: region names and `CoilInfo` per copy (`coil_A1+` …) must be generated, not parsed.

### P6. Features to add to the web UI (from `emdlab_solvers_ms2d_tlcp.gui`, plotting methods)
1. **Flux lines**: contour of A over the mesh (`plotFluxLines`). Cheap and the most recognisable SRM plot.
2. **Smoothed |B|**: area-weighted nodal average of element B (`evalBn`, `evalBnSmooth` MEX), shown
   next to the raw element |B|.
3. **Air-gap Br/Bt along a circle** at r_mid and its FFT (`plotBrBtOnCircle`, `plotBrFFT`).
4. **Solver performance tab**: per-iteration relative ΔA, residual and energy (srm-forge already
   has iterations and residual in `FieldSolution`; store the history).
5. **Mesh information table** per region (elements per zone) and a free-boundary / BC-node view.
6. **Coil arm view**: highlight each coil side with its +/− direction and turns.
7. **MST torque on a circle** as a third torque estimate beside Arkkio and virtual work, in checks.

### P7. Relevant from other machine types (optional)
* `solvers/magnetic-transient-2d/emdlab_solvers_mt2d_tl3_ihnlwm.m`: time-stepping with motion and
  circuit coupling (stranded/solid coils, star connection). `rotateMovingRegion` rotates zones and
  recomputes only the interface Ke, then `rebuildKeMeFe` concatenates cached per-zone matrices. For
  SRM this would be a voltage-driven, field-coupled check of the map-based drive model, which is
  heavy. Treat it as a validation tool, not a map replacement.
* `functions/emdlab_calculateIronLosses*.m`, `emdlab_flib_calculateMECLM*.m`: iron-loss and
  magnetic-equivalent-circuit helpers. srm-forge R3 already covers iron losses. Not reviewed in depth.

### Do not copy
* `rand` in Newton damping, and DistMesh's random sampling. They break srm-forge's provenance and
  cache guarantees.
* Energy computed every Newton iteration only for the stopping test (5 % of EMDLAB solve time).
* Row-replacement Dirichlet BCs (forces LU, see P4).
* Single-point-per-script architecture.

---

## 6. Suggested first session in srm-forge

1. Measure before changing: add timers around `_Discretisation.__init__`, `set_tangent`,
   `Inverse`, `residual` and post in `examples/solve_speed.py` (screening, 20 A, θ = 0).
2. Run `examples/mesh_convergence.py run-presets` with a trial `preview` preset to see whether a
   ~10k-node mesh meets the 2 % / 3 % targets on 8/6, 12/8 and 24/16 (P1).
3. Prototype P3 (cache fixed blocks) and P4 (symbolic reuse or Cholesky). Gate on the
   goldens (`tests/maps/test_goldens.py`, slow) and the adapter cross-check.
4. Spec work for P2 (sector symmetry): decision in spec §11, validator rule for which excitations
   allow it, band on an arc.
5. UI items from P6, starting with flux lines and the air-gap Br/Bt plot.

Update the living project doc ("SRM design tool — how it was built") as CLAUDE.md requires.

---

## 7. Reproduce the EMDLAB numbers

The scripts are in `docs/emdlab-data/`. They expect EMDLAB at `C:\emdlab-win64` (its README's
install path). MATLAB runs headless from any shell, with no MCP needed:
```bash
cd docs/emdlab-data && "/c/Program Files/MATLAB/R2026b/bin/matlab.exe" -batch "bench_emdlab_srm86"
```
* `bench_emdlab_srm86.m`: builds the 8/6 example at size scales 1, 0.5, 0.3 and 0.2 (then one
  thread) and prints nodes, stage times, Newton iterations, ψ and T.
* `profile_emdlab.m`: MATLAB profiler, line times of `solve()` at ~40k nodes.
* `sweep86.m`: the shipped 30-position static-torque example with a timer, plots removed.

EMDLAB's own `emdlab paper.pdf` was not read here (no PDF renderer on that machine). Its content
came from the `emdlab` Claude skill built from the paper.

## 8. What the EMDLAB paper says (from the installed `emdlab` skill)

Jamali-Fard, Mirsalim, Sharifi, Majlesi, *EMDLAB*, SoftwareX 32 (2025) 102446, v0.2.1, GPL-3.0.

* The SRM benchmark (8/6, 125/74 mm, 0.5 mm gap, 70 mm stack, 278 turns, 3.6 A, M530-50A) matched
  ANSYS Maxwell: energy 0.6457 vs 0.6365 J, co-energy 0.7956 vs 0.7953 J.
* That match used **22,706 elements** for EMDLAB against 20,442 for Maxwell, which is about 11k
  nodes, the same size as the example mesh measured in section 1. Coarse meshes are the paper's
  normal practice, not a shortcut.
* The paper's torque check: Arkkio, MST at mid-gap, and co-energy derivative over 30 positions in
  30°. All three agree with Maxwell under saturation.
* Paper scope: 2D magnetostatic only, no transient, no automatic losses. **The repo has moved
  past this**: it now ships `solvers/magnetic-transient-2d` (motion, circuits, cage, star),
  thermal 2D/3D static and transient solvers, an NSGA-II optimiser class and iron-loss helpers.
* The paper's "mesh mapping" (mesh the fraction, mirror and rotate) is what section 5 P5 recommends.

---

## 9. Feature comparison: EMDLAB vs srm-forge (main @ af86518)

### 9.1 What each one shows

| view | EMDLAB `s.gui` (MATLAB figure, after one solve) | srm-forge web UI (`srmweb`, React) |
|---|---|---|
| geometry | Geometry tab: sketch of faces and edges | outline SVG (`/api/geometry`) live while typing; Dimension tab |
| mesh | Mesh Zones, Global Mesh, Wireframe, Free Boundary, element count per zone | not shown as a view (mesh is internal; Field tab has a layer toggle) |
| coils | every coil arm; one tab per coil; flux-linkage table | Winding tab: turns per pole, strands, wire, parallel paths, auto/fixed mode, winding scan |
| boundary conditions | Dirichlet and periodic nodes highlighted | not shown (A = 0 on the outer edge, fixed) |
| field | \|B\|, smoothed \|B\|, flux lines, \|B\| + flux lines, B arrows, M arrows, A | Field tab: WebGL \|B\| (inferno), rotor-angle and current controls, aligned/unaligned, layers, torque readout; animation unaligned → aligned with B(θ) probes in stator pole, yoke, rotor pole |
| air-gap waveforms | Br/Bt on a circle or arc, Br FFT | not shown |
| solver convergence | energy, co-energy, relative error, energy residual per iteration | job stepper with ETA; iterations stored per map point |
| flux-linkage / torque maps | none (a script would have to loop) | Map tab: ψ(θ,i), inductance vs angle, torque vs angle; .mat/CSV export |
| inductance | none | Design factors: inductance vs current; La, Lu, La/Lu key numbers |
| drive performance | none | Performance tab: torque-speed envelope; Waveforms tab: phase and line current, phase voltage |
| losses / efficiency | helper functions only, no view | Losses tab: iron loss (stroke fields, per-element B radial/tangential), AC copper, efficiency map |
| control | none | Control tab: SIL (hysteresis, PWM current, TSF controllers, ADC, encoder, dead time, load step) and HIL rig panel |
| validation | user compares with Maxwell by hand | EM validation panel, "2D-verified" label, §7.3 map checks, run report (HTML) |
| design search | none (NSGA-II class exists, not wired to SRM) | requirements → candidates → stage-1 filter → turns scan → Pareto plot |

### 9.2 Can it do X?

| capability | EMDLAB | srm-forge |
|---|---|---|
| inner-rotor radial SRM | yes (6/4, 8/6, 12/8 examples) | yes (any valid Ns/Nr, 3+ phases; references 8/6, 12/8, 24/16) |
| outer-rotor SRM | **yes** (12/16 examples, `tc_srm1/2`) | no (radial inner rotor only) |
| rectangular coils, coil shape variants | **yes** (`tc_srm7`, `_rc` examples) | coil fills the slot by clearance and fill-factor rules |
| other machines (IM, PMSM, IPM, SynRM, BLDC, AFPM, transformers, linear) | **yes**, ~50 geometry templates | no (SRM only, by design) |
| P2 (second-order) elements | **yes** (TL6 solvers) | no (P1 only) |
| fraction model with periodic BC | **yes** | no (reserved) |
| transient with motion + circuits | **yes** (`mt2d_*`) | no (map-based drive simulation instead) |
| thermal FEA | **yes** (2D/3D, static/transient) | no |
| full ψ/T map, inverse tables, LUT export | no | **yes** |
| mesh convergence presets with stated errors | no | **yes** (M5a) |
| deterministic, cached, provenance-hashed results | no (random mesher and damping) | **yes** |
| DXF import | **no** | **yes**: import iron loops, checked (`check_iron`), locked geometry, before/after compare |
| DXF export | **no** (`showDXF` only plots) | **yes** |
| export to ANSYS Maxwell | **yes** (VBS script: `drawGeometryInMaxwellModel`) | no |
| Gmsh .geo/.msh, STL | yes | uses Gmsh internally |
| requirements-driven design search | no | **yes** |
| control SIL/HIL | no | **yes** |
| runtime | MATLAB licence | free Python stack |

---

## 10. Geometry routes: template, or draw it yourself

### Template (parametric)
* **EMDLAB**: call a library function with dimensions, e.g.
  `emdlab_g2d_lib_srm1(g, Ns, Nr, Dsh, ISD, OSD, gap, beta_r, beta_s, wry, wsy)` or the tooth-coil
  pair `emdlab_g2d_lib_tc_srm1/2(g, ISD, OSD, N, g_beta, g_wy, name1, name2)`. Seven SRM tooth-coil
  templates (`tc_srm1, 2, 301, 302, 4, 7, 8`), round or rectangular coils, inner or outer rotor. Each
  draws one sector. You must name zones and wire up coil sides (`sca11`, `sca21` …) yourself in
  the script. There is no input validation: a bad dimension surfaces as a mesher or solver error.
* **srm-forge**: `RadialSRMParams` (poles, phases, diameters, gap, stack, pole arcs, **taper**,
  yokes, **fillets**, turns, fill factor, liner, clearance, lamination thickness, max speed),
  presets from references 8/6, 12/8, 24/16, or a search candidate. `model/validator.py` rejects bad
  designs before meshing, naming the parameter and the rule. Coil sides and circuits are generated
  (`CoilInfo`).
* **To port from EMDLAB**: an outer-rotor topology variant and a rectangular-coil variant.

### Draw it yourself (DXF)
* **EMDLAB**: no DXF reader. You would trace points into `addPoint`/`addSegment`/`addArc`, or use
  `addClosedPolylineLoop(x, y)` with coordinates parsed in your own MATLAB code.
* **srm-forge** (R2): Export a case's iron as DXF, edit it in CAD, and Import DXF to create a new
  case with origin `dxf`. `check_iron` reports `open_loop`, `bad_segment`, `centre`,
  `rotor_angle`, `self_intersection`, `bodies`, `stray_loop`, `air_gap`, `coil_overlap`, `repeat` and
  `web_width`. Geometry is locked afterwards (the mesh preset stays editable), and
  `/api/cases/{id}/compare` shows before/after ψ, torque, key numbers and mass.
* **Gap**: imported iron may be asymmetric, so the symmetry speed-ups (P2, P5, P8 below) must
  detect symmetry (rotate and mirror the loops, compare within tolerance) and fall back to the full
  model when it fails.

---

## 11. Fast route for srm-forge

Three speed tiers, with the moves from section 5 placed where they pay. Numbers are [inferred]
multipliers on the current per-point cost unless marked.

**Tier A: interactive, under 1 s per point (Field tab, live edits, DXF compare)**
1. `preview` preset, about 4× fewer nodes (P1): ~3–4×.
2. Sector model with anti-periodic BCs when the drawing is symmetric (P2): 2× on 8/6, 4× on 12/8.
3. Cache the stator and rotor discretisation and change only the band per angle (P3).
4. Keep a warm solver per case in the quick lane (`QuickLane` already spawns one process), so
   repeated snapshots reuse mesh, sparsity and the factorisation analysis.
* Combined, a 3 s point drops to roughly 0.2–0.4 s.

**Tier B: maps for the optimiser (screening, 360 points)**
1. **P8, new: solve half a rotor pole pitch.** For a symmetric lamination with single-phase
   excitation, ψ(−θ) = ψ(θ) and T(−θ) = −T(θ) about the aligned position, so `angle_grid` over
   `[0, τ)` solves each angle twice. Solve `[0, τ/2]` and mirror: ~2× fewer points. The
   `zero_mean_torque` and `sign_pattern` checks then become true by construction, so keep the full
   pitch for `validate`. The overlap map (two phases) and asymmetric DXF iron need the full pitch.
2. Sector model (P2) and Cholesky with symbolic reuse (P4): 2–4× and up to ~2× respectively.
3. Warm start from the neighbouring current: measured 20 % saving, rejected for independence
   (`maps/run.py`). Offer it as an opt-in "fast" flag that is excluded from validated maps.
4. Group pool jobs by angle so each worker reuses its cached discretisation for all currents at
   that angle (P3), while keeping highest-current-first inside the group.
* Combined, 262 s on this laptop could plausibly drop to ~30–60 s for screening maps.

**Tier C: validated maps (`full`/`reference`)**
* Keep the full pitch and full model, and use only exact speed-ups: P3, P4, and sector replication
  of the mesh (P5, which also removes mesh-asymmetry noise). Re-run the goldens and
  `em_validate` after each change.

**Beyond P1 elements (research option)**: EMDLAB's TL6 solver suggests trying P2 elements on a
coarser mesh. They often reach the same error with fewer DOF for smooth fields, though iron
corners limit the gain. Measure on the M5a designs before committing.

---

## 12. Can EMDLAB run in GNU Octave?

Not as shipped. Octave was not installed here, so this is a code scan, not a test.

* **The MEX binaries are MATLAB-only.** The `.mexw64` files link MATLAB's `libmx.dll`/`libmex.dll`
  [observed]. Octave loads MEX built with its own `mkoctfile --mex`, and **the repo ships no C
  source** for any of the 133 MEX files [observed: no `.c`/`.cpp` in the tree]. Every solve calls
  `evalKeMeFe`, `evalJIT`, `evalB` and `evalG`, and the mesher calls `ext_dpoly2d`. These would
  need rewriting, either as vectorised `.m` code or as C rebuilt from the section 2.3 pseudocode.
* **MATLAB-only language and library features** [observed counts]:
  * `matlab.mixin.SetGet` and other `matlab.mixin` classes (33 files).
  * Property validation such as `(1,1) double {mustBePositive}` (75 files, 37 with `mustBe*`).
  * `delaunayTriangulation` (9 files) and `scatteredInterpolant` (6, used by the `mg0` mesher).
  * `uniquetol(...,'ByRows')` (10, used by `ggmesh` node merging).
  * `uitabgroup`/`uitab`/`uitable` (the whole GUI) and `animatedline` (6).
  * `fnint` (1, B-H energy splines; Curve Fitting Toolbox in MATLAB).
  * MATLAB string objects with `+` concatenation in plots.
  * Octave support for several of these is missing or partial [inferred; verify per Octave version].
* **Cost of a port**: rewrite the MEX kernels and several classes, the mesher and the GUI. That
  is a fork, not a setting. For srm-forge it is not needed: the ideas port to Python directly.

---

## 13. Should EMDLAB be ported to Python as a whole?

**Recommendation: no. Port selected ideas into srm-forge instead.**

### Size and mapping
The repo holds roughly 50k+ lines of MATLAB [inferred from counted parts: mesh classes ~18.9k,
magnetostatic 2D ~8.6k, transient 2D ~6.4k lines, plus geometry, ~50 templates, 3D meshes,
thermal and GUI].

| EMDLAB | Python equivalent | difficulty |
|---|---|---|
| MEX kernels (no source shipped) | numpy einsum or numba (srm-forge `physics/fem.py` already does this) | trivial |
| `sparse(I,J,V)`, `\` | `scipy.sparse` COO→CSR; UMFPACK, CHOLMOD or PARDISO | easy |
| `pchip`, `ppval`, `fnint` | `scipy.interpolate.PchipInterpolator`, `.antiderivative()` | easy |
| `uniquetol` node merge | `scipy.spatial.cKDTree` | easy |
| geometry db (point → edge → loop → face) | own classes, or Gmsh OCC | medium |
| DistMesh `mg0`, `delaunayTriangulation` | Gmsh or `triangle` (scipy's Delaunay is unconstrained) | medium; Gmsh beats the original |
| mirror/rotate replication, air-gap band | numpy | medium |
| ~50 geometry templates | mechanical translation | tedious |
| TL6, transient with motion and circuits | same assembly + time stepping + circuit rows | medium–hard |
| thermal 2D/3D, hex/prism meshes | separate subsystems | hard, low value for SRM |
| `uitabgroup` GUI | matplotlib/pyvista or a web front end | medium |

The real cost is **re-validation**, not translation: every solver must be benchmarked again
against Maxwell, FEMM or measurements. srm-forge already paid that cost for SRM (M5: convergence,
TEAM 24, FEMM, Krishnan 6/4).

### Why not port the whole thing
* For SRM, srm-forge's core is already stronger: deterministic, validated, ~1.5× faster per node
  (section 1), with maps, losses and control.
* What EMDLAB adds beyond srm-forge is mostly other machine types and thermal, which are outside
  srm-forge's purpose.
* For a general multi-machine Python FEA tool, start from existing projects (pyleecan,
  scikit-fem/NGSolve directly, FEMM via pyfemm, GetDP/ONELAB) rather than rebuilding EMDLAB.

### What to port instead (one session each)
1. Speed tiers from section 11: sector symmetry (P2), half-pitch angles (P8), discretisation
   caching (P3), Cholesky with symbolic reuse (P4).
2. Outer-rotor and rectangular-coil SRM templates (section 10).
3. UI items from P6: flux lines, air-gap Br/Bt with FFT, convergence plots.
4. Transient-with-motion solver as a validation tool (P7), optional.
5. A P2-element accuracy-per-DOF experiment on the M5a designs.

### Licence caveat
EMDLAB is **GPL-3.0**. Translating its `.m` source line by line into srm-forge would likely make
that part a derivative work under GPL-3, which matters if srm-forge is in-house or differently
licensed. Reimplementing from the paper, textbooks and observed behaviour is the safer route. This
file describes ideas and pseudocode of standard FE kernels only, not copied code. Not legal
advice; check before shipping.

---

## 14. Open questions
* Exact srm-forge per-stage split at 43k nodes (only totals and the factorisation time are recorded).
* Whether `preview` meets targets at the corner points of M5a (high saturation, unaligned).
* EMDLAB's TL6 (second-order) solver accuracy per DOF compared with P1. P2 elements often reach a
  target error with fewer DOF; not measured here.
