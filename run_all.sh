#!/usr/bin/env bash
# Linux runner (same protocol as run-all.ps1). Usage: ./run_all.sh <label> [seeds]
set -euo pipefail
LABEL=${1:-linux}; SEEDS=${2:-5}; OUT=results/$LABEL; mkdir -p $OUT
RID=${RID:-linux-x64}
dotnet build build/jit/DtPerf.csproj -c Release -v q
dotnet publish build/aot/DtPerf.csproj -c Release -r $RID -o bin-aot -v q
declare -A RT=( [net8]="dotnet build/jit/bin/Release/net8.0/DtPerf.dll" [net10]="dotnet build/jit/bin/Release/net10.0/DtPerf.dll" [aot]="./bin-aot/DtPerf" )
lscpu > $OUT/platform.txt 2>/dev/null || true; ${RT[net10]} env >> $OUT/platform.txt
for r in net8 net10 aot; do ${RT[$r]} micro $OUT/micro_$r.csv; done
echo "Runtime,Strategy,P,BuildMs,FirstCallMs,SecondCallMs" > $OUT/cold.csv
for rep in $(seq 1 10); do for r in net8 net10 aot; do for p in 5 20 50; do for s in Reflection ReflectionInvoker CompiledPerProperty CompiledWhole Generated; do
  ${RT[$r]} cold $p $s >> $OUT/cold.csv; done; done; done; done
# closed-loop experiment (v2 protocol: full-cycle budget, per-fleet references, held-out budgets, ablation, sensitivity)
OUT=$OUT SEEDS=${SEEDS} ./run_v2.sh
echo done > $OUT/DONE
