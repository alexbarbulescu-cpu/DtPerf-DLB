# Manifest: manuscript artefacts → raw files → scripts

`./reproduce.sh out` regenerates all CSV tables and figures below; file names refer to `out/<platform>/`.

| Manuscript | Raw data (results/…) | Produced by | Output |
|---|---|---|---|
| Table 2 (instantiation, set property) | `cloud-xeon/v3/micro_rep/{net8,net10,aot}_{1..10}.csv` | analyze.py | `table_instantiate.csv`, `table_setproperty.csv` |
| Table 3, Figure 2 (materialization) | same | analyze.py | `table_materialize.csv`, `table_materialize_long.csv`, `fig2_materialization.{png,pdf}` |
| Section 4.2 (between-process variation, steady state) | `cloud-xeon/v3/micro_rep/*.csv`, `iterlog_*.csv`; first single-process run `cloud-xeon/micro_*.csv` | analyze_v3.py | `summary_v3.json` (`rep_*`, `ss_*`, `orig_*`) |
| Table 4 (S4/S5b/S5 control, cold payloads) | `cloud-xeon/v3/microctl/*.csv`, `cloud-xeon/v3/sim_s5b.csv` | analyze_v3.py | `table_control_long.csv`, `summary_v3.json` (`ctrl`, `s5b_loop`) |
| Table 5 (cold start, break-even) | `cloud-xeon/cold.csv` | analyze.py | `table_cold.csv` |
| Table 6, Figures 3–4 (closed loop, thresholds) | `cloud-xeon/sim.csv`, `cloud-xeon/reference.csv` | analyze.py, analyze_v3.py | `table_sim.csv`, `table_sim_seed.csv`, `table_capacity.csv`, `table_collapse_seed.csv`, `table_bootstrap.csv`, `fig3_closed_loop.*`, `fig4_whatif_coverage.*` |
| Section 4.6 (deadline compliance, GC) | `cloud-xeon/sim.csv`, `cloud-xeon/gc_diagnostic.csv`, `cloud-xeon/v3/gc_modes.csv` | analyze_v3.py | `table_compliance.csv`, `table_gcmodes.csv` |
| Section 4.7, Figure 5 (depth, ablation, model tests) | `cloud-xeon/sim.csv`, `cloud-xeon/ablation.csv`, `cloud-xeon/reference.csv`, `cloud-xeon/v3/mcbench.csv`, `cloud-xeon/v3/sim_null.csv` | analyze.py, analyze_v3.py | `table_depth.csv`, `table_ablation.csv`, `table_kpred.csv`, `table_onset.csv`, `table_cA.csv`, `fig5_depth_vs_regret.*` |
| Table 7, Section 4.8 (policies, long horizon, θ) | `cloud-xeon/v3/policy.csv`, `policy_reference.csv`, `long.csv`, `calibration_low.csv` | analyze_v3.py | `table_policy.csv`, `table_long.csv`, `table_calibration_all.csv` |
| Tables 8–9 (platforms) | `legion-i9-14900hx/*`, `t14s-ryzen7pro/*` (runs separately in `run1/`, `run2/`) | analyze.py (per platform), analyze_v3.py | `table_materialize_long.csv`, `table_sim.csv` per platform; `summary_v3.json` (`t14s`) |
| Figure 6 (capacity map, held-out budgets) | `cloud-xeon/synthetic.csv`, `cloud-xeon/reference.csv` | analyze.py, analyze_v3.py | `table_synthetic.csv`, `fig6_capacity_map.*`, `summary.json` (`syn_*`), `summary_v3.json` (`map_*`) |
| Appendix A (θ calibration) | `cloud-xeon/calibration.csv`, `cloud-xeon/v3/calibration_low.csv`, `cloud-xeon/theta.txt` | analyze_v3.py | `table_calibration_all.csv` |
| Appendix B (θ sensitivity) | `cloud-xeon/sensitivity.csv`, `cloud-xeon/sim.csv`, `cloud-xeon/reference.csv` | analyze_v3.py | `table_sensitivity.csv` |
| Snapshot equivalence check | `cloud-xeon/v3/verify.txt` | `DtPerf verify` | — |

Raw closed-loop CSV files have no header; columns are `DtSim.Header` in `src/DtSim.cs`, with a leading `Theta`, `K`, or `Policy` column where applicable.
