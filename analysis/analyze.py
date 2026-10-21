"""Tables and figures for the manuscript. Usage: python analyze.py <results_root> <out_dir> [primary_label]"""
import sys, os, glob, json
import pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.figure as _mf
_orig_savefig = _mf.Figure.savefig
def _savefig_also_pdf(self, fname, *a, **k):
    _orig_savefig(self, fname, *a, **k)
    if isinstance(fname, str) and fname.endswith(".png"):
        k2 = {kk: vv for kk, vv in k.items() if kk != "dpi"}; _orig_savefig(self, fname[:-4] + ".pdf", *a, **k2)
_mf.Figure.savefig = _savefig_also_pdf


root, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
labels = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
primary = sys.argv[3] if len(sys.argv) > 3 else labels[0]

STRATS = ["Reflection", "ReflectionInvoker", "CompiledPerProperty", "CompiledWhole", "Generated"]
SLAB = {"Reflection": "S1 Reflection", "ReflectionInvoker": "S2 Reflection invoker", "CompiledPerProperty": "S3 Compiled per property",
        "CompiledWhole": "S4 Compiled whole object", "Generated": "S5 Generated (source-gen equivalent)"}
COL = dict(zip(STRATS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"]))
MRK = dict(zip(STRATS, ["o", "s", "^", "D", "v"]))
LS = dict(zip(STRATS, ["-", "--", "-.", ":", "-"]))
RTS = [".NET 8.0 JIT", ".NET 10.0 JIT", ".NET 10.0 NativeAOT"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": 0.6, "axes.edgecolor": "#8a8984",
                     "axes.labelcolor": "#0b0b0b", "xtick.color": "#52514e", "ytick.color": "#52514e", "legend.frameon": False,
                     "lines.linewidth": 1.6, "lines.markersize": 5, "savefig.dpi": 600})

SIMCOLS = ["Runtime", "Strategy", "Assets", "BudgetMs", "Seed", "Ticks", "CostPer1kAssetTicks", "FailuresPer1k", "PmPer1k", "IngestMs",
           "IngestShare", "DroppedShare", "Candidates", "UnsampledCandShare", "SamplesPerCand", "OverrunShare", "Overrun5Share",
           "CycleP95Ms", "CycleP99Ms", "CycleMaxMs", "ScreenMs", "DecisionMs"]
def readsim(path, prefix=None):
    """Read a closed-loop CSV with or without header; prefix names a leading extra column (e.g. Theta, K)."""
    if not os.path.exists(path) or os.path.getsize(path) < 5: return None
    first = open(path, encoding="utf-8-sig").readline()
    if first.startswith(("Runtime", "Theta")): return pd.read_csv(path, encoding="utf-8-sig")
    names = ([prefix] if prefix else []) + SIMCOLS
    return pd.read_csv(path, header=None, names=names, skip_blank_lines=True, encoding="utf-8-sig")
def load(label, pat):
    fs = glob.glob(os.path.join(root, label, pat))
    if not fs: return None
    d = pd.concat([(readsim(f) if pat.endswith("sim.csv") else pd.read_csv(f)) for f in fs], ignore_index=True); d["Platform"] = label; return d
def paired_regret(cons, ref):
    """Regret (%) of each constrained run relative to the unconstrained reference with the same fleet size and seed."""
    r_ = ref.groupby(["Assets", "Seed"]).CostPer1kAssetTicks.mean().rename("ref_cost").reset_index()
    x = cons.merge(r_, on=["Assets", "Seed"], how="left")
    x["regret_seed"] = 100 * (x.CostPer1kAssetTicks - x.ref_cost) / x.ref_cost
    return x
def sim_and_ref(label):
    s_ = readsim(os.path.join(root, label, "sim.csv"))
    if s_ is None: return None, None
    rf = readsim(os.path.join(root, label, "reference.csv"))
    if rf is None: rf = s_[s_.BudgetMs >= 1000]
    s_ = s_[s_.BudgetMs < 1000]
    return s_, rf

def micro_rep_agg(label):
    """Between-process aggregation of the repeated microbenchmark suite (v3): median of the per-process medians and a distribution-free
    confidence interval for that median from order statistics (for 10 processes: 2nd and 9th value, coverage 97.9%)."""
    fs = sorted(glob.glob(os.path.join(root, label, "v3", "micro_rep", "*_[0-9]*.csv")))
    fs = [f for f in fs if not os.path.basename(f).startswith("iterlog")]
    if len(fs) < 6: return None
    from scipy.stats import binom
    d = pd.concat([pd.read_csv(f).assign(proc=os.path.basename(f)) for f in fs], ignore_index=True)
    rows = []
    for (rt, cat, mth, p_), g in d.groupby(["Runtime", "Category", "Method", "P"], sort=False):
        v = np.sort(g.MedianNs.values); n = len(v); j = 0
        while j + 1 < n // 2 and 1 - 2 * binom.cdf(j + 1, n, 0.5) >= 0.95: j += 1   # [v_j, v_(n-1-j)] covers the median with prob 1 - 2 F(j)
        rows.append({"Runtime": rt, "Category": cat, "Method": mth, "P": p_, "MedianNs": float(np.median(v)), "MeanNs": float(v.mean()),
                     "SdNs": float(v.std(ddof=1)), "CiLoNs": float(v[j]), "CiHiNs": float(v[n - 1 - j]), "Ci95Ns": float((v[n - 1 - j] - v[j]) / 2),
                     "CvPct": float(100 * v.std(ddof=1) / v.mean()), "NProc": n, "AllocBytesPerOp": float(g.AllocBytesPerOp.median())})
    a = pd.DataFrame(rows); a["Platform"] = label; return a
def load_micro(l):
    a = micro_rep_agg(l)
    if a is not None: return a
    x = load(l, "micro_*.csv")
    if x is not None:   # single process: t-interval of the mean over 30 iterations, widened to contain the median
        x["CiLoNs"] = np.minimum(x.MedianNs, x.MeanNs - x.Ci95Ns); x["CiHiNs"] = np.maximum(x.MedianNs, x.MeanNs + x.Ci95Ns); x["NProc"] = 1
    return x
micro = pd.concat([x for x in (load_micro(l) for l in labels) if x is not None], ignore_index=True)
cold = pd.concat([x for x in (load(l, "cold.csv") for l in labels) if x is not None], ignore_index=True)
sim_labels = [l for l in labels if sim_and_ref(l)[0] is not None]
summary = {"platforms": labels, "primary": primary}

# ---------- Table: instantiation and setters (primary platform) ----------
def fmt(m, lo, hi):
    d = 1 if hi < 100 else 0
    return f"{m:.{d}f} ({lo:.{d}f}–{hi:.{d}f})"
mp = micro[micro.Platform == primary]
for cat in ["Instantiate", "SetProperty"]:
    t = mp[mp.Category == cat].copy(); t["v"] = [fmt(a, b, c) for a, b, c in zip(t.MedianNs, t.CiLoNs, t.CiHiNs)]
    tab = t.pivot_table(index="Method", columns="Runtime", values="v", aggfunc="first", sort=False)[RTS]
    tab.to_csv(f"{out}/table_{cat.lower()}.csv")
# ---------- Table: materialization ns/op and speed-up vs S1 ----------
m = mp[mp.Category == "Materialize"].copy()
rows = []
for (rt, p), g in m.groupby(["Runtime", "P"]):
    base = g[g.Method == "Reflection"].MedianNs.iloc[0]
    for _, r in g.iterrows():
        rows.append({"Runtime": rt, "P": p, "Strategy": r.Method, "ns/op": r.MedianNs, "mean": r.MeanNs, "CI95": r.Ci95Ns,
                     "lo": r.CiLoNs, "hi": r.CiHiNs, "x vs S1": base / r.MedianNs, "B/op": r.AllocBytesPerOp})
mat = pd.DataFrame(rows); mat.to_csv(f"{out}/table_materialize_long.csv", index=False)
wide = mat.assign(cell=[f"{a:,.0f} ({x:.2f}×)" for a, x in zip(mat["ns/op"], mat["x vs S1"])]) \
    .pivot_table(index=["P", "Strategy"], columns="Runtime", values="cell", aggfunc="first")[RTS]
wide = wide.reindex(pd.MultiIndex.from_product([[5, 20, 50], STRATS])); wide.to_csv(f"{out}/table_materialize.csv")
# ---------- Cold start & break-even ----------
cp = cold[cold.Platform == primary]
cs = cp.groupby(["Runtime", "P", "Strategy"])[["BuildMs", "FirstCallMs", "SecondCallMs"]].median().reset_index()
be = []
for _, r in cs.iterrows():
    s1 = mat[(mat.Runtime == r.Runtime) & (mat.P == r.P) & (mat.Strategy == "Reflection")]
    sx = mat[(mat.Runtime == r.Runtime) & (mat.P == r.P) & (mat.Strategy == r.Strategy)]
    s1c = cs[(cs.Runtime == r.Runtime) & (cs.P == r.P) & (cs.Strategy == "Reflection")]
    if len(s1) and len(sx) and len(s1c):
        dsteady = s1["ns/op"].iloc[0] - sx["ns/op"].iloc[0]                                  # ns saved per op
        dcold = (r.BuildMs + r.FirstCallMs + r.SecondCallMs) - (s1c.BuildMs.iloc[0] + s1c.FirstCallMs.iloc[0] + s1c.SecondCallMs.iloc[0])  # ms extra at start
        be.append({"Runtime": r.Runtime, "P": r.P, "Strategy": r.Strategy, "BuildMs": r.BuildMs, "FirstCallMs": r.FirstCallMs,
                   "SecondCallMs": r.SecondCallMs, "ExtraColdMs": dcold, "SavedNsPerOp": dsteady,
                   "BreakEvenOps": (dcold * 1e6 / dsteady) if (dsteady > 0 and dcold > 0) else (0 if dsteady > 0 else np.inf)})
be = pd.DataFrame(be); be.to_csv(f"{out}/table_cold.csv", index=False)

# ---------- Figure 2: materialization cost vs P ----------
fig, axs = plt.subplots(1, 3, figsize=(7.2, 2.6), sharey=True)
for ax, rt in zip(axs, RTS):
    g = mat[mat.Runtime == rt]
    for s in STRATS:
        h = g[g.Strategy == s].sort_values("P")
        ax.errorbar(h.P, h["ns/op"], yerr=[h["ns/op"] - h.lo, h.hi - h["ns/op"]], color=COL[s], marker=MRK[s], ls=LS[s], label=SLAB[s], capsize=2)
    ax.set_yscale("log"); ax.set_xticks([5, 20, 50]); ax.set_title(rt, fontsize=9); ax.set_xlabel("Properties per snapshot (P)")
axs[0].set_ylabel("ns per snapshot (median, log)")
h, l = axs[0].get_legend_handles_labels(); fig.legend(h, l, loc="lower center", ncol=3, fontsize=7.5, bbox_to_anchor=(0.5, -0.08))
fig.tight_layout(rect=(0, 0.12, 1, 1)); fig.savefig(f"{out}/fig2_materialization.png", bbox_inches="tight"); plt.close(fig)

# ---------- Simulation ----------
json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)
cons, ref = sim_and_ref(primary)
if cons is None:
    sys.exit(0)  # platform with microbenchmarks only
FLEETS = sorted(cons.Assets.unique())
refagg = ref.groupby("Assets").agg(ref_cost=("CostPer1kAssetTicks", "mean"), ref_sd=("CostPer1kAssetTicks", "std"),
                                   ref_fail=("FailuresPer1k", "mean"), ref_pm=("PmPer1k", "mean")).reset_index()
refagg.to_csv(f"{out}/table_reference.csv", index=False)
summary.update({"unconstrained_cost_mean": float(ref.CostPer1kAssetTicks.mean()), "unconstrained_cost_sd": float(ref.CostPer1kAssetTicks.std()),
                "ref_cost_min": float(refagg[refagg.Assets.isin(FLEETS)].ref_cost.min()), "ref_cost_max": float(refagg[refagg.Assets.isin(FLEETS)].ref_cost.max()),
                "ref_pm_mean": float(ref.PmPer1k.mean()), "ref_fail_mean": float(ref.FailuresPer1k.mean()), "n_seeds": int(cons.Seed.nunique())})
pr = paired_regret(cons, ref); pr.to_csv(f"{out}/table_sim_seed.csv", index=False)
has = lambda c: c in pr.columns and pr[c].notna().any()
aggspec = dict(cost=("CostPer1kAssetTicks", "mean"), cost_sd=("CostPer1kAssetTicks", "std"), fail=("FailuresPer1k", "mean"),
    pm=("PmPer1k", "mean"), ingest_ms=("IngestMs", "mean"), share=("IngestShare", "mean"), dropped=("DroppedShare", "mean"),
    unsampled=("UnsampledCandShare", "mean"), samples=("SamplesPerCand", "mean"), n=("Seed", "count"), Candidates=("Candidates", "mean"),
    regret_pct=("regret_seed", "mean"), regret_sd=("regret_seed", "std"), regret_min=("regret_seed", "min"), regret_max=("regret_seed", "max"),
    ref_cost=("ref_cost", "mean"))
for c_ in ["Overrun5Share", "CycleP95Ms", "CycleP99Ms", "CycleMaxMs", "ScreenMs", "DecisionMs", "OverrunShare"]:
    if has(c_): aggspec[c_] = (c_, "mean")
agg = pr.groupby(["Runtime", "Strategy", "Assets"]).agg(**aggspec).reset_index()
agg.to_csv(f"{out}/table_sim.csv", index=False)
# per-seed collapse fleet (first fleet with regret > 100 % in that seed)
pc = []
for (rt, st, sd), g in pr.groupby(["Runtime", "Strategy", "Seed"]):
    g = g.sort_values("Assets"); bad = g[g.regret_seed > 100].Assets
    pc.append({"Runtime": rt, "Strategy": st, "Seed": sd, "collapse_fleet": int(bad.iloc[0]) if len(bad) else np.nan})
pd.DataFrame(pc).to_csv(f"{out}/table_collapse_seed.csv", index=False)
# capacity and per-asset costs (sync, screening) from runs that were not budget-limited
cap = []
for (rt, st), g in agg.groupby(["Runtime", "Strategy"]):
    ok = g[g.regret_pct <= 10].Assets; nb = g[(g.share < 0.95) & (g.dropped < 0.05)]   # per processed message
    cap.append({"Runtime": rt, "Strategy": st, "MaxFleetRegretLe10": int(ok.max()) if len(ok) else 0,
                "PerAssetIngestUs": float((nb.ingest_ms / (nb.Assets * (1 - nb.dropped)) * 1000).median()) if len(nb) else np.nan,
                "PerAssetScreenUs": float((nb.ScreenMs / nb.Assets * 1000).median()) if (len(nb) and "ScreenMs" in nb) else np.nan,
                "DecisionMs": float(nb.DecisionMs.median()) if (len(nb) and "DecisionMs" in nb) else np.nan})
pd.DataFrame(cap).to_csv(f"{out}/table_capacity.csv", index=False)
if "CycleP99Ms" in agg:
    summary.update({"cyc_p95_med": float(agg.CycleP95Ms.median()), "cyc_p95_max": float(agg.CycleP95Ms.max()),
                    "cyc_p99_med": float(agg.CycleP99Ms.median()), "cyc_p99_max": float(agg.CycleP99Ms.max()),
                    "cyc_max_max": float(agg.CycleMaxMs.max()), "ovr5_mean": float(agg.Overrun5Share.mean()),
                    "ovr5_max": float(agg.Overrun5Share.max()), "screen_us_med": float(np.nanmedian([c["PerAssetScreenUs"] for c in cap])),
                    "dec_ms_med": float(np.nanmedian([c["DecisionMs"] for c in cap]))})
    agg.groupby(["Runtime", "Strategy"]).agg(p95=("CycleP95Ms", "median"), p99=("CycleP99Ms", "median"), p99max=("CycleP99Ms", "max"),
        mx=("CycleMaxMs", "max"), ovr5=("Overrun5Share", "mean")).reset_index().to_csv(f"{out}/table_latency.csv", index=False)

rts_present = [r for r in RTS if r in set(agg.Runtime)]
_rng = np.random.default_rng(20261020)
def _boot_ci(v, n=2000):
    v = np.asarray(v, float)
    if len(v) < 2: return (v.mean(), v.mean())
    m = _rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1); return tuple(np.percentile(m, [2.5, 97.5]))
bci = pr.groupby(["Runtime", "Strategy", "Assets"]).regret_seed.apply(lambda v: _boot_ci(v.values)).rename("ci").reset_index()
agg = agg.merge(bci, on=["Runtime", "Strategy", "Assets"], how="left")
agg["regret_lo"] = [c[0] for c in agg.ci]; agg["regret_hi"] = [c[1] for c in agg.ci]; agg = agg.drop(columns="ci")
agg.to_csv(f"{out}/table_sim.csv", index=False)
fig, axs = plt.subplots(2, len(rts_present), figsize=(2.5 * len(rts_present) + 0.6, 4.8), sharex=True, sharey="row", squeeze=False)
for j, rt in enumerate(rts_present):
    g = agg[agg.Runtime == rt]
    for s in STRATS:
        h = g[g.Strategy == s].sort_values("Assets")
        axs[0, j].errorbar(h.Assets / 1000, h.regret_pct, yerr=[h.regret_pct - h.regret_lo, h.regret_hi - h.regret_pct], color=COL[s], marker=MRK[s],
                           ls=LS[s], label=SLAB[s], capsize=2)
        axs[1, j].plot(h.Assets / 1000, 100 * h.share, color=COL[s], marker=MRK[s], ls=LS[s])
    axs[0, j].set_yscale("symlog", linthresh=10); axs[0, j].axhline(10, color="#52514e", lw=0.8, ls=(0, (4, 3)))
    axs[0, j].axhline(100, color="#52514e", lw=0.8, ls=(0, (1, 2)))
    axs[1, j].axhline(100, color="#52514e", lw=0.8, ls=(0, (4, 3)))
    axs[0, j].set_title(rt, fontsize=9); axs[1, j].set_xlabel("Fleet size (thousand assets)")
axs[0, 0].set_yticks([0, 10, 100, 500]); axs[0, 0].set_yticklabels(["0", "10", "100", "500"])
axs[0, 0].set_ylabel("Regret vs. unconstrained\ntwin (%, symlog)"); axs[1, 0].set_ylabel("Synchronization time\n(% of budget B)")
h, l = axs[0, 0].get_legend_handles_labels(); fig.legend(h, l, loc="lower center", ncol=3, fontsize=7.5, bbox_to_anchor=(0.5, -0.06))
fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig(f"{out}/fig3_closed_loop.png", bbox_inches="tight"); plt.close(fig)

fig, ax = plt.subplots(figsize=(3.6, 3.3))
g = agg[agg.Runtime == ".NET 10.0 JIT"]
for s in STRATS:
    h = g[g.Strategy == s].sort_values("Assets")
    ax.plot(h.Assets / 1000, 100 * (1 - h.unsampled), color=COL[s], marker=MRK[s], ls=LS[s], label=SLAB[s])
ax.set_xlabel("Fleet size (thousand assets)"); ax.set_ylabel("At-risk assets with what-if\nevidence (%)"); ax.set_ylim(0, 105)
ax.legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.45, -0.22), ncol=2); fig.tight_layout(); fig.savefig(f"{out}/fig4_whatif_coverage.png", bbox_inches="tight"); plt.close(fig)

# ---------- association between analysis depth and regret (+ depth-only ablation) ----------
from scipy.stats import spearmanr
dd = agg[agg.samples > 0].copy()
yv = np.log(dd.regret_pct.clip(lower=0.5) + 1)
def _r2(X):
    b, *_ = np.linalg.lstsq(X, yv, rcond=None); r = yv - X @ b; return float(1 - r.var() / yv.var())
X1 = np.column_stack([np.ones(len(dd)), np.log(dd.samples)])
Dm = pd.get_dummies(dd[["Strategy", "Runtime"]], drop_first=True).astype(float).values
XA = np.log(dd.Assets.values)
summary.update({"med_n": int(len(dd)), "med_n_zero": int((agg.samples <= 0).sum()),
                "med_rho": float(spearmanr(dd.samples, dd.regret_pct).correlation),
                "med_r2_k": _r2(X1), "med_r2_k_sr": _r2(np.column_stack([X1, Dm])),
                "med_r2_sr": _r2(np.column_stack([np.ones(len(dd)), Dm])),
                "med_r2_a": _r2(np.column_stack([np.ones(len(dd)), XA])), "med_r2_ka": _r2(np.column_stack([X1, XA]))})
# partial Spearman correlation of K and regret controlling for fleet size (rank residuals)
from scipy.stats import rankdata
def _res(y, x): X = np.column_stack([np.ones(len(x)), x]); b, *_ = np.linalg.lstsq(X, y, rcond=None); return y - X @ b
ra_, rk_, rg_ = rankdata(dd.Assets), rankdata(dd.samples), rankdata(dd.regret_pct)
summary["med_rho_partial_a"] = float(np.corrcoef(_res(rk_, ra_), _res(rg_, ra_))[0, 1])
abl = readsim(os.path.join(root, primary, "ablation.csv"), prefix="K")
abl_curve = None
if abl is not None:
    ab = paired_regret(abl, ref)
    abl_curve = ab.groupby(["K", "Assets"]).agg(regret=("regret_seed", "mean"), samples=("SamplesPerCand", "mean")).reset_index()
    abl_curve.to_csv(f"{out}/table_ablation.csv", index=False)
    # predict constrained regret from the ablation at the same fleet size and analysis depth (interpolation in log K)
    pred = []
    for _, r in dd.iterrows():
        c_ = abl_curve[abl_curve.Assets == r.Assets].sort_values("samples")
        if len(c_) < 2: pred.append(np.nan); continue
        pred.append(float(np.expm1(np.interp(np.log(r.samples), np.log(c_.samples), np.log1p(c_.regret.clip(lower=0))))))
    dd["abl_pred"] = pred; kmin = float(abl_curve.samples.min())
    ok = dd.abl_pred.notna() & (dd.samples >= kmin)   # compare only within the ablated range of K (no extrapolation)
    lowk = dd[dd.samples < kmin]
    summary.update({"abl_kmin": kmin, "abl_low_n": int(len(lowk)), "abl_low_regret_min": float(lowk.regret_pct.min()) if len(lowk) else float("nan"),
                    "abl_low_regret_med": float(lowk.regret_pct.median()) if len(lowk) else float("nan"),
                    "abl_regret_at_kmin": float(abl_curve[abl_curve.K == abl_curve.K.min()].regret.mean()),
                    "abl_fleet_spread": float(abl_curve.groupby("K").regret.agg(lambda v: v.max() - v.min()).max())})
    yo, yp = np.log1p(dd.regret_pct.clip(lower=0)[ok]), np.log1p(dd.abl_pred[ok])
    summary.update({"abl_r2": float(1 - ((yo - yp) ** 2).sum() / ((yo - yo.mean()) ** 2).sum()),
                    "abl_mad_pp": float((dd.regret_pct[ok] - dd.abl_pred[ok]).abs().median()),
                    "abl_excess_med": float((dd.regret_pct[ok] - dd.abl_pred[ok]).median()),
                    "abl_n": int(ok.sum())})
    dd.to_csv(f"{out}/table_depth.csv", index=False)
RM = {".NET 8.0 JIT": "o", ".NET 10.0 JIT": "s", ".NET 10.0 NativeAOT": "^"}
fig, ax = plt.subplots(figsize=(5.2, 3.4))
if abl_curve is not None:
    ac = abl_curve.groupby("K").agg(lo=("regret", "min"), hi=("regret", "max"), med=("regret", "median"), k=("samples", "mean")).reset_index()
    ax.fill_between(ac.k, ac.lo.clip(lower=0.5), ac.hi.clip(lower=0.5), color="#c9c7c1", alpha=0.6, lw=0, zorder=1)
    ax.plot(ac.k, ac.med.clip(lower=0.5), color="#52514e", lw=1.2, zorder=2)
for s in STRATS:
    for rt in RTS:
        h = dd[(dd.Strategy == s) & (dd.Runtime == rt)]
        if len(h): ax.scatter(h.samples, h.regret_pct.clip(lower=0.5), color=COL[s], marker=RM[rt], s=26, edgecolor="white", linewidth=0.6, zorder=3)
ax.set_xscale("log"); ax.set_yscale("log")
ax.axhline(10, color="#52514e", lw=0.9, ls=(0, (4, 3))); ax.axhline(100, color="#52514e", lw=0.9, ls=(0, (1, 2)))
ax.text(0.02, 11.5, "10% regret", fontsize=7, color="#52514e", ha="left", transform=ax.get_yaxis_transform()); ax.text(0.02, 115, "cost doubled (100%)", fontsize=7, color="#52514e", ha="left", transform=ax.get_yaxis_transform())
ax.set_xlabel("Monte Carlo samples per candidate asset (K, log)"); ax.set_ylabel("Regret vs. unconstrained twin (%, log)")
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
hs = [Line2D([], [], color=COL[s], marker="o", ls="", label=SLAB[s].split(" (")[0]) for s in STRATS] + \
     [Line2D([], [], color="#52514e", marker=RM[rt], ls="", mfc="white", label=rt) for rt in RTS]
if abl_curve is not None:
    hs += [Patch(color="#c9c7c1", label="Ablation: fixed K, no time limit\n(range over fleet sizes; line: median)")]
ax.legend(handles=hs, fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
fig.tight_layout(); fig.savefig(f"{out}/fig5_depth_vs_regret.png", bbox_inches="tight"); plt.close(fig)
json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)

# ---------- Figure 6: technology-agnostic capacity map (synthetic per-message cost sweep) + held-out budgets ----------
sy = readsim(os.path.join(root, primary, "synthetic.csv"))
if sy is not None:
    from matplotlib.colors import ListedColormap, BoundaryNorm
    sy["extra"] = sy.Strategy.str.replace("Synthetic", "").astype(int)
    sy = paired_regret(sy, ref)
    sga = sy.groupby(["BudgetMs", "extra", "Assets"]).agg(cost=("CostPer1kAssetTicks", "mean"), ingest=("IngestMs", "mean"), share=("IngestShare", "mean"),
            dropped=("DroppedShare", "mean"),
            samples=("SamplesPerCand", "mean"), regret=("regret_seed", "mean"), scr=("ScreenMs", "mean"), dec=("DecisionMs", "mean")).reset_index()
    s10 = sga[sga.BudgetMs == 10]
    # per-message synchronization cost of each level and per-asset screening / decision time, estimated at B = 10 ms only
    nb = s10[(s10.share < 0.9) & (s10.dropped < 0.05)]
    cl = nb.assign(c=lambda d: d.ingest / (d.Assets * (1 - d.dropped)) * 1000).groupby("extra").c.median()
    c_scr = float((nb.scr / nb.Assets * 1000).median()); t_dec = float(nb.dec.median())
    sga["c_us"] = sga.extra.map(cl); sga.to_csv(f"{out}/table_synthetic.csv", index=False)
    def astar_full(B, c): return (B - t_dec) * 1000 / (c + c_scr)
    def astar_sync(B, c): return B * 1000 / c
    res = {}
    for B, g in sga.groupby("BudgetMs"):
        for nm_, f_ in [("full", astar_full), ("sync", astar_sync)]:
            agree = tot_ = 0
            for _, r in g.iterrows():
                tot_ += 1; agree += int((r.Assets > f_(B, r.c_us)) == (r.regret > 100))
            res[f"syn_{nm_}_B{B:g}"] = (agree, tot_)
    summary.update({"syn_c_scr_us": c_scr, "syn_t_dec_ms": t_dec, "syn_budgets": sorted(float(b) for b in sga.BudgetMs.unique())})
    sga["pred_full"] = astar_full(sga.BudgetMs, sga.c_us)
    wrong = sga[(sga.Assets > sga.pred_full) != (sga.regret > 100)]
    early = wrong[wrong.regret > 100]
    summary.update({"syn_err_total": int(len(wrong)), "syn_err_early": int(len(early)),
                    "syn_err_ratio_min": float((early.Assets / early.pred_full).min()) if len(early) else float("nan"),
                    "syn_err_ratio_max": float((early.Assets / early.pred_full).max()) if len(early) else float("nan")})
    for k_, (a_, t_) in res.items(): summary[k_ + "_agree"] = a_; summary[k_ + "_total"] = t_
    summary["syn_agree"], summary["syn_total"] = res["syn_full_B10"]
    levels = sorted(s10.extra.unique()); fl = sorted(s10.Assets.unique())
    cvals = np.array([cl[e] for e in levels])
    def edges(v):
        lv = np.log(v); mid = (lv[1:] + lv[:-1]) / 2
        return np.exp(np.concatenate([[lv[0] - (mid[0] - lv[0])], mid, [lv[-1] + (lv[-1] - mid[-1])]]))
    xe, ye = edges(cvals), edges(np.array(fl, float))
    Z = np.full((len(fl), len(levels)), np.nan)
    for i, a in enumerate(fl):
        for j, e in enumerate(levels):
            r = s10[(s10.Assets == a) & (s10.extra == e)]
            if len(r): Z[i, j] = r.regret.iloc[0]
    band = np.digitize(Z, [10, 100])
    cmap = ListedColormap(["#d6e6f8", "#7fb0ea", "#1f5ea8"]); norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.pcolormesh(xe, ye, band, cmap=cmap, norm=norm, edgecolors="white", linewidth=1.5)
    for i, a in enumerate(fl):
        for j, e in enumerate(levels):
            if np.isfinite(Z[i, j]):
                xl = np.exp(np.log(xe[j]) + 0.08 * (np.log(xe[j + 1]) - np.log(xe[j])))
                ax.text(xl, a, f"{Z[i, j]:.0f}", ha="left", va="center", fontsize=5.6, color="white" if band[i, j] == 2 else "#0b0b0b")
    xs = np.geomspace(xe[0], xe[-1], 100)
    ax.plot(xs, astar_full(10, xs), color="#eb6834", lw=1.8)
    ax.plot(xs, astar_sync(10, xs), color="#eb6834", lw=1.0, ls=(0, (4, 3)))
    REALM = {".NET 8.0 JIT": "o", ".NET 10.0 JIT": "s", ".NET 10.0 NativeAOT": "^"}
    for lab in [primary]:
        cs_, rf_ = sim_and_ref(lab); x_ = paired_regret(cs_, rf_)
        ra = x_.groupby(["Runtime", "Strategy", "Assets"]).agg(reg=("regret_seed", "mean"), ing=("IngestMs", "mean"), sh=("IngestShare", "mean"),
                                                               dr=("DroppedShare", "mean")).reset_index()
        for (rt, st), g_ in ra.groupby(["Runtime", "Strategy"]):
            ok = g_[(g_.sh < 0.95) & (g_.dr < 0.05)]
            if not len(ok): continue
            c_ = float((ok.ing / (ok.Assets * (1 - ok.dr)) * 1000).median())
            g_ = g_.sort_values("Assets"); bad = g_[g_.reg > 100]
            if not len(bad): continue
            hi = bad.Assets.iloc[0]; lo = g_[g_.Assets < hi].Assets.max() if (g_.Assets < hi).any() else hi / 2
            ax.errorbar(c_, np.sqrt(lo * hi), yerr=[[np.sqrt(lo * hi) - lo], [hi - np.sqrt(lo * hi)]], fmt=REALM.get(rt, "o"),
                        color="#0b0b0b", mfc="white", ms=5, lw=0.8, capsize=2, zorder=5)
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlim(xe[0], xe[-1]); ax.set_ylim(ye[0], ye[-1])
    from matplotlib.ticker import NullFormatter, FixedLocator, NullLocator
    ax.xaxis.set_major_locator(FixedLocator(cvals)); ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{v:.2f}" for v in cvals]); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_locator(FixedLocator(fl)); ax.yaxis.set_minor_locator(NullLocator()); ax.set_yticklabels([f"{a / 1000:g}k" for a in fl])
    ax.set_xlabel("Synchronization cost per message, c (µs, log)"); ax.set_ylabel("Fleet size A (assets, log)"); ax.grid(False)
    hs = [Patch(color="#d6e6f8", label="Regret ≤ 10%"), Patch(color="#7fb0ea", label="Regret 10–100% (degraded)"),
          Patch(color="#1f5ea8", label="Regret > 100% (collapsed)"),
          Line2D([], [], color="#eb6834", lw=1.8, label="Equation (4): $(B-T_{dec})/(c+c_s)$"),
          Line2D([], [], color="#eb6834", lw=1.0, ls=(0, (4, 3)), label="Sync-only bound $B/c$\n(nearly coincides with Eq. (4))"),
          Line2D([], [], color="#0b0b0b", marker="s", ls="", mfc="white", label="Measured strategy, .NET 10 JIT"),
          Line2D([], [], color="#0b0b0b", marker="o", ls="", mfc="white", label="Measured strategy, .NET 8 JIT"),
          Line2D([], [], color="#0b0b0b", marker="^", ls="", mfc="white", label="Measured strategy, Native AOT")]
    ax.legend(handles=hs, fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout(); fig.savefig(f"{out}/fig6_capacity_map.png", bbox_inches="tight"); plt.close(fig)
    summary.update({"syn_c_min": float(cvals.min()), "syn_c_max": float(cvals.max())})
json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)
