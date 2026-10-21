#!/usr/bin/env bash
# v2 protocol (Linux, primary platform): full-cycle budget (sync+screen+what-if+decision), per-fleet references, 5 seeds, held-out budgets, depth ablation.
OUT=${OUT:-results/cloud-xeon}; mkdir -p $OUT
J="build/jit/bin/Release"; declare -A RT=( [net8]="$J/net8.0/DtPerf.dll" [net10]="$J/net10.0/DtPerf.dll" [aot]="./bin-aot/DtPerf" )
run() { local r=$1; shift; if [ "$r" = aot ]; then ${RT[aot]} "$@"; else dotnet ${RT[$r]} "$@"; fi; }
SEEDS=${SEEDS:-5}; FLEETS="2500 5000 7500 10000 15000 20000 30000"
# 1) calibration of theta on the unconstrained twin
if [ ! -f $OUT/CAL_DONE ]; then : > $OUT/calibration.csv
for th in 0.0005 0.001 0.002 0.003 0.005 0.0075 0.01 0.02 0.05; do
  for seed in 1 2 3; do echo "$th,$(DT_THETA=$th run net10 sim Generated 2500 1000 200 $seed)" >> $OUT/calibration.csv; done
  for seed in 1 2; do echo "$th,$(DT_THETA=$th run net10 sim Generated 10000 1000 200 $seed)" >> $OUT/calibration.csv; done
done; echo done > $OUT/CAL_DONE; fi
TH=$(python3 - "$OUT/calibration.csv" <<'PY'
import sys,pandas as pd
# one-standard-deviation rule: the largest theta whose mean cost is within one SD of the minimum at every calibration fleet size
d=pd.read_csv(sys.argv[1],header=None); d=d[[0,3,7]]; d.columns=["th","A","cost"]
ok=None
for a,g in d.groupby("A"):
    m=g.groupby("th").cost.agg(["mean","std"]); best=m["mean"].idxmin(); s=set(m.index[m["mean"]<=m.loc[best,"mean"]+m.loc[best,"std"]])
    ok=s if ok is None else ok & s
print(max(ok))
PY
); echo "$TH" > $OUT/theta.txt; export DT_THETA=$TH
# 2) unconstrained references for every fleet size and seed (fleet 1000 for the synthetic map)
if [ ! -f $OUT/REF_DONE ]; then
for seed in $(seq 1 $SEEDS); do for a in 1000 $FLEETS; do run net10 sim Generated $a 1000 200 $seed; done; done > $OUT/reference.csv
echo done > $OUT/REF_DONE; fi
# 3) main grid
if [ ! -f $OUT/SIM_DONE ]; then
for seed in $(seq 1 $SEEDS); do for r in net10 net8 aot; do for a in $FLEETS; do for s in Reflection ReflectionInvoker CompiledPerProperty CompiledWhole Generated; do
  run $r sim $s $a 10 200 $seed; done; done; done; done > $OUT/sim.csv
echo done > $OUT/SIM_DONE; fi
# 4) synthetic capacity map (B = 10 ms) and held-out budgets (B = 5 and 20 ms)
if [ ! -f $OUT/SYN_DONE ]; then
for B in 10 5 20; do for seed in 1 2 3; do for x in 0 250 500 1000 2000 4000; do for a in 1000 $FLEETS; do
  run net10 sim Synthetic$x $a $B 200 $seed; done; done; done; done > $OUT/synthetic.csv
echo done > $OUT/SYN_DONE; fi
# 5) analysis-depth ablation: unconstrained budget, samples per candidate capped at K
if [ ! -f $OUT/ABL_DONE ]; then
for seed in 1 2 3; do for k in 2 4 8 16 32 64 128 256 512; do for a in $FLEETS; do
  echo "$k,$(DT_KMAX=$k run net10 sim Generated $a 1000 200 $seed)"; done; done; done > $OUT/ablation.csv
echo done > $OUT/ABL_DONE; fi
# 6) sensitivity to theta (references included)
if [ ! -f $OUT/SENS_DONE ]; then
for th in 0.0005 0.005; do for seed in 1 2; do for a in $FLEETS; do
  for s in Reflection CompiledWhole Generated; do echo "$th,$(DT_THETA=$th run net10 sim $s $a 10 200 $seed)"; done
  echo "$th,$(DT_THETA=$th run net10 sim Generated $a 1000 200 $seed)"; done; done; done > $OUT/sensitivity.csv
echo done > $OUT/SENS_DONE; fi
echo done > $OUT/DONE
