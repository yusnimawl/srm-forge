# R6d: optimisation methods for R7 (literature review)

Date: 2026-11-06. Roadmap item R6d (`docs/superpowers/specs/2026-10-12-roadmap-r1-r10-design.md`). This review is the input to R7's spike. It does not change code.

**Recommendation.** R7's spike compares three arms on the same budget of `screening` maps, then confirms every arm's finalists at `full`:

1. **Funnel (baseline):** today's Latin-hypercube sample, stage-1 filter and shortlist.
2. **Evolutionary:** NSGA-II (NSGA-III if the R7 spec keeps four or more objectives), from pymoo.
3. **Surrogate:** a Gaussian-process (Kriging) model per pole set, with batch noisy expected-hypervolume infill (qLogNEHVI, BoTorch).

The literature gives the surrogate arm the best odds. Direct evolutionary search on FE needs thousands of design evaluations in the SRM papers below. The tool can afford about 220 to 320 `screening` maps in a 10-hour night on the LattePanda. Before the spike, R7 should also cut the FE dimension and the cost per map (§4). Those gains multiply with any algorithm.

## 1. The problem R7 has to solve

| Item | Today (`srmapp`) | In R7 |
| --- | --- | --- |
| Geometry variables | 8 per pole set: OD, stack/OD, rotor/OD, two pole arcs, two yoke ratios, shaft ratio (`sizing/generator.py`) | 9: the air gap joins (roadmap R7) |
| Pole set | 4 fixed sets (6/4, 8/6, 12/8, 24/16), budget split evenly | categorical, the same split or a choice |
| Winding | turns and parallel paths chosen after the map, exact by `turns.rescale_turns` | the same |
| Objectives | mass, kW/kg, copper-only efficiency at base speed (`SearchResult.pareto`) | peak and continuous kW/kg and kW/L (roadmap §1) |
| Constraints | torque and power ratio ≥ the grade margin | plus R5: hot spot, rotor stress at 1.2 × max speed, gap closure |
| Fidelity ladder | stage-1 analytic bound (ms), `screening` map, `full` map | explore at `screening`, confirm at `full` |

Cost of one design evaluation. One evaluation is a whole map, not one FE solve. Measured on the LattePanda (i5-1340P, 8 workers, srmcore 0.7.0, 2026-10-31, `docs/validation-report.md`):

| Map | 8/6 | 12/8 | Maps in 10 h |
| --- | --- | --- | --- |
| `screening` (40 × 8 points) | 113 s | 162 s | 222 to 318 |
| `full` (48 × 20 points) | 694 s | 928 s | 39 to 52 |

The fidelity rule (core spec §7.2) allows exploring at `screening` if key numbers stay within 3 % of `full` and the design ranking keeps Spearman ρ ≥ 0.95. On four near-identical 8/6 variants the peak-torque ρ was −0.4 because the variants spanned only 0.3 % (`docs/m4-handoff.md`). The rule therefore needs designs that differ by more than the screening error.

## 2. What the literature reports

The numbers below come from different machines and different "evaluation" units. They are not directly comparable, and no source reports time to a stated accuracy on an SRM. They show orders of magnitude.

| Method | Source | Problem | Evaluations or cost | Finding |
| --- | --- | --- | --- | --- |
| Response surface vs differential evolution (DE) | [Duan and Ionel 2013](https://scholars.uky.edu/en/publications/a-review-of-recent-developments-in-electrical-machine-design-opti-2/) | PMSM, 5 variables, nonlinear Pareto front | not stated in the abstract | The two are comparable with few candidate designs. DE is better with many. |
| Kriging + NSGA-II, sequential subspaces | [Diao et al. 2020](https://opus.lib.uts.edu.au/handle/10453/147017) | segmented-rotor SRM drive, 10 motor and control variables, 3 subspaces | 3993 FEM samples in 3 iterations, against about 50 000 for direct GA (100 × 500) | Torque +41.9 %, ripple −65.9 % against the initial design |
| Multi-level (subspace) optimisation, Kriging + DE | [Lei et al. 2017](https://opus.lib.uts.edu.au/handle/10453/123900) | claw-pole motor, 9 variables | 6.71 % of the FEM samples of direct optimisation | Space-reduction methods need about 10 % of the samples of DE plus FEM. |
| DOE + response surface to narrow bounds, then multi-objective DE | [Tekgun et al. 2022](https://avesis.agu.edu.tr/yayin/e4275592-d4e9-4af9-8759-f9a9479a3286/fea-based-fast-topology-optimization-method-for-switched-reluctance-machines) | 24/16 SRM hub motor, 6 variables, 3 objectives | 559 designs, 6 h 30 min, against ≥ 3000 designs, 32 h 50 min | A similar Pareto front, but the narrowing "does not guarantee" it |
| Surrogate model survey | [Cheng et al. 2024](https://eprints.whiterose.ac.uk/id/eprint/209388/) | electric motors | Kriging studies use 2 to 5 variables. CNN surrogates stayed mediocre with a few thousand samples. | Kriging is the most accurate statistical surrogate at low dimension. |
| Gaussian-process Bayesian optimisation | [Asef and Vagg 2025](https://arxiv.org/abs/2503.00420) | wound-field synchronous machine slot design, 2D FEA | 45 % faster than NSGA-II | Physics features in the GP model help. |
| Cheap/expensive split in multi-objective BO | [Loka et al. 2024](https://documentserver.uhasselt.be/handle/1942/41753) | PMSM, FEM objectives plus closed-form ones | not stated in the abstract | Modelling only the FE outputs and evaluating closed-form terms directly gives a large gain in data efficiency. |
| qNEHVI acquisition | [Daulton et al. 2021](https://papers.neurips.cc/paper_files/paper/2021/file/11704817e347269b7254e744b5e22dac-Paper.pdf) | benchmark problems | batch of q points in parallel | Robust to noisy observations, polynomial cost in q |
| NSGA-III | [Deb and Jain 2014](https://scispace.com/pdf/an-evolutionary-many-objective-optimization-algorithm-using-8ez88ki1ee.pdf) | test problems, 3 to 15 objectives | population-based, as NSGA-II | For many objectives. NSGA-II (Deb et al. 2002, doi 10.1109/4235.996017) remains the usual choice up to 3. |

Three points follow for this tool:

1. **Direct evolutionary search does not fit the budget.** A GA with population 100 over 50 generations needs 5000 maps, about 7 to 9 days of `screening` maps on the LattePanda. Even Tekgun's reduced 559 designs is about 18 to 25 hours.
2. **Kriging fits the dimension.** Per pole set the FE problem has 8 or 9 variables (7 or 8 with stack-length rescaling, §4). That is above the 2 to 5 variables in Cheng's Kriging table but below the point where only neural models are left. Diao and Lei handle 9 to 10 variables with Kriging by splitting the space into subspaces.
3. **Most of the R7 objective is cheap.** The map is the only expensive step. Turns, wire, drive envelope, losses (from cached strokes), the R5 thermal network and rotor stress are post-processing. This is the cheap/expensive split of Loka et al.: model the map's key outputs, compute the rest exactly.

## 3. Pole-shape and topology optimisation

| Source | Method | Machine | Finding |
| --- | --- | --- | --- |
| [Lee, Lee and Jang 2021](https://koasas.kaist.ac.kr/handle/10203/287230) | spline pole shapes, Maxwell plus Simplorer | SRM rotor and stator | Shapes set average torque and ripple under a current limit. |
| [Zhang et al. 2014](https://faculty.xjtu.edu.cn/youpeng.huangfu/zh_CN/lwcg/304986/content/16789.htm) | level set on the rotor | 4/2 high-speed SRM | The rotor saliency shape raises the static torque. |
| [Manninen et al. 2019](https://cris.vtt.fi/en/publications/impact-of-topology-optimization-problem-setup-on-switched-relucta/) | topology optimisation, three formulations | 8/6 rotor | The result depends on the material definition and the mesh. Rotor mass could not drop much without torque loss. |
| [Abdalmagid, Bakr and Emadi 2023](https://pure.kfupm.edu.sa/en/publications/a-linesearch-based-algorithm-for-topology-and-generative-optimiza/) | ON/OFF topology with a linesearch | 6/14 SRM | Faster convergence than annealing-based ON/OFF |

These methods tune the shape of one chosen machine, mostly for ripple. They need many solves per design or adjoint sensitivities, and srmcore has no shape sensitivities. They belong after R7 has chosen the main dimensions, with R9 (ripple) or the DXF path of R2. They are not part of the R7 spike.

## 4. Winding choice and cheaper evaluations

The tool already does the established step for the winding: one map at `REFERENCE_TURNS`, then turns and paths by exact rescaling. Lei et al. 2017 leave the turns out of the FEM for the same reason. Wire and paths are discrete, so enumeration after the map stays the right method.

Levers that cut the cost of each evaluation, in order of expected gain:

1. **Stack length after the map.** srmcore uses `stack_length` only as the 2D depth (`physics/build.py`). ψ and torque scale linearly with it, and B does not depend on it. The end winding and the map checks are analytic. A `rescale_stack` beside `rescale_turns` removes one FE variable, and R7 can then search stack length for free. The measured end-effect gap grows on short stacks (`docs/r4-end-effect-results.md`), so the budget row must use the final stack.
2. **Half-pitch symmetry.** ψ(−θ) = ψ(θ) and T(−θ) = −T(θ) for phase A. Half the angles need solving. This is listed as a lever in the v0 spec §4 and is not done.
3. **No zero-current column, L_inc optional.** Both are v0 spec §4 levers. With 8 currents the zero column is 1/8 of the `screening` map.
4. **The fidelity ladder.** Stage-1 bounds (milliseconds) prune, `screening` explores, `full` confirms. The stage-1 false-drop rate is tracker item 11 and should be measured before the spike.

Radial scaling (all lengths × k, ampere-turns × k) is exact in 2D magnetostatics only when the air gap and the mesh scale too. R7 makes the gap a free variable with a buildable minimum, so radial scaling is not recommended.

## 5. The R7 spike list

Each arm runs on the same requirements, the same pole set and the same number of `screening` maps. The finalists of each arm are confirmed at `full`. The score is the hypervolume of the confirmed feasible front against maps spent.

| Arm | Method | Library | Why it is in the spike |
| --- | --- | --- | --- |
| A | Funnel: LHS, stage-1 filter, shortlist (today) | none new | Baseline. Cheap per design, no learning. |
| B | NSGA-II, or NSGA-III with 4 or more objectives | pymoo ([Blank and Deb 2020](https://arxiv.org/abs/2002.04504), Apache 2.0) | The roadmap names it. The literature's default. |
| C | GP per pole set on the map's key outputs, initial LHS, then qLogNEHVI batches | BoTorch ([repository](https://github.com/meta-pytorch/botorch), MIT, needs PyTorch) | Best data efficiency in the sources, and the cheap/expensive split fits the tool. |

Suggested spike scale: the 8/6 pole set, one requirement set at the 400 V bus, 150 `screening` maps per arm, two seeds. That is 6 runs of about 5 hours on the LattePanda, plus `full` confirmation of about 5 finalists per run. Arm C uses about 20 initial LHS designs (about 2 per variable) before infill.

Kept out of the spike, with the reason:

- **PSO, ACO and other swarm methods:** no source here shows an advantage over DE or GA on machine design.
- **Neural-network and deep surrogates:** CNN surrogates stayed mediocre with a few thousand samples (Cheng et al. 2024), about ten times the budget.
- **Sequential subspace and multi-level optimisation:** a fallback if the dimension grows past about 10. It needs a sensitivity study first.
- **Pole-shape and topology optimisation:** after R7 (§3).

Open questions for the R7 spec:

1. How many objectives? Peak and continuous kW/kg and kW/L are four, which needs NSGA-III. kW/kg and kW/L are strongly correlated, so two or three may do.
2. Is PyTorch acceptable as an optional extra (`opt`), like `ngsolve`?
3. What budget is acceptable for one R7 search: one night on the LattePanda?

## Sources

Pages were opened on 2026-11-05 or 2026-11-06. "Abstract only" means the abstract or the publisher record was read, not the paper. "Record only" means only the bibliographic record was checked.

- Y. Duan and D. M. Ionel, "A review of recent developments in electrical machine design optimization methods with a permanent-magnet synchronous motor benchmark study," IEEE Trans. Ind. Appl. 49(3), 2013, pp. 1268–1275, doi 10.1109/TIA.2013.2252597. Abstract only. https://scholars.uky.edu/en/publications/a-review-of-recent-developments-in-electrical-machine-design-opti-2/
- K. Diao, X. Sun, G. Lei, Y. Guo and J. Zhu, "Multiobjective system level optimization method for switched reluctance motor drive systems using finite-element model," IEEE Trans. Ind. Electron. 67(12), 2020, pp. 10055–10064. Accepted version read in full. https://opus.lib.uts.edu.au/handle/10453/147017
- G. Lei, J. Zhu, Y. Guo, C. Liu and B. Ma, "A review of design optimization methods for electrical machines," Energies 10(12), 1962, 2017, doi 10.3390/en10121962. Read in full. https://opus.lib.uts.edu.au/handle/10453/123900
- D. Tekgun, B. Tekgün and İ. Alan, "FEA based fast topology optimization method for switched reluctance machines," Electrical Engineering 104(4), 2022, pp. 1985–1995, doi 10.1007/s00202-021-01453-9. Abstract only. https://avesis.agu.edu.tr/yayin/e4275592-d4e9-4af9-8759-f9a9479a3286/fea-based-fast-topology-optimization-method-for-switched-reluctance-machines
- M. Cheng, X. Zhao, M. Dhimish, W. Qiu and S. Niu, "A review of data-driven surrogate models for design optimization of electric motors," IEEE Trans. Transp. Electrif., 2024, doi 10.1109/TTE.2024.3366417. Accepted version read in full. https://eprints.whiterose.ac.uk/id/eprint/209388/
- P. Asef and C. Vagg, "A physics-informed Bayesian optimization method for rapid development of electrical machines," arXiv 2503.00420. Read in full. https://arxiv.org/abs/2503.00420
- N. Loka, M. Ibrahim, I. Couckuyt, I. Van Nieuwenhuyse and T. Dhaene, "Cheap-expensive multi-objective Bayesian optimization for permanent magnet synchronous motor design," Engineering with Computers 40(4), 2024, pp. 2143–2159, doi 10.1007/s00366-023-01900-0. Abstract only. https://documentserver.uhasselt.be/handle/1942/41753
- S. Daulton, M. Balandat and E. Bakshy, "Parallel Bayesian optimization of multiple noisy objectives with expected hypervolume improvement," NeurIPS 2021. Record only. https://papers.neurips.cc/paper_files/paper/2021/file/11704817e347269b7254e744b5e22dac-Paper.pdf
- K. Deb and H. Jain, "An evolutionary many-objective optimization algorithm using reference-point-based nondominated sorting approach, Part I," IEEE Trans. Evol. Comput. 18(4), 2014, pp. 577–601, doi 10.1109/TEVC.2013.2281535. Record only.
- C. Lee, J. Lee and I. G. Jang, "Shape optimization-based design investigation of the switched reluctance motors regarding the target torque and current limitation," Struct. Multidiscip. Optim. 64(2), 2021, pp. 859–870, doi 10.1007/s00158-021-02897-0. Abstract only. https://koasas.kaist.ac.kr/handle/10203/287230
- H. Zhang, W. Xu, S. Wang, Y. Huangfu, G. Wang and J. Zhu, "Optimum design of rotor for high-speed switched reluctance motor using level set method," IEEE Trans. Magn. 50(2), 2014, 7018904. Record only. https://faculty.xjtu.edu.cn/youpeng.huangfu/zh_CN/lwcg/304986/content/16789.htm
- A. Manninen et al., "Impact of topology optimization problem setup on switched reluctance machine design," COMPUMAG 2019, doi 10.1109/COMPUMAG45669.2019.9032826. Abstract only. https://cris.vtt.fi/en/publications/impact-of-topology-optimization-problem-setup-on-switched-relucta/
- M. Abdalmagid, M. H. Bakr and A. Emadi, "A linesearch-based algorithm for topology and generative optimization of switched reluctance machines," IEEE Trans. Transp. Electrif. 9(3), 2023, pp. 3849–3866, doi 10.1109/TTE.2023.3245992. Abstract only. https://pure.kfupm.edu.sa/en/publications/a-linesearch-based-algorithm-for-topology-and-generative-optimiza/
- J. Blank and K. Deb, "pymoo: Multi-objective optimization in Python," IEEE Access 8, 2020, pp. 89497–89509. https://arxiv.org/abs/2002.04504
- BoTorch repository (MIT licence, Python ≥ 3.11, PyTorch ≥ 2.0.1) and its multi-objective documentation (qLogNEHVI). https://github.com/meta-pytorch/botorch, https://botorch.org/docs/multi_objective
