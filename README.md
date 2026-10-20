# DtPerf — replication package

Code, raw results and analysis scripts for the manuscript
**"Decision-Latency Budgets in Digital Twins: How Object-Materialization Strategies Bound Fleet Capacity and Decision Quality"**
(A. Bărbulescu, T. F. Furtună — Bucharest University of Economic Studies; submitted to the *Journal of Systems and Software*, Elsevier).

The version cited in the manuscript is the commit that introduced this README text (see the Data availability section of the article). All code and data are identical to commit `0c88459`.

## Contents
| Path | What it is |
|---|---|
| `src/` | Materialization strategies S1–S5 and synthetic probe (`Materializers.cs`), benchmark harness (`Harness.cs`), micro-benchmarks (`MicroBenches.cs`), closed-loop fleet digital twin (`DtSim.cs`), generated entities/mappers (`*.g.cs`) |
| `tools/gen_entities.py` | Generates the snapshot classes and the source-generator-equivalent mappers |
| `build/jit`, `build/aot` | .NET 8 + .NET 10 JIT project; .NET 10 Native AOT project |
| `run_all.sh` / `run-all.ps1`, `RUN-ME.cmd`, `setup-and-run.ps1` | Microbenchmarks and cold-start measurements (Linux / Windows) |
| `run_v2.sh` | Closed-loop protocol v2 on Linux: θ calibration, unconstrained references for every fleet size and seed, main grid (5 seeds), synthetic capacity map at B = 10, 5 and 20 ms, depth-only ablation, θ sensitivity |
| `run-sim-v2.ps1`, `RUN-SIM-V2.cmd` | Closed-loop protocol v2 on Windows (references + main grid, 3 seeds) |
| `analysis/analyze.py` | Produces all tables and figures from `results/` |
| `results/<platform>/` | Raw CSV results: `micro_*.csv`, `cold.csv` (microbenchmarks, cold start); `sim.csv`, `reference.csv` (closed loop v2); cloud platform only: `calibration.csv`, `synthetic.csv`, `ablation.csv`, `sensitivity.csv`, `gc_diagnostic.csv`, `micro20_rep/` (P = 20 materialization repeated in fresh processes), `theta.txt` |
| `results_v1_superseded/` | Closed-loop results of the first protocol (decision step outside the budget, single reference fleet), kept for transparency; not used in the manuscript |

## Closed-loop protocol v2
* The budget B covers the whole cycle until decisions are issued (synchronization, screening, what-if analysis, decision); time for screening and decision is reserved from a smoothed estimate of previous cycles.
* Each run reports the 95th/99th percentile and maximum cycle latency and the share of cycles exceeding B by more than 5 %.
* Regret is computed per seed against an unconstrained reference (B = 1 s, S5, 2,048 samples per candidate) with the same fleet size and seed.
* Monte Carlo paths allow at most one regime shift, as the physical process.
* CSV files written by `run_v2.sh` / `run-sim-v2.ps1` have no header; the columns are listed in `DtSim.Header` (`src/DtSim.cs`), with a leading `Theta` (calibration, sensitivity) or `K` (ablation) column where applicable.

## Reproduce
Linux: `./run_all.sh <label>` (microbenchmarks, cold start, then `run_v2.sh`). Windows: `RUN-ME.cmd`, then `RUN-SIM-V2.cmd`.
Analysis: `python analysis/analyze.py results out <platform-label>`.

## License
Code (src/, tools/, analysis/, scripts): MIT License (see LICENSE). Data (results/, results_v1_superseded/): Creative Commons Attribution 4.0 International (CC BY 4.0, see results/LICENSE).
