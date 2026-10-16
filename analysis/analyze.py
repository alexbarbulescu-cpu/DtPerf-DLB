"""Tables and figures for the manuscript. Usage: python analyze.py <results_root> <out_dir> [primary_label]"""
import sys, os, glob, json
import pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

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

def load(label, pat):
    fs = glob.glob(os.path.join(root, label, pat))
    if not fs: return None
    d = pd.concat([pd.read_csv(f) for f in fs], ignore_index=True); d["Platform"] = label; return d

micro = pd.concat([x for x in (load(l, "micro_*.csv") for l in labels) if x is not None], ignore_index=True)
cold = pd.concat([x for x in (load(l, "cold.csv") for l in labels) if x is not None], ignore_index=True)
sim = pd.concat([x for x in (load(l, "sim.csv") for l in labels) if x is not None], ignore_index=True)
summary = {"platforms": labels, "primary": primary}

# ---------- Table: instantiation and setters (primary platform) ----------
def fmt(m, ci): return f"{m:.1f} ± {ci:.1f}" if m < 100 else f"{m:.0f} ± {ci:.0f}"
mp = micro[micro.Platform == primary]
for cat in ["Instantiate", "SetProperty"]:
    t = mp[mp.Category == cat].copy(); t["v"] = [fmt(a, b) for a, b in zip(t.MedianNs, t.Ci95Ns)]
    tab = t.pivot_table(index="Method", columns="Runtime", values="v", aggfunc="first", sort=False)[RTS]
    tab.to_csv(f"{out}/table_{cat.lower()}.csv")
# ---------- Table: materialization ns/op and speed-up vs S1 ----------
m = mp[mp.Category == "Materialize"].copy()
rows = []
for (rt, p), g in m.groupby(["Runtime", "P"]):
    base = g[g.Method == "Reflection"].MedianNs.iloc[0]
    for _, r in g.iterrows():
        rows.append({"Runtime": rt, "P": p, "Strategy": r.Method, "ns/op": r.MedianNs, "CI95": r.Ci95Ns,
                     "x vs S1": base / r.MedianNs, "B/op": r.AllocBytesPerOp})
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
        ax.errorbar(h.P, h["ns/op"], yerr=h.CI95, color=COL[s], marker=MRK[s], ls=LS[s], label=SLAB[s], capsize=2)
    ax.set_yscale("log"); ax.set_xticks([5, 20, 50]); ax.set_title(rt, fontsize=9); ax.set_xlabel("Properties per snapshot (P)")
axs[0].set_ylabel("ns per snapshot (median, log)")
h, l = axs[0].get_legend_handles_labels(); fig.legend(h, l, loc="lower center", ncol=3, fontsize=7.5, bbox_to_anchor=(0.5, -0.08))
fig.tight_layout(rect=(0, 0.12, 1, 1)); fig.savefig(f"{out}/fig2_materialization.png", bbox_inches="tight"); plt.close(fig)

# ---------- Simulation ----------
sp = sim[sim.Platform == primary]
ref = sp[sp.BudgetMs >= 1000]; cons = sp[sp.BudgetMs < 1000]
ref_cost = ref.CostPer1kAssetTicks.mean(); summary["unconstrained_cost_mean"] = ref_cost
summary["unconstrained_cost_sd"] = ref.CostPer1kAssetTicks.std()
agg = cons.groupby(["Runtime", "Strategy", "Assets"]).agg(
    cost=("CostPer1kAssetTicks", "mean"), cost_sd=("CostPer1kAssetTicks", "std"), fail=("FailuresPer1k", "mean"),
    pm=("PmPer1k", "mean"), ingest_ms=("IngestMs", "mean"), share=("IngestShare", "mean"), dropped=("DroppedShare", "mean"),
    unsampled=("UnsampledCandShare", "mean"), samples=("SamplesPerCand", "mean"), n=("Seed", "count")).reset_index()
agg["regret_pct"] = 100 * (agg.cost - ref_cost) / ref_cost
agg.to_csv(f"{out}/table_sim.csv", index=False)
# capacity: largest fleet with regret <= 10 %
cap = []
for (rt, s), g in agg.groupby(["Runtime", "Strategy"]):
    ok = g[g.regret_pct <= 10].Assets; cap.append({"Runtime": rt, "Strategy": s, "MaxFleetRegretLe10": int(ok.max()) if len(ok) else 0,
                                                  "PerAssetIngestUs": float((g.ingest_ms / g.Assets * 1000)[g.share < 0.95].median()) if (g.share < 0.95).any() else np.nan})
pd.DataFrame(cap).to_csv(f"{out}/table_capacity.csv", index=False)

rts_present = [r for r in RTS if r in set(agg.Runtime)]
fig, axs = plt.subplots(2, len(rts_present), figsize=(2.5 * len(rts_present) + 0.6, 4.6), sharex=True, sharey="row", squeeze=False)
for j, rt in enumerate(rts_present):
    g = agg[agg.Runtime == rt]
    for s in STRATS:
        h = g[g.Strategy == s].sort_values("Assets")
        axs[0, j].errorbar(h.Assets / 1000, h.cost, yerr=h.cost_sd, color=COL[s], marker=MRK[s], ls=LS[s], label=SLAB[s], capsize=2)
        axs[1, j].plot(h.Assets / 1000, 100 * h.share.clip(upper=1.0), color=COL[s], marker=MRK[s], ls=LS[s])
    axs[0, j].axhline(ref_cost, color="#52514e", lw=1, ls=(0, (4, 3)), label="Unconstrained twin (reference)"); axs[0, j].set_title(rt, fontsize=9)
    axs[1, j].set_xlabel("Fleet size (thousand assets)"); axs[1, j].set_ylim(0, 105)
axs[0, 0].set_ylabel("Maintenance cost per\n1000 asset-cycles"); axs[1, 0].set_ylabel("Budget consumed by\ningest+materialize (%)")
h, l = axs[0, 0].get_legend_handles_labels(); fig.legend(h, l, loc="lower center", ncol=3, fontsize=7.5, bbox_to_anchor=(0.5, -0.06))
fig.tight_layout(rect=(0, 0.07, 1, 1)); fig.savefig(f"{out}/fig3_closed_loop.png", bbox_inches="tight"); plt.close(fig)

# what-if depth panel
fig, ax = plt.subplots(figsize=(3.6, 3.3))
g = agg[agg.Runtime == ".NET 10.0 JIT"]
for s in STRATS:
    h = g[g.Strategy == s].sort_values("Assets")
    ax.plot(h.Assets / 1000, 100 * (1 - h.unsampled), color=COL[s], marker=MRK[s], ls=LS[s], label=SLAB[s])
ax.set_xlabel("Fleet size (thousand assets)"); ax.set_ylabel("At-risk assets with what-if\nevidence (%)"); ax.set_ylim(0, 105)
ax.legend(fontsize=6.5, loc="upper center", bbox_to_anchor=(0.45, -0.22), ncol=2); fig.tight_layout(); fig.savefig(f"{out}/fig4_whatif_coverage.png", bbox_inches="tight"); plt.close(fig)

# ---------- cross-platform robustness (S1 vs S4 vs S5 materialization P=20) ----------
xp = micro[(micro.Category == "Materialize") & (micro.P == 20)].pivot_table(index=["Platform", "Runtime"], columns="Method", values="MedianNs")
xp.to_csv(f"{out}/table_crossplatform_p20.csv")
json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)
print(json.dumps(summary, indent=1, default=float))

# ---------- Figure 5 + mediation statistics: analysis depth (samples per candidate) vs regret ----------
from scipy.stats import spearmanr
dd = agg[agg.samples > 0].copy()
yv = np.log(dd.regret_pct.clip(lower=0.5) + 1)
def _r2(X):
    b, *_ = np.linalg.lstsq(X, yv, rcond=None); r = yv - X @ b; return float(1 - r.var() / yv.var())
X1 = np.column_stack([np.ones(len(dd)), np.log(dd.samples)])
Dm = pd.get_dummies(dd[["Strategy", "Runtime"]], drop_first=True).astype(float).values
summary.update({"med_n": int(len(dd)), "med_n_zero": int((agg.samples <= 0).sum()),
                "med_rho": float(spearmanr(dd.samples, dd.regret_pct).correlation),
                "med_r2_k": _r2(X1), "med_r2_k_sr": _r2(np.column_stack([X1, Dm])),
                "med_r2_sr": _r2(np.column_stack([np.ones(len(dd)), Dm]))})
RM = dict(zip(RTS, ["o", "s", "^"]))
fig, ax = plt.subplots(figsize=(5.2, 3.4))
for s in STRATS:
    for rt in RTS:
        h = dd[(dd.Strategy == s) & (dd.Runtime == rt)]
        if len(h): ax.scatter(h.samples, h.regret_pct.clip(lower=0.5), color=COL[s], marker=RM[rt], s=26, edgecolor="white", linewidth=0.6, zorder=3)
ax.set_xscale("log"); ax.set_yscale("log")
ax.axhline(REG_TOL := 10, color="#52514e", lw=0.9, ls=(0, (4, 3))); ax.axhline(100, color="#52514e", lw=0.9, ls=(0, (1, 2)))
ax.text(0.98, 11.5, "10% regret", fontsize=7, color="#52514e", ha="right", transform=ax.get_yaxis_transform()); ax.text(0.98, 115, "cost doubled (100%)", fontsize=7, color="#52514e", ha="right", transform=ax.get_yaxis_transform())
ax.set_xlabel("Monte Carlo samples per candidate asset (K, log)"); ax.set_ylabel("Regret vs. unconstrained twin (%, log)")
from matplotlib.lines import Line2D
hs = [Line2D([], [], color=COL[s], marker="o", ls="", label=SLAB[s].split(" (")[0]) for s in STRATS] + \
     [Line2D([], [], color="#52514e", marker=RM[rt], ls="", mfc="white", label=rt) for rt in RTS]
ax.legend(handles=hs, fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
fig.tight_layout(); fig.savefig(f"{out}/fig5_depth_vs_regret.png", bbox_inches="tight"); plt.close(fig)
json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)

# ---------- Figure 6: technology-agnostic capacity map (synthetic per-message cost sweep) ----------
syn_path = os.path.join(root, primary, "synthetic.csv")
if os.path.exists(syn_path):
    from matplotlib.colors import ListedColormap, BoundaryNorm
    sy = pd.read_csv(syn_path)
    sy["extra"] = sy.Strategy.str.replace("Synthetic", "").astype(int)
    sg = sy.groupby(["extra", "Assets"]).agg(cost=("CostPer1kAssetTicks", "mean"), ingest=("IngestMs", "mean"), share=("IngestShare", "mean"),
                                           samples=("SamplesPerCand", "mean")).reset_index()
    sg["regret"] = 100 * (sg.cost - ref_cost) / ref_cost
    # effective per-asset synchronization cost of each level (from runs that were not budget-limited)
    cl = sg[sg.share < 0.9].assign(c=lambda d: d.ingest / d.Assets * 1000).groupby("extra").c.median()
    sg["c_us"] = sg.extra.map(cl)
    sg.to_csv(f"{out}/table_synthetic.csv", index=False)
    levels = sorted(sg.extra.unique()); fl = sorted(sg.Assets.unique())
    cvals = np.array([cl[e] for e in levels])
    # cell edges in log space
    def edges(v):
        lv = np.log(v); mid = (lv[1:] + lv[:-1]) / 2
        return np.exp(np.concatenate([[lv[0] - (mid[0] - lv[0])], mid, [lv[-1] + (lv[-1] - mid[-1])]]))
    xe, ye = edges(cvals), edges(np.array(fl, float))
    Z = np.full((len(fl), len(levels)), np.nan)
    for i, a in enumerate(fl):
        for j, e in enumerate(levels):
            r = sg[(sg.Assets == a) & (sg.extra == e)]
            if len(r): Z[i, j] = r.regret.iloc[0]
    band = np.digitize(Z, [10, 100])  # 0: <=10, 1: 10-100, 2: >100
    cmap = ListedColormap(["#d6e6f8", "#7fb0ea", "#1f5ea8"]); norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], 3)
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.pcolormesh(xe, ye, band, cmap=cmap, norm=norm, edgecolors="white", linewidth=1.5)
    for i, a in enumerate(fl):
        for j, e in enumerate(levels):
            if np.isfinite(Z[i, j]):
                ax.text(cvals[j] * 1.13, a * 0.93, f"{Z[i, j]:.0f}", ha="left", va="top", fontsize=5.8,
                        color="white" if band[i, j] == 2 else "#0b0b0b")
    xs = np.geomspace(xe[0], xe[-1], 100)
    ax.plot(xs, 10_000 / xs, color="#eb6834", lw=1.8, label="Predicted collapse  $A^{*}=B/c$")
    # real strategies (all platforms, .NET 10 JIT and AOT) at their measured cost and observed collapse interval midpoint
    REALM = {".NET 8.0 JIT": "o", ".NET 10.0 JIT": "s", ".NET 10.0 NativeAOT": "^"}
    for lab in labels:
        cp_ = os.path.join(root, lab, "sim.csv")
        if not os.path.exists(cp_): continue
        rs = pd.read_csv(cp_); rref = rs[rs.BudgetMs >= 1000].CostPer1kAssetTicks.mean(); rs = rs[rs.BudgetMs < 1000]
        ra = rs.groupby(["Runtime", "Strategy", "Assets"]).agg(cost=("CostPer1kAssetTicks", "mean"), ing=("IngestMs", "mean"), sh=("IngestShare", "mean")).reset_index()
        for (rt, st), g_ in ra.groupby(["Runtime", "Strategy"]):
            ok = g_[g_.sh < 0.9]
            if not len(ok): continue
            c_ = float((ok.ing / ok.Assets * 1000).median())
            g_ = g_.sort_values("Assets"); bad = g_[100 * (g_.cost - rref) / rref > 100]
            if not len(bad): continue
            hi = bad.Assets.iloc[0]; lo = g_[g_.Assets < hi].Assets.max() if (g_.Assets < hi).any() else hi / 2
            ax.errorbar(c_, np.sqrt(lo * hi), yerr=[[np.sqrt(lo * hi) - lo], [hi - np.sqrt(lo * hi)]], fmt=REALM.get(rt, "o"),
                        color="#0b0b0b", mfc="white" if "cloud" in lab else "#0b0b0b", ms=5, lw=0.8, capsize=2, zorder=5)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(xe[0], xe[-1]); ax.set_ylim(ye[0], ye[-1])
    from matplotlib.ticker import NullFormatter, FixedLocator, NullLocator
    ax.xaxis.set_major_locator(FixedLocator(cvals)); ax.xaxis.set_minor_locator(NullLocator())
    ax.set_xticklabels([f"{v:.2f}" for v in cvals]); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.yaxis.set_major_locator(FixedLocator(fl)); ax.yaxis.set_minor_locator(NullLocator())
    ax.set_yticklabels([f"{a / 1000:g}k" for a in fl])
    ax.set_xlabel("Synchronization cost per message, c (µs, log)"); ax.set_ylabel("Fleet size A (assets, log)")
    ax.grid(False)
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    hs = [Patch(color="#d6e6f8", label="Regret ≤ 10%"), Patch(color="#7fb0ea", label="Regret 10–100% (degraded)"),
          Patch(color="#1f5ea8", label="Regret > 100% (collapsed)"), Line2D([], [], color="#eb6834", lw=1.8, label="Predicted collapse A* = B/c"),
          Line2D([], [], color="#0b0b0b", marker="s", ls="", mfc="white", label="Measured .NET strategy, cloud"),
          Line2D([], [], color="#0b0b0b", marker="s", ls="", label="Measured .NET strategy, laptop")]
    ax.legend(handles=hs, fontsize=6.5, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    fig.tight_layout(); fig.savefig(f"{out}/fig6_capacity_map.png", bbox_inches="tight"); plt.close(fig)
    # how well does the hyperbola separate collapsed from non-collapsed synthetic cells?
    agree = tot_ = 0
    for i, a in enumerate(fl):
        for j, e in enumerate(levels):
            if not np.isfinite(Z[i, j]): continue
            tot_ += 1; pred = a > 10_000 / cvals[j]; obs = Z[i, j] > 100
            agree += int(pred == obs)
    summary.update({"syn_agree": agree, "syn_total": tot_, "syn_c_min": float(cvals.min()), "syn_c_max": float(cvals.max())})
    json.dump(summary, open(f"{out}/summary.json", "w"), indent=1, default=float)
