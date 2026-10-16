# DtPerf — replication package

Code, raw results and analysis scripts for the manuscript
**"Decision-Latency Budgets in Digital Twins: How Object-Materialization Strategies Bound Fleet Capacity and Decision Quality"**
(A. Bărbulescu, T. F. Furtună — Bucharest University of Economic Studies; submitted to *Systems*, MDPI).

## Contents
| Path | What it is |
|---|---|
| `src/` | Materialization strategies S1–S5 and synthetic probe (`Materializers.cs`), benchmark harness (`Harness.cs`), micro-benchmarks (`MicroBenches.cs`), closed-loop fleet digital twin (`DtSim.cs`), generated entities/mappers (`*.g.cs`) |
| `tools/gen_entities.py` | Generates the snapshot classes and the source-generator-equivalent mappers |
| `build/jit`, `build/aot` | .NET 8 + .NET 10 JIT project; .NET 10 Native AOT project |
| `run-all.ps1`, `RUN-ME.cmd`, `setup-and-run.ps1` | Windows protocol (installs prerequisites, runs everything) |
| `run_all.sh`, `run_sim.sh`, `run_sens.sh`, `run_synth.sh`, `cal.sh` | Linux protocol, closed-loop runs, sensitivity, synthetic sweep, threshold calibration |
| `analysis/analyze.py` | Produces all tables and figures from `results/` |
| `results/cloud-xeon`, `results/t14s-ryzen7pro`, `results/legion-i9-14900hx` | Raw CSV results for the three platforms |

## Reproduce
Windows: double-click `RUN-ME.cmd` (or `.\run-all.ps1 -Label <name>`). Linux: `./run_all.sh <name>`.
Analysis: `python analysis/analyze.py results out <primary-label>`.

## License
Code (src/, tools/, analysis/, scripts): MIT License (see LICENSE). Data (results/): Creative Commons Attribution 4.0 International (CC BY 4.0, see results/LICENSE).
