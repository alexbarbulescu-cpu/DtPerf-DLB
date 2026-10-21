# DtPerf-DLB — replication package

Code, raw results and analysis scripts for the manuscript
**"Decision-Latency Budgets in Digital Twins: How Object-Materialization Strategies Bound Fleet Capacity and Decision Quality"**
(A. Bărbulescu, T. F. Furtună, Bucharest University of Economic Studies; submitted to the *Journal of Systems and Software*).

The manuscript cites a specific commit of this repository (see its Data availability section).

## Quick start: regenerate every table and figure (no .NET needed)

```bash
pip install -r requirements.txt     # Python 3.13; exact versions used for the manuscript
./reproduce.sh out                  # writes CSV tables, figures (PNG + PDF), summary.json and summary_v3.json to out/<platform>/
```

`MANIFEST.md` maps every table, figure and in-text statistic of the manuscript to its raw files and to the output of `reproduce.sh`.

## Contents

| Path | What it is |
|---|---|
| `src/` | Strategies S1–S5, control S5b (`GeneratedLookup`), null materializer and synthetic probe (`Materializers.cs`); benchmark harness (`Harness.cs`); microbenchmarks, control suite and snapshot-equivalence check (`MicroBenches.cs`); closed-loop fleet twin (`DtSim.cs`); generated entities and mappers (`*.g.cs`); entry point and modes (`Program.cs`) |
| `tools/gen_entities.py` | Generates the snapshot classes and the source-generator-equivalent mappers (S5 and S5b) |
| `build/jit`, `build/aot` | .NET 8 + .NET 10 JIT project; .NET 10 Native AOT project |
| `run_all.sh` / `run-all.ps1`, `RUN-ME.cmd`, `setup-and-run.ps1` | Build, single-process microbenchmarks and cold-start measurements (Linux / Windows) |
| `run_v2.sh` | Closed-loop protocol v2 on Linux (primary platform): θ calibration, unconstrained references for every fleet size and seed, main grid (5 seeds), synthetic capacity map at B = 10, 5 and 20 ms, depth-only ablation, θ sensitivity. Stages are resumable (`*_DONE` files). |
| `scripts/run_v2_rest.sh` | Completes `run_v2.sh` after an interrupted run (re-adds missing synthetic rows, then resumes); used once on the primary platform |
| `run-sim-v2.ps1`, `RUN-SIM-V2.cmd` | Closed-loop protocol v2 on Windows (references + main grid, 3 seeds) |
| `run_v3.sh` | Revision experiments on the primary platform. Stage A: snapshot-equivalence check, cost per Monte Carlo path, full microbenchmark suite in 10 fresh processes per runtime with per-iteration logs, S4/S5/S5b control and cold-payload suite (3 processes), S5b and null materializer in the closed loop. Stage B: two alternative decision policies with their own references, garbage-collector configurations, 600-cycle horizon, θ below 0.0005. Usage `./run_v3.sh A`, then `./run_v3.sh B`. |
| `scripts/run_gcdiag.sh` | Garbage-collection diagnostic (`results/cloud-xeon/gc_diagnostic.csv`) |
| `analysis/analyze.py`, `analysis/analyze_v3.py` | All tables and figures (called by `reproduce.sh`) |
| `results/<platform>/` | Raw results used in the manuscript (see below) |
| `results_v1_superseded/` | Superseded runs, kept for transparency and **not used** in the manuscript (see below) |
| `scripts/superseded/` | First version of the v2 script (θ selection by minimum cost; not used for the reported data) |

## Raw results

* `results/cloud-xeon/` (primary platform, 2-vCPU cloud VM, Ubuntu 24.04): `micro_*.csv` (first, single-process run of the microbenchmark suite; superseded by `v3/micro_rep/` but used to quantify between-session variation), `cold.csv`, `sim.csv`, `reference.csv`, `calibration.csv`, `theta.txt`, `synthetic.csv`, `ablation.csv`, `sensitivity.csv`, `gc_diagnostic.csv`, `micro20_rep/` (an earlier 5-process repetition of the P = 20 benchmark, superseded by `v3/micro_rep/`), `v3/` (all revision experiments: `micro_rep/`, `microctl/`, `mcbench.csv`, `verify.txt`, `sim_s5b.csv`, `sim_null.csv`, `policy.csv`, `policy_reference.csv`, `gc_modes.csv`, `long.csv`, `calibration_low.csv`).
* `results/legion-i9-14900hx/`, `results/t14s-ryzen7pro/`: single-process microbenchmarks and cold start (measured in a session before the closed-loop runs), closed-loop `sim.csv` and `reference.csv` (3 seeds). On the T14s the closed loop was run twice with the same seeds; `run1/` and `run2/` hold the original files, and the pooled files at the top level number the seeds of run 2 as 11–13 (see `README_T14S.txt`). The manuscript reports the two runs separately.
* Closed-loop CSV files have no header; the columns are `DtSim.Header` in `src/DtSim.cs`, with a leading `Theta`, `K` or `Policy` column where applicable.

## Protocol notes and history

* **Budget.** The budget B covers the whole cycle until decisions are issued; time for screening and decision is reserved from a smoothed estimate of previous cycles. Budget checks are cooperative, so cycles can overrun (reported as latency percentiles and overrun shares).
* **Regret** is computed per seed against an unconstrained reference (B = 1 s, S5, 2,048 paths per candidate) with the same fleet size, seed and decision rule.
* **θ selection.** The first version of the v2 script (`scripts/superseded/run_v2_first_argmin.sh`) selected θ by minimum normalized mean cost, which would have given θ = 0.0005, the lowest value of the original grid. The rule was changed to the one-standard-deviation rule (largest θ within one SD of the minimum at every calibration fleet) while the calibration was running and before the main experiment; it gives θ = 0.001, used throughout. `run_v3.sh B` extends the calibration to θ = 0.0001 and 0.0002.
* **Superseded runs.** `results_v1_superseded/` contains closed-loop results of the first protocol (decision step outside the budget, single reference fleet) on all platforms and the microbenchmarks of a first Legion run; some of those microbenchmarks were up to about 40% slower than the reported ones.
* **Repeated microbenchmarks.** For the primary platform the manuscript reports the median of 10 per-process medians with a distribution-free confidence interval (2nd and 9th order statistics). Per-iteration times are in `v3/micro_rep/iterlog_*.csv` (columns: runtime, category, method, P, iteration, ns/op).
* **Snapshot equivalence.** `DtPerf verify` compares the snapshots produced by all strategies on 3,600 payloads; the result for each runtime is in `results/cloud-xeon/v3/verify.txt`.

## Running the experiments

Linux: `./run_all.sh <label>` (build, microbenchmarks, cold start), then `./run_v2.sh` and `./run_v3.sh A` / `./run_v3.sh B`.
Windows: `RUN-ME.cmd`, then `RUN-SIM-V2.cmd`. Absolute timings are platform- and session-specific; the closed-loop thresholds depend on them.

## License

Code (src/, tools/, analysis/, scripts): MIT License (see LICENSE). Data (results/, results_v1_superseded/): Creative Commons Attribution 4.0 International (CC BY 4.0, see results/LICENSE).
