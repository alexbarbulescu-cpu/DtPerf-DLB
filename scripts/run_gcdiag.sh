#!/usr/bin/env bash
# Garbage-collection diagnostic of Section 4.6 (results/cloud-xeon/gc_diagnostic.csv): reruns the configurations listed in that file
# with DT_GCLOG=1, which makes the simulator report on stderr how many measured cycles overran the budget by more than 5% and how
# many of them contained a garbage collection. Usage: scripts/run_gcdiag.sh [out.csv]
set -e
OUT=${1:-results/cloud-xeon/gc_diagnostic_rerun.csv}; export DT_THETA=$(cat results/cloud-xeon/theta.txt)
J="build/jit/bin/Release"; declare -A RT=( [".NET 8.0 JIT"]="dotnet $J/net8.0/DtPerf.dll" [".NET 10.0 JIT"]="dotnet $J/net10.0/DtPerf.dll" [".NET 10.0 NativeAOT"]="./bin-aot/DtPerf" )
echo "Runtime,Strategy,Assets,BudgetMs,Seed,MeasuredCycles,Overrun5Cycles,Overrun5CyclesWithGC,CyclesWithGC,CycleP95Ms,CycleP99Ms,CycleMaxMs" > "$OUT"
tail -n +2 results/cloud-xeon/gc_diagnostic.csv | while IFS=, read rt st a b seed rest; do
  r=$(DT_GCLOG=1 ${RT[$rt]} sim "$st" "$a" "$b" 200 "$seed" 2> gc.err)
  python3 - "$r" "$(cat gc.err)" >> "$OUT" <<'PY'
import sys
f = sys.argv[1].split(","); kv = dict(t.split("=") for t in sys.argv[2].replace("GCLOG", "").split() if "=" in t)
print(",".join(f[:5] + [kv["measured"], kv["overrun5"], kv["overrun5_with_gc"], kv["cycles_with_gc"]] + f[17:20]))
PY
done; rm -f gc.err; echo "written $OUT"
