"""Revision analyses (v3). Run after analyze.py. Usage: python analyze_v3.py <results_root> <figs_dir> <primary_label>
Reads the outputs of analyze.py (figs_dir/table_*.csv) and the raw v3 files in <results_root>/<primary>/v3/, and writes
figs_dir/summary_v3.json plus supporting tables. Every block is skipped silently when its input files are missing."""
import sys, os, glob, json, math
import numpy as np, pandas as pd
from scipy.stats import spearmanr, binom

root, figs, primary = sys.argv[1], sys.argv[2], sys.argv[3]
P = os.path.join(root, primary); V3 = os.path.join(P, "v3")
RTS = [".NET 8.0 JIT", ".NET 10.0 JIT", ".NET 10.0 NativeAOT"]
SIMCOLS = ["Runtime", "Strategy", "Assets", "BudgetMs", "Seed", "Ticks", "CostPer1kAssetTicks", "FailuresPer1k", "PmPer1k", "IngestMs",
           "IngestShare", "DroppedShare", "Candidates", "UnsampledCandShare", "SamplesPerCand", "OverrunShare", "Overrun5Share",
           "CycleP95Ms", "CycleP99Ms", "CycleMaxMs", "ScreenMs", "DecisionMs"]
B_MS, TOL, COLL = 10.0, 10.0, 100.0
S = {}
rng = np.random.default_rng(7)


def rd(path, prefix=None, extra_tail=0):
    if not os.path.exists(path) or os.path.getsize(path) < 5: return None
    rows = [ln.rstrip("\n").split(",") for ln in open(path, encoding="utf-8-sig") if ln.strip()]
    rows = [r for r in rows if not r[0].startswith(("Runtime", "Theta"))]
    names = ([prefix] if prefix else []) + SIMCOLS
    rows = [r[:len(names)] + ([",".join(r[len(names):])] if extra_tail else []) for r in rows if len(r) >= len(names)]
    d = pd.DataFrame(rows, columns=names + (["Tail"] if extra_tail else []))
    for c in names:
        if c not in ("Runtime", "Strategy", "Policy", "Mode"): d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def regret(cons, ref, keys=("Assets", "Seed")):
    r = ref.groupby(list(keys)).CostPer1kAssetTicks.mean().rename("ref_cost").reset_index()
    x = cons.merge(r, on=list(keys), how="inner"); x["reg"] = 100 * (x.CostPer1kAssetTicks - x.ref_cost) / x.ref_cost; return x


def thresholds(g, fleets):
    """capacity (largest fleet with mean regret <= TOL) and collapse interval (first fleet with mean regret > COLL) on the grid."""
    m = g.groupby("Assets").reg.mean().reindex(fleets)
    ok = [a for a in fleets if np.isfinite(m[a]) and m[a] <= TOL]; cap = max(ok) if ok else 0
    bad = [a for a in fleets if np.isfinite(m[a]) and m[a] > COLL]
    hi = bad[0] if bad else None; lo = max([a for a in fleets if a < hi], default=0) if hi else fleets[-1]
    return cap, (lo, hi)


def kf(x): return f"{x / 1000:g}"
def cap_txt(c, fleets): return (kf(c) + ("+" if c == fleets[-1] else "")) if c else f"< {kf(fleets[0])}"
def coll_txt(iv, fleets):
    lo, hi = iv
    return f"> {kf(lo)}" if hi is None else (f"≤ {kf(hi)}" if lo == 0 else f"{kf(lo)}–{kf(hi)}")


def interp_cross(fleets, vals, level):
    """first fleet size at which a regret curve crosses `level` (log-linear interpolation in log A and log(1 + regret))."""
    a = np.log(np.asarray(fleets, float)); y = np.log1p(np.clip(np.asarray(vals, float), 0, None)); t = math.log1p(level)
    for i in range(len(a)):
        if y[i] > t:
            if i == 0: return float("nan")  # already above at the smallest fleet
            return float(np.exp(a[i - 1] + (t - y[i - 1]) * (a[i] - a[i - 1]) / (y[i] - y[i - 1])))
    return float("inf")


# ------------------------------------------------------------------ main closed-loop tables from analyze.py
sim = pd.read_csv(f"{figs}/table_sim.csv"); seed = pd.read_csv(f"{figs}/table_sim_seed.csv"); cap = pd.read_csv(f"{figs}/table_capacity.csv")
FLEETS = sorted(sim.Assets.unique()); S["fleets"] = FLEETS
ref = rd(os.path.join(P, "reference.csv"))
seed["reg"] = seed.regret_seed

# ---- deadline compliance (M8)
S["cmp_n"] = int(len(sim))
S["cmp_over_any_mean"] = float(100 * sim.OverrunShare.mean())
S["cmp_over5_mean"] = float(100 * sim.Overrun5Share.mean()); S["cmp_over5_max"] = float(100 * sim.Overrun5Share.max())
S["cmp_p95_med"] = float(sim.CycleP95Ms.median()); S["cmp_p99_med"] = float(sim.CycleP99Ms.median())
S["cmp_p99_gt2b"] = int((sim.CycleP99Ms > 2 * B_MS).sum()); S["cmp_max"] = float(sim.CycleMaxMs.max())
S["cmp_sync_gtB"] = int((sim.share > 1).sum()); S["cmp_sync_gt11"] = int((sim.share > 1.1).sum())
coll = sim[sim.regret_pct > COLL]; nonc = sim[sim.regret_pct <= COLL]
S["cmp_n_coll"] = int(len(coll)); S["cmp_sync_gtB_coll"] = int((coll.share > 1).sum())
S["cmp_nonc_over5_mean"] = float(100 * nonc.Overrun5Share.mean()); S["cmp_nonc_p99_med"] = float(nonc.CycleP99Ms.median())
S["cmp_nonc_p95_med"] = float(nonc.CycleP95Ms.median()); S["cmp_nonc_over_any"] = float(100 * nonc.OverrunShare.mean())
S["cmp_coll_over5_mean"] = float(100 * coll.Overrun5Share.mean())
w = sim.loc[sim.share.idxmax()]
S["cmp_worst"] = {"rt": w.Runtime, "st": w.Strategy, "A": int(w.Assets), "sync_ms": float(w.ingest_ms), "p95": float(w.CycleP95Ms)}
bys = sim[sim.regret_pct <= COLL].groupby("Strategy").Overrun5Share.mean() * 100
S["cmp_over5_by_strategy_nonc"] = {k: float(v) for k, v in bys.items()}
lat = sim.groupby(["Runtime", "Strategy"]).agg(p95=("CycleP95Ms", "median"), p99=("CycleP99Ms", "median"), over_any=("OverrunShare", "mean"),
                                                over5=("Overrun5Share", "mean"), sync_gtB=("share", lambda v: int((v > 1).sum()))).reset_index()
lat.to_csv(f"{figs}/table_compliance.csv", index=False)

# ---- bootstrap intervals over seeds for capacity and collapse (M9)
boot_rows = []
for (rt, st), g in seed.groupby(["Runtime", "Strategy"]):
    seeds = sorted(g.Seed.unique()); caps, his = [], []
    piv = g.pivot_table(index="Seed", columns="Assets", values="reg")
    for _ in range(2000):
        ss = rng.choice(seeds, size=len(seeds), replace=True); m = piv.loc[ss].mean()
        ok = [a for a in FLEETS if a in m and m[a] <= TOL]; caps.append(max(ok) if ok else 0)
        bad = [a for a in FLEETS if a in m and m[a] > COLL]; his.append(bad[0] if bad else np.inf)
    c0, iv0 = thresholds(g, FLEETS)
    clo, chi = np.percentile(caps, [2.5, 97.5], method="nearest"); hlo, hhi = np.percentile(his, [2.5, 97.5], method="nearest")
    boot_rows.append({"Runtime": rt, "Strategy": st, "cap": c0, "cap_lo": clo, "cap_hi": chi, "coll_hi": iv0[1] if iv0[1] else np.inf,
                      "coll_hi_lo": hlo, "coll_hi_hi": hhi, "cap_point_in_ci": clo <= c0 <= chi})
boot = pd.DataFrame(boot_rows); boot.to_csv(f"{figs}/table_bootstrap.csv", index=False)
S["boot_cap_width0"] = int((boot.cap_lo == boot.cap_hi).sum()); S["boot_n"] = int(len(boot))
S["boot_cap_multi"] = int((boot.cap_lo != boot.cap_hi).sum())
S["boot_coll_multi"] = int((boot.coll_hi_lo != boot.coll_hi_hi).sum())
def _bt(r):
    f = lambda x: "—" if x == 0 else ("> 30" if not np.isfinite(x) else kf(x))
    return f(r.cap_lo) if r.cap_lo == r.cap_hi else f"{f(r.cap_lo)}–{f(r.cap_hi)}"
boot["cap_ci_txt"] = [_bt(r) for _, r in boot.iterrows()]
# regret SD across seeds near collapse
S["seed_sd_max"] = float(sim.regret_sd.max()); r_ = sim.loc[sim.regret_sd.idxmax()]
S["seed_sd_max_cfg"] = {"rt": r_.Runtime, "st": r_.Strategy, "A": int(r_.Assets), "mean": float(r_.regret_pct)}

# ---- probabilistic depth guideline (seed-level runs)
gl = []
for k in [16, 32, 64, 128, 256]:
    x = seed[seed.SamplesPerCand >= k]
    gl.append({"K": k, "n": int(len(x)), "le10": float(100 * (x.reg <= 10).mean()), "le20": float(100 * (x.reg <= 20).mean()),
               "max": float(x.reg.max())})
S["guide"] = gl
# depth among sampled candidates and coverage, seed level
seed["cov"] = 1 - seed.UnsampledCandShare
seed["kdepth"] = seed.SamplesPerCand / seed["cov"].clip(lower=1e-9)

# ---- analysis depth: scales, regimes, coverage vs depth, within-fleet (M6)
dd = sim[sim.samples > 0].copy()
yl = np.log1p(dd.regret_pct.clip(lower=0.5)); xk = np.log(dd.samples)
def r2(y, X):
    X = np.column_stack([np.ones(len(y))] + list(X)); b, *_ = np.linalg.lstsq(X, y, rcond=None); return float(1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum())
S["r2_log"] = r2(yl.values, [xk.values]); S["r2_raw"] = r2(dd.regret_pct.values, [xk.values])
S["r2_raw_on_log"] = None
hiK, loK = dd[dd.samples >= 1], dd[dd.samples < 1]
S["r2_log_k_ge1"], S["n_k_ge1"] = r2(np.log1p(hiK.regret_pct.clip(lower=0.5)).values, [np.log(hiK.samples).values]), int(len(hiK))
S["n_k_lt1"] = int(len(loK)); S["k_lt1_min"] = float(loK.samples.min()) if len(loK) else float("nan")
if len(loK) > 3:
    S["r2_log_k_lt1"] = r2(np.log1p(loK.regret_pct.clip(lower=0.5)).values, [np.log(loK.samples).values])
    S["rho_k_lt1"] = float(spearmanr(loK.samples, loK.regret_pct).correlation)
cov_ = (1 - dd.unsampled).clip(lower=1e-4); kdep = dd.samples / cov_
S["r2_cov"] = r2(yl.values, [np.log(cov_).values]); S["r2_kdepth"] = r2(yl.values, [np.log(kdep).values])
S["r2_cov_kdepth"] = r2(yl.values, [np.log(cov_).values, np.log(kdep).values])
# seed level with fleet-size fixed effects (within-fleet variance explained by log K)
sd_ = seed[seed.SamplesPerCand > 0].copy(); ys = np.log1p(sd_.reg.clip(lower=0.5)).values
FE = pd.get_dummies(sd_.Assets.astype(str), drop_first=True).astype(float).values.T
S["seed_n"] = int(len(sd_)); S["seed_r2_k"] = r2(ys, [np.log(sd_.SamplesPerCand).values])
r2_fe = r2(ys, list(FE)); r2_fek = r2(ys, list(FE) + [np.log(sd_.SamplesPerCand).values])
S["seed_r2_fe"] = r2_fe; S["seed_r2_fe_k"] = r2_fek; S["seed_within_r2"] = float((r2_fek - r2_fe) / (1 - r2_fe))
# endogenous number of candidates
if ref is not None:
    rc = ref.groupby(["Assets", "Seed"]).Candidates.mean().rename("ref_cand").reset_index()
    xx = seed.merge(rc, on=["Assets", "Seed"]); xx["cand_ratio"] = xx.Candidates / xx.ref_cand
    deg = xx[(xx.reg > TOL) & (xx.reg <= COLL)]; col_ = xx[xx.reg > COLL]; good = xx[xx.reg <= TOL]
    S["cand_ratio_good_med"] = float(good.cand_ratio.median()); S["cand_ratio_deg_med"] = float(deg.cand_ratio.median())
    S["cand_ratio_coll_med"] = float(col_.cand_ratio.median()); S["cand_ratio_max"] = float(xx.cand_ratio.max())
    S["ref_cand_by_fleet"] = {int(a): float(v) for a, v in ref.groupby("Assets").Candidates.mean().items()}
# residuals vs ablation by strategy in the degraded band
dpath = f"{figs}/table_depth.csv"
if os.path.exists(dpath):
    dp = pd.read_csv(dpath)
    band = dp[(dp.regret_pct > TOL) & (dp.regret_pct <= COLL) & dp.abl_pred.notna()].copy(); band["res"] = band.regret_pct - band.abl_pred
    S["res_by_strategy"] = {k: {"n": int(len(g)), "med": float(g.res.median()), "min": float(g.res.min()), "max": float(g.res.max())}
                            for k, g in band.groupby("Strategy")}
    ab_coll = dp[(dp.regret_pct > COLL) & dp.abl_pred.notna()]
    S["res_coll_n"] = int(len(ab_coll))
    if len(ab_coll): S["res_coll_min"], S["res_coll_max"] = float((ab_coll.regret_pct - ab_coll.abl_pred).min()), float((ab_coll.regret_pct - ab_coll.abl_pred).max())
    # unsampled share at similar depth: reflection vs others
    S["unsampled_by_strategy_band"] = {k: float(100 * g.unsampled.median()) for k, g in band.groupby("Strategy")}

# ---- c_mc per runtime and c_u from the null materializer
mcb = os.path.join(V3, "mcbench.csv")
cmc = {}
if os.path.exists(mcb):
    m_ = pd.read_csv(mcb, header=None, names=["rt", "rep", "ns"])
    rtmap = {"net8": RTS[0], "net10": RTS[1], "aot": RTS[2]}
    cmc = {rtmap[k]: float(g.ns.median()) / 1000 for k, g in m_.groupby("rt")}   # µs per simulated path
    S["cmc_us"] = cmc
nul = rd(os.path.join(V3, "sim_null.csv"))
cu = None
if nul is not None:
    nb = nul[(nul.IngestShare < 0.95) & (nul.DroppedShare < 0.05)]
    cu_by = (nb.IngestMs / (nb.Assets * (1 - nb.DroppedShare)) * 1000).groupby(nb.Assets).median()
    cu = float(cu_by.median()); S["cu_us"] = cu; S["cu_by_fleet"] = {int(a): float(v) for a, v in cu_by.items()}
    S["null_share_30k"] = float(nul[nul.Assets == FLEETS[-1]].IngestShare.mean())

# ---- per-asset synchronization cost as a function of fleet size, c(A) (M2)
cA = seed[(seed.IngestShare < 0.95) & (seed.DroppedShare < 0.05)].assign(c=lambda d: d.IngestMs / (d.Assets * (1 - d.DroppedShare)) * 1000).groupby(["Runtime", "Strategy", "Assets"]).c.median().reset_index()
cA.to_csv(f"{figs}/table_cA.csv", index=False)
slopes = []
for (rt, st), g in cA.groupby(["Runtime", "Strategy"]):
    if g.Assets.nunique() >= 3:
        b = np.polyfit(np.log(g.Assets), np.log(g.c), 1)[0]; slopes.append(b)
        g2 = g.sort_values("Assets")
S["cA_slope_med"] = float(np.median(slopes)) if slopes else float("nan")
g5 = cA[(cA.Runtime == RTS[1]) & (cA.Strategy == "Generated")].sort_values("Assets")
if len(g5) >= 2:
    S["cA_s5_lo"], S["cA_s5_hi"], S["cA_s5_a_lo"], S["cA_s5_a_hi"] = float(g5.c.iloc[0]), float(g5.c.iloc[-1]), int(g5.Assets.iloc[0]), int(g5.Assets.iloc[-1])

# ---- tests of Equations (2)-(3) and an onset predictor (M1)
abl_path = f"{figs}/table_ablation.csv"
if cmc and ref is not None and os.path.exists(abl_path):
    abl = pd.read_csv(abl_path); ac = abl.groupby("K").agg(reg=("regret", "median"), k=("samples", "mean")).reset_index().sort_values("k")
    # K_10: depth at which the depth-only ablation reaches 10 % regret (log-log interpolation, regret decreasing in K)
    lk, lr = np.log(ac.k.values), np.log(ac.reg.clip(lower=0.01).values)
    i = int(np.argmax(lr < math.log(TOL)))
    K10 = float(np.exp(lk[i - 1] + (math.log(TOL) - lr[i - 1]) * (lk[i] - lk[i - 1]) / (lr[i] - lr[i - 1]))) if i > 0 else float(ac.k.iloc[0])
    S["K10"] = K10
    i1 = int(np.argmax(lr < math.log(COLL))); S["K100"] = float(np.exp(lk[i1 - 1] + (math.log(COLL) - lr[i1 - 1]) * (lk[i1] - lk[i1 - 1]) / (lr[i1] - lr[i1 - 1]))) if i1 > 0 else float(ac.k.iloc[0])
    capc = cap.set_index(["Runtime", "Strategy"])
    c_s = float(np.nanmedian(capc.PerAssetScreenUs)); t_dec = float(np.nanmedian(capc.DecisionMs))
    S["c_s_us"], S["t_dec_ms"] = c_s, t_dec
    ncref = ref.groupby("Assets").Candidates.mean()
    la, ln = np.log(ncref.index.values.astype(float)), np.log(ncref.values)
    nc_of = lambda A: float(np.exp(np.interp(np.log(A), la, ln, left=None, right=None) if la[0] <= np.log(A) <= la[-1]
                                  else (ln[0] + (np.log(A) - la[0]) * (ln[1] - ln[0]) / (la[1] - la[0]) if np.log(A) < la[0]
                                        else ln[-1] + (np.log(A) - la[-1]) * (ln[-1] - ln[-2]) / (la[-1] - la[-2]))))
    def k_pred(A, c, rt, nc=None):
        twi = B_MS * 1000 - A * (c + c_s) - t_dec * 1000   # µs
        return max(0.0, min(2048.0, twi / ((nc or nc_of(A)) * cmc[rt])))
    # (a) predicted vs observed K for every configuration (exogenous n_c from the reference twin)
    rows = []
    for _, r in sim.iterrows():
        if (r.Runtime, r.Strategy) not in capc.index: continue
        c = capc.loc[(r.Runtime, r.Strategy), "PerAssetIngestUs"]
        if not np.isfinite(c): continue
        rows.append({"Runtime": r.Runtime, "Strategy": r.Strategy, "Assets": r.Assets, "K_obs": r.samples, "K_pred": k_pred(r.Assets, c, r.Runtime),
                     "regret": r.regret_pct})
    kp = pd.DataFrame(rows); kp.to_csv(f"{figs}/table_kpred.csv", index=False)
    ok = kp[(kp.K_pred >= 1) & (kp.K_obs >= 1) & (kp.K_pred < 2048)]
    S["kpred_n"] = int(len(ok)); S["kpred_rho"] = float(spearmanr(ok.K_pred, ok.K_obs).correlation)
    lr_ = np.log(ok.K_obs / ok.K_pred); S["kpred_ratio_med"] = float(np.exp(lr_.median()))
    S["kpred_ratio_q1"], S["kpred_ratio_q3"] = float(np.exp(lr_.quantile(0.25))), float(np.exp(lr_.quantile(0.75)))
    S["kpred_r2_log"] = float(1 - ((np.log(ok.K_obs) - np.log(ok.K_pred) - lr_.mean()) ** 2).sum() / ((np.log(ok.K_obs) - np.log(ok.K_obs).mean()) ** 2).sum())
    # depth with the observed (endogenous) number of candidates, to separate the candidate feedback from the other sources of error
    kp2 = []
    for _, r in sim.iterrows():
        if (r.Runtime, r.Strategy) not in capc.index: continue
        c = capc.loc[(r.Runtime, r.Strategy), "PerAssetIngestUs"]
        if np.isfinite(c): kp2.append(k_pred(r.Assets, c, r.Runtime, nc=r.Candidates) if "Candidates" in r else np.nan)
    if "Candidates" in sim:
        kp["K_pred_obsnc"] = kp2; ok2 = kp[(kp.K_pred_obsnc >= 1) & (kp.K_obs >= 1) & (kp.K_pred_obsnc < 2048)]
        S["kpred_obsnc_ratio_med"] = float(np.exp(np.log(ok2.K_obs / ok2.K_pred_obsnc).median()))
    # (b) onset (10 % regret) and collapse (100 %) predictors versus interpolated observations
    grid = np.geomspace(500, 60000, 4000); orow = []
    for (rt, st), g in sim.groupby(["Runtime", "Strategy"]):
        if (rt, st) not in capc.index: continue
        c = capc.loc[(rt, st), "PerAssetIngestUs"]
        if not np.isfinite(c): continue
        g = g.set_index("Assets").reindex(FLEETS)
        on_obs = interp_cross(FLEETS, g.regret_pct.values, TOL); co_obs = interp_cross(FLEETS, g.regret_pct.values, COLL)
        kk = np.array([k_pred(A, c, rt) for A in grid])
        on_pred = float(grid[np.argmax(kk < K10)]) if (kk < K10).any() else float("inf")
        oth = ok[~((ok.Runtime == rt) & (ok.Strategy == st))]; eta = float(np.exp(np.log(oth.K_obs / oth.K_pred).median()))
        on_cal = float(grid[np.argmax(eta * kk < K10)]) if (eta * kk < K10).any() else float("inf")
        co_k = float(grid[np.argmax(kk < S["K100"])]) if (kk < S["K100"]).any() else float("inf")
        astar = (B_MS - t_dec) * 1000 / (c + c_s)
        # Eq. (4) with the fleet-dependent cost c(A) measured in the loop (log-linear in A, extrapolated with the fitted slope)
        gA = cA[(cA.Runtime == rt) & (cA.Strategy == st)]
        if gA.Assets.nunique() >= 2:
            b1, b0 = np.polyfit(np.log(gA.Assets), np.log(gA.c), 1); cfun = lambda A: float(np.exp(b0 + b1 * np.log(A)))
            f = np.array([A * (cfun(A) + c_s) - (B_MS - t_dec) * 1000 for A in grid]); astar_cA = float(grid[np.argmax(f > 0)]) if (f > 0).any() else float("inf")
        else: astar_cA = float("nan")
        cap0 = capc.loc[(rt, st), "MaxFleetRegretLe10"]
        nxt = next((a for a in FLEETS if a > cap0), np.inf) if cap0 else FLEETS[0]
        orow.append({"Runtime": rt, "Strategy": st, "c_us": c, "onset_obs": on_obs, "onset_pred": on_pred, "onset_cal": on_cal, "eta": eta,
                     "onset_cal_in": bool((cap0 < on_cal <= nxt) if cap0 else on_cal <= FLEETS[0]), "collapse_obs": co_obs, "astar": astar,
                     "astar_cA": astar_cA, "collapse_k": co_k, "cap": cap0, "cap_next": nxt,
                     "onset_in_interval": bool((cap0 < on_pred <= nxt) if cap0 else on_pred <= FLEETS[0]),
                     "astar_ratio": astar / on_obs if np.isfinite(on_obs) and on_obs > 0 else np.nan})
    on = pd.DataFrame(orow); on.to_csv(f"{figs}/table_onset.csv", index=False)
    fin = on[np.isfinite(on.onset_obs) & np.isfinite(on.onset_pred)]
    err = 100 * (fin.onset_pred / fin.onset_obs - 1)
    S["onset_n"] = int(len(fin)); S["onset_err_med_abs"] = float(err.abs().median()); S["onset_err_med"] = float(err.median())
    S["onset_err_max_abs"] = float(err.abs().max()); S["onset_in_interval"] = int(on.onset_in_interval.sum()); S["onset_tot"] = int(len(on))
    ec = 100 * (fin.onset_cal / fin.onset_obs - 1); S["onset_cal_med_abs"] = float(ec.abs().median()); S["onset_cal_max_abs"] = float(ec.abs().max())
    S["onset_cal_in"] = int(on.onset_cal_in.sum()); S["eta_lo"], S["eta_hi"] = float(on.eta.min()), float(on.eta.max())
    S["onset_over_astar_lo"] = float((fin.onset_obs / fin.astar).min()); S["onset_over_astar_hi"] = float((fin.onset_obs / fin.astar).max())
    # baseline: constant fraction of A* (median ratio), leave-one-out
    fr = (fin.onset_obs / fin.astar).values; loo = []
    for j in range(len(fr)):
        q = np.median(np.delete(fr, j)); loo.append(100 * abs(q * fin.astar.values[j] / fin.onset_obs.values[j] - 1))
    S["onset_frac_loo_med_abs"] = float(np.median(loo)) if loo else float("nan")
    cf = on[np.isfinite(on.collapse_obs)]
    e4 = 100 * (cf.astar / cf.collapse_obs - 1); e4c = 100 * (cf.astar_cA / cf.collapse_obs - 1); ek = 100 * (cf.collapse_k / cf.collapse_obs - 1)
    S["coll_n"] = int(len(cf)); S["coll_err4_med"] = float(e4.median()); S["coll_err4_med_abs"] = float(e4.abs().median())
    S["coll_err4cA_med"] = float(e4c.median()); S["coll_err4cA_med_abs"] = float(e4c.abs().median())
    S["coll_errk_med"] = float(ek.median()); S["coll_errk_med_abs"] = float(ek.abs().median())
    S["coll_err4_pos"] = int((e4 > 0).sum())

# ---- capacity map: near-boundary accuracy and continuous error (M2)
syp = f"{figs}/table_synthetic.csv"
if os.path.exists(syp):
    sg = pd.read_csv(syp); c_scr = S.get("c_s_us");
    js = json.load(open(f"{figs}/summary.json")); c_scr, t_d = js["syn_c_scr_us"], js["syn_t_dec_ms"]
    sg["astar"] = (sg.BudgetMs - t_d) * 1000 / (sg.c_us + c_scr)
    near = sg[(sg.Assets / sg.astar).between(1 / 1.5, 1.5)]
    S["map_near_n"] = int(len(near)); S["map_near_ok"] = int(((near.Assets > near.astar) == (near.regret > COLL)).sum())
    S["map_maj"] = {f"{b:g}": int(max((g.regret > COLL).sum(), (g.regret <= COLL).sum())) for b, g in sg.groupby("BudgetMs")}
    S["map_tot"] = {f"{b:g}": int(len(g)) for b, g in sg.groupby("BudgetMs")}
    ce = []
    for (b, e), g in sg.groupby(["BudgetMs", "extra"]):
        g = g.sort_values("Assets"); x = interp_cross(g.Assets.values, g.regret.values, COLL)
        if np.isfinite(x): ce.append(100 * (g.astar.iloc[0] / x - 1))
    S["map_cont_n"] = len(ce); S["map_cont_med"] = float(np.median(ce)) if ce else float("nan")
    S["map_cont_lo"], S["map_cont_hi"] = (float(min(ce)), float(max(ce))) if ce else (float("nan"), float("nan"))
    # synthetic per-message cost at the smallest and largest unsaturated fleet (B = 10 ms, zero-busy-wait level)
    raw = rd(os.path.join(P, "synthetic.csv"))
    if raw is not None:
        z = raw[(raw.BudgetMs == 10) & (raw.Strategy == "Synthetic0") & (raw.IngestShare < 0.9)]
        zz = (z.IngestMs / z.Assets * 1000).groupby(z.Assets).median()
        if len(zz) >= 2: S["syn0_c_lo"], S["syn0_c_hi"], S["syn0_a_lo"], S["syn0_a_hi"] = float(zz.iloc[0]), float(zz.iloc[-1]), int(zz.index[0]), int(zz.index[-1])

# ---- microbenchmark repetitions: steady state and comparison with the single-process run (M5)
il = sorted(glob.glob(os.path.join(V3, "micro_rep", "iterlog_*.csv")))
if il:
    d = pd.concat([pd.read_csv(f, header=None, names=["Runtime", "Category", "Method", "P", "it", "ns"]).assign(proc=os.path.basename(f)) for f in il])
    st_rows = []
    for k, g in d.groupby(["proc", "Runtime", "Category", "Method", "P"]):
        g = g.sort_values("it"); v = g.ns.values
        if len(v) < 20: continue
        first, last = np.median(v[:10]), np.median(v[-10:]); rho, p = spearmanr(np.arange(len(v)), v)
        st_rows.append({"rel": (last - first) / first, "rho": rho, "p": p})
    st = pd.DataFrame(st_rows)
    S["ss_n"] = int(len(st)); S["ss_within2"] = float(100 * (st.rel.abs() <= 0.02).mean()); S["ss_within5"] = float(100 * (st.rel.abs() <= 0.05).mean())
    S["ss_trend_sig"] = float(100 * ((st.p < 0.01) & (st.rho.abs() > 0.5)).mean())
    S["ss_trend_down"] = float(100 * ((st.p < 0.01) & (st.rho < -0.5)).mean()); S["ss_trend_up"] = float(100 * ((st.p < 0.01) & (st.rho > 0.5)).mean())
    tr = st[(st.p < 0.01) & (st.rho.abs() > 0.5)]
    S["ss_trend_rel_med"] = float(100 * tr.rel.abs().median()) if len(tr) else 0.0; S["ss_rel_med"] = float(100 * st.rel.abs().median())
mr = sorted(f for f in glob.glob(os.path.join(V3, "micro_rep", "*.csv")) if not os.path.basename(f).startswith("iterlog"))
if mr:
    rep = pd.concat([pd.read_csv(f).assign(proc=os.path.basename(f)) for f in mr])
    S["rep_nproc"] = int(rep.groupby("Runtime").proc.nunique().min())
    mat = rep[rep.Category == "Materialize"]
    cv = mat.groupby(["Runtime", "Method", "P"]).MedianNs.agg(lambda v: 100 * v.std(ddof=1) / v.mean())
    S["rep_cv_med"] = float(cv.median()); S["rep_cv_max"] = float(cv.max()); cvm = cv.idxmax(); S["rep_cv_max_cfg"] = [str(x) for x in cvm]
    rk = mat.groupby(["Runtime", "P", "proc"]).apply(lambda x: tuple(x.sort_values("MedianNs").Method)).groupby(level=[0, 1]).nunique()
    S["rep_rank_stable"] = int((rk == 1).sum()); S["rep_rank_tot"] = int(len(rk))
    ex = mat.groupby(["Runtime", "P", "proc"]).apply(lambda x: (x.sort_values("MedianNs").Method.iloc[0], x.sort_values("MedianNs").Method.iloc[-1]))
    S["rep_extremes_stable"] = int((ex.groupby(level=[0, 1]).nunique() == 1).sum())
    S["rep_s5_fastest_all"] = bool(all(e[0] == "Generated" for e in ex.values))
    # single-process values of the original run versus the between-process median
    orig = pd.concat([pd.read_csv(f) for f in glob.glob(os.path.join(P, "micro_*.csv"))])
    med = mat.groupby(["Runtime", "Method", "P"]).MedianNs.median()
    o = orig[orig.Category == "Materialize"].set_index(["Runtime", "Method", "P"]).MedianNs
    dev = (100 * (o / med - 1)).dropna(); S["orig_dev_med_abs"] = float(dev.abs().median()); S["orig_dev_max_abs"] = float(dev.abs().max())
    dm = dev.abs().idxmax(); S["orig_dev_max_cfg"] = [str(x) for x in dm] + [float(o[dm]), float(med[dm])]
    # proportion of single-process values outside the between-process range
    lohi = mat.groupby(["Runtime", "Method", "P"]).MedianNs.agg(["min", "max"])
    jj = lohi.join(o.rename("o"), how="inner"); S["orig_outside"] = int(((jj.o < jj["min"]) | (jj.o > jj["max"])).sum()); S["orig_tot"] = int(len(jj))
    # .NET 8 vs .NET 10 compiled advantage (S1/S4) at P = 20 and 50 with between-process medians
    for p_ in [20, 50]:
        for rt, kk_ in [(RTS[0], "net8"), (RTS[1], "net10")]:
            S[f"adv_s4_{kk_}_p{p_}"] = float(med[(rt, "Reflection", p_)] / med[(rt, "CompiledWhole", p_)])
            S[f"refl_{kk_}_p{p_}"] = float(med[(rt, "Reflection", p_)])

# ---- S4/S5 control: generated code with S4's lookup algorithm (S5b) and a cache-cold payload set (P1 / M5)
ctl = sorted(glob.glob(os.path.join(V3, "microctl", "*.csv")))
if ctl:
    c = pd.concat([pd.read_csv(f).assign(proc=os.path.basename(f)) for f in ctl])
    cm = c.groupby(["Runtime", "Category", "Method", "P"]).MedianNs.median().reset_index(); cm.to_csv(f"{figs}/table_control_long.csv", index=False)
    ctrl = {}
    for rt in RTS:
        x = cm[(cm.Runtime == rt) & (cm.Category == "MaterializeCtl")].set_index(["Method", "P"]).MedianNs
        for p_ in [5, 20, 50]:
            try:
                ctrl[f"{rt}|{p_}"] = {"S4": float(x[("CompiledWhole", p_)]), "S5b": float(x[("GeneratedLookup", p_)]), "S5": float(x[("Generated", p_)])}
            except KeyError: pass
        y = cm[(cm.Runtime == rt) & (cm.Category == "MaterializeCold")].set_index("Method").MedianNs
        if len(y): ctrl[f"{rt}|cold"] = {k: float(v) for k, v in y.items()}
        z = cm[(cm.Runtime == rt) & (cm.Category == "MaterializeCtl") & (cm.P == 20)].set_index("Method").MedianNs
        if len(z): ctrl[f"{rt}|hot20"] = {k: float(v) for k, v in z.items()}
    S["ctrl"] = ctrl
s5b = rd(os.path.join(V3, "sim_s5b.csv"))
if s5b is not None and ref is not None:
    x = regret(s5b, ref); out = {}
    for rt, g in x.groupby("Runtime"):
        c0, iv = thresholds(g, FLEETS); nb = g[(g.IngestShare < 0.95) & (g.DroppedShare < 0.05)]
        nbm = (nb.IngestMs / (nb.Assets * (1 - nb.DroppedShare)) * 1000).groupby(nb.Assets).median()
        out[rt] = {"cap": cap_txt(c0, FLEETS), "coll": coll_txt(iv, FLEETS), "c_us": float(nbm.median()) if len(nbm) else float("nan"),
                   "cap_raw": int(c0), "coll_hi": iv[1]}
    S["s5b_loop"] = out

# ---- decision-policy variants (M3)
pol = rd(os.path.join(V3, "policy.csv"), prefix="Policy"); pref = rd(os.path.join(V3, "policy_reference.csv"), prefix="Policy")
if pol is not None and pref is not None:
    rows = []
    base = seed.copy(); base["Policy"] = "base"
    jref = pref[pref.Policy == "jeffreys"]; fref = pref[pref.Policy == "fb2"]
    # fb2 changes only the rule for candidates without samples; in the reference every candidate is sampled, so its reference equals the base one
    if len(fref):
        cmpf = fref.merge(ref, on=["Assets", "Seed"], suffixes=("", "_b"))
        S["fb2_ref_identical"] = bool(np.allclose(cmpf.CostPer1kAssetTicks, cmpf.CostPer1kAssetTicks_b))
    allp = {"base": base.rename(columns={"reg": "reg"})}
    allp["fb2"] = regret(pol[pol.Policy == "fb2"], ref); allp["jeffreys"] = regret(pol[pol.Policy == "jeffreys"], jref)
    S["jeff_ref_vs_base_pct"] = float(100 * (jref.CostPer1kAssetTicks.mean() / ref[ref.Assets.isin(jref.Assets.unique())].CostPer1kAssetTicks.mean() - 1))
    for pn, x in allp.items():
        x = x[x.Runtime == RTS[1]] if "Runtime" in x else x
        for st, g in x.groupby("Strategy"):
            if st not in ("Reflection", "ReflectionInvoker", "CompiledWhole", "Generated"): continue
            c0, iv = thresholds(g, FLEETS); m = g.groupby("Assets").reg.mean()
            rows.append({"Policy": pn, "Strategy": st, "cap": c0, "coll_lo": iv[0], "coll_hi": iv[1], "max_regret": float(m.max()),
                         "cap_txt": cap_txt(c0, FLEETS), "coll_txt": coll_txt(iv, FLEETS),
                         "fail_max": float(g.groupby("Assets").FailuresPer1k.mean().max())})
    pt = pd.DataFrame(rows); pt.to_csv(f"{figs}/table_policy.csv", index=False); S["policy"] = rows
    det = []
    for pn, x in allp.items():
        x = x[x.Runtime == RTS[1]]
        for (st, a), g in x.groupby(["Strategy", "Assets"]):
            det.append({"Policy": pn, "Strategy": st, "Assets": int(a), "cand": float(g.Candidates.mean()), "pm": float(g.PmPer1k.mean()),
                        "fail": float(g.FailuresPer1k.mean()), "k": float(g.SamplesPerCand.mean()), "unsampled": float(g.UnsampledCandShare.mean()),
                        "share": float(g.IngestShare.mean()), "reg": float(g.reg.mean())})
    pd.DataFrame(det).to_csv(f"{figs}/table_policy_detail.csv", index=False); S["policy_detail"] = det
    S["policy_ref"] = {"base": {"pm": float(ref.PmPer1k.mean()), "fail": float(ref.FailuresPer1k.mean()), "cand30k": float(ref[ref.Assets == FLEETS[-1]].Candidates.mean())},
                       "jeffreys": {"pm": float(jref.PmPer1k.mean()), "fail": float(jref.FailuresPer1k.mean()), "cand30k": float(jref[jref.Assets == FLEETS[-1]].Candidates.mean())}}
    # ordering preserved?
    order_ok = True
    for pn, g in pt.groupby("Policy"):
        g = g.set_index("Strategy"); pos = lambda st: FLEETS.index(g.loc[st, "coll_hi"]) if g.loc[st, "coll_hi"] in FLEETS else len(FLEETS)
        order_ok &= pos("Reflection") <= pos("CompiledWhole") <= pos("Generated") and g.loc["Reflection", "cap"] <= g.loc["Generated", "cap"]
    S["policy_order_ok"] = bool(order_ok)

# ---- GC modes (M4)
gcm = os.path.join(V3, "gc_modes.csv")
if os.path.exists(gcm) and os.path.getsize(gcm) > 10:
    rows = []
    for ln in open(gcm):
        parts = ln.strip().split(",")
        if len(parts) < 23: continue
        mode = parts[0]; r = dict(zip(SIMCOLS, parts[1:23])); tail = ",".join(parts[23:])
        kv = dict(t.split("=") for t in tail.replace("GCLOG", "").split() if "=" in t)
        rows.append({"Mode": mode, **{k: (v if k in ("Runtime", "Strategy") else float(v)) for k, v in r.items()}, **{k: float(v) for k, v in kv.items()}})
    g_ = pd.DataFrame(rows)
    g_ = regret(g_, ref)
    gs = g_.groupby(["Mode", "Strategy", "Assets"]).agg(over5=("Overrun5Share", "mean"), over=("OverrunShare", "mean"), p99=("CycleP99Ms", "mean"),
         reg=("reg", "mean"), share=("IngestShare", "mean"), k=("SamplesPerCand", "mean"), o5=("overrun5", "sum"), o5gc=("overrun5_with_gc", "sum"),
         cgc=("cycles_with_gc", "sum"), meas=("measured", "sum")).reset_index()
    gs.to_csv(f"{figs}/table_gcmodes.csv", index=False); S["gcmodes"] = gs.to_dict("records")
    t = g_.groupby("Mode").agg(over5=("Overrun5Share", "mean"), p99=("CycleP99Ms", "median"), o5=("overrun5", "sum"), o5gc=("overrun5_with_gc", "sum"),
                              cgc=("cycles_with_gc", "sum"), meas=("measured", "sum"))
    S["gcmode_sum"] = {m: {"over5": float(100 * r.over5), "p99": float(r.p99), "gc_share_of_over": float(100 * r.o5gc / max(1, r.o5)),
                           "cycles_gc_pct": float(100 * r.cgc / max(1, r.meas))} for m, r in t.iterrows()}

# ---- long horizon (M4): 600 cycles with 300 burn-in
lg = rd(os.path.join(V3, "long.csv"))
if lg is not None:
    lref = lg[lg.BudgetMs >= 1000]; lc = lg[lg.BudgetMs < 1000]; x = regret(lc, lref)
    lf = sorted(x.Assets.unique()); rows = []
    for st, g in x.groupby("Strategy"):
        m = g.groupby("Assets").reg.mean()
        mb = seed[(seed.Runtime == RTS[1]) & (seed.Strategy == st) & seed.Assets.isin(lf) & seed.Seed.isin(g.Seed.unique())].groupby("Assets").reg.mean()
        rows += [{"Strategy": st, "Assets": int(a), "reg_long": float(m[a]), "reg_main": float(mb.get(a, np.nan))} for a in lf]
    lt = pd.DataFrame(rows); lt.to_csv(f"{figs}/table_long.csv", index=False); S["long"] = rows
    S["long_ref_cost"] = float(lref.CostPer1kAssetTicks.mean()); S["long_ref_pm"] = float(lref.PmPer1k.mean())
    S["main_ref_pm_same"] = float(ref[ref.Assets.isin(lf)].PmPer1k.mean())
    def cls(v): return 0 if v <= TOL else (1 if v <= COLL else 2)
    S["long_same_class"] = int(sum(cls(r["reg_long"]) == cls(r["reg_main"]) for r in rows if np.isfinite(r["reg_main"]))); S["long_n"] = len(rows)

# ---- theta below 0.0005 (M3): unconstrained twin
cl = rd(os.path.join(V3, "calibration_low.csv"), prefix="Theta")
if cl is not None:
    cal = rd(os.path.join(P, "calibration.csv"), prefix="Theta")
    allc = pd.concat([cal, cl]) if cal is not None else cl
    cg = allc.groupby(["Assets", "Theta"]).agg(cost=("CostPer1kAssetTicks", "mean"), sd=("CostPer1kAssetTicks", "std"), n=("Seed", "count")).reset_index()
    cg.to_csv(f"{figs}/table_calibration_all.csv", index=False)
    S["cal_low"] = cg.to_dict("records")
    best = cg.loc[cg.groupby("Assets").cost.idxmin()]; S["cal_best"] = {int(r.Assets): float(r.Theta) for _, r in best.iterrows()}

# ---- T14s runs reported separately (M7)
for lab in [l for l in os.listdir(root) if l.startswith("t14s")]:
    out = {}
    for run in ["run1", "run2"]:
        s_ = rd(os.path.join(root, lab, run, "sim.csv")); r_ = rd(os.path.join(root, lab, run, "reference.csv"))
        if s_ is None or r_ is None: continue
        s_ = s_[s_.BudgetMs < 1000]; x = regret(s_, r_)
        for rt in [RTS[1], RTS[2]]:
            for st in ["Reflection", "ReflectionInvoker", "CompiledPerProperty", "CompiledWhole", "Generated"]:
                g = x[(x.Runtime == rt) & (x.Strategy == st)]
                if not len(g): continue
                c0, iv = thresholds(g, FLEETS)
                gm = g.groupby("Assets").reg.median(); bad = [a for a in FLEETS if a in gm and gm[a] > COLL]
                ivm = (max([a for a in FLEETS if a < bad[0]], default=0), bad[0]) if bad else (FLEETS[-1], None)
                out[f"{run}|{rt}|{st}"] = {"coll": coll_txt(iv, FLEETS), "coll_med": coll_txt(ivm, FLEETS), "cap": cap_txt(c0, FLEETS)}
        out[f"{run}|over5"] = float(100 * s_.Overrun5Share.mean()); out[f"{run}|p99_med"] = float(s_.groupby(["Runtime", "Strategy", "Assets"]).CycleP99Ms.mean().median())
        out[f"{run}|sync_gtB"] = int((s_.groupby(["Runtime", "Strategy", "Assets"]).IngestShare.mean() > 1).sum())
        out[f"{run}|ncfg"] = int(s_.groupby(["Runtime", "Strategy", "Assets"]).ngroups)
    # paired differences between the two runs of the same seed (run 2 seed s+10 repeats run 1 seed s), regret in percentage points
    pr_ = {}
    for run in ["run1", "run2"]:
        s_ = rd(os.path.join(root, lab, run, "sim.csv")); r_ = rd(os.path.join(root, lab, run, "reference.csv"))
        if s_ is not None and r_ is not None: pr_[run] = regret(s_[s_.BudgetMs < 1000], r_)
    if len(pr_) == 2:
        a_ = pr_["run1"]; b_ = pr_["run2"].copy(); b_["Seed"] = b_.Seed - 10 if b_.Seed.min() > 10 else b_.Seed
        m_ = a_.merge(b_, on=["Runtime", "Strategy", "Assets", "Seed"], suffixes=("_1", "_2")); m_["d"] = m_.reg_2 - m_.reg_1
        out["pair_n"] = int(len(m_)); out["pair_med"] = float(m_.d.median()); out["pair_q"] = [float(m_.d.quantile(0.05)), float(m_.d.quantile(0.95))]
        for sd_ in sorted(m_.Seed.unique()):
            out[f"pair_seed{int(sd_)}_med_abs"] = float(m_[m_.Seed == sd_].d.abs().median()); out[f"pair_seed{int(sd_)}_max_abs"] = float(m_[m_.Seed == sd_].d.abs().max())
    # seed 11 anomaly
    s2 = rd(os.path.join(root, lab, "sim.csv"))
    if s2 is not None:
        z = s2[(s2.Runtime == RTS[1]) & (s2.Assets == 10000) & s2.Strategy.isin(["CompiledPerProperty", "CompiledWhole", "Generated"])]
        out["s11_share"] = [float(z[z.Seed == 11].IngestShare.min()), float(z[z.Seed == 11].IngestShare.max())]
        out["other_share"] = [float(z[z.Seed != 11].IngestShare.min()), float(z[z.Seed != 11].IngestShare.max())]
    S["t14s"] = out

json.dump(S, open(f"{figs}/summary_v3.json", "w"), indent=1, default=lambda o: (None if (isinstance(o, float) and not np.isfinite(o)) else (int(o) if isinstance(o, (np.integer,)) else float(o))))
print("v3 ok", len(S))

# ---- Appendix B: sensitivity of capacity and collapse to theta (S1, S4, S5 on .NET 10 JIT)
sen = rd(os.path.join(P, "sensitivity.csv"), prefix="Theta")
if sen is not None and ref is not None:
    th0 = float(open(os.path.join(P, "theta.txt")).read()) if os.path.exists(os.path.join(P, "theta.txt")) else 0.001
    main = rd(os.path.join(P, "sim.csv")); main = main[(main.Runtime == RTS[1]) & main.Strategy.isin(["Reflection", "CompiledWhole", "Generated"])].copy()
    main.insert(0, "Theta", th0); r0 = ref.copy(); r0.insert(0, "Theta", th0)
    allx = pd.concat([sen, main, r0], ignore_index=True); rows = []
    for th, g in allx.groupby("Theta"):
        x = regret(g[g.BudgetMs < 1000], g[g.BudgetMs >= 1000])
        for st, h in x.groupby("Strategy"):
            c0, iv = thresholds(h, FLEETS); rows.append({"Theta": th, "Strategy": st, "seeds": int(h.Seed.nunique()), "capacity": cap_txt(c0, FLEETS), "collapse": coll_txt(iv, FLEETS)})
    pd.DataFrame(rows).to_csv(f"{figs}/table_sensitivity.csv", index=False)
    json.dump(S, open(f"{figs}/summary_v3.json", "w"), indent=1, default=lambda o: (None if (isinstance(o, float) and not np.isfinite(o)) else (int(o) if isinstance(o, (np.integer,)) else float(o))))
