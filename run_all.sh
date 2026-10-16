#!/usr/bin/env bash
# Linux runner (same protocol as run-all.ps1). Usage: ./run_all.sh <label> [seeds]
set -euo pipefail
LABEL=${1:-linux}; SEEDS=${2:-3}; OUT=results/$LABEL; mkdir -p $OUT
RID=${RID:-linux-x64}
dotnet build build/jit/DtPerf.csproj -c Release -v q
dotnet publish build/aot/DtPerf.csproj -c Release -r $RID -o bin-aot -v q
declare -A RT=( [net8]="dotnet build/jit/bin/Release/net8.0/DtPerf.dll" [net10]="dotnet build/jit/bin/Release/net10.0/DtPerf.dll" [aot]="./bin-aot/DtPerf" )
lscpu > $OUT/platform.txt 2>/dev/null || true; ${RT[net10]} env >> $OUT/platform.txt
for r in net8 net10 aot; do ${RT[$r]} micro $OUT/micro_$r.csv; done
echo "Runtime,Strategy,P,BuildMs,FirstCallMs,SecondCallMs" > $OUT/cold.csv
for rep in $(seq 1 10); do for r in net8 net10 aot; do for p in 5 20 50; do for s in Reflection ReflectionInvoker CompiledPerProperty CompiledWhole Generated; do
  ${RT[$r]} cold $p $s >> $OUT/cold.csv; done; done; done; done
echo "Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare" > $OUT/sim.csv
for seed in $(seq 1 $SEEDS); do for r in net10 net8 aot; do for a in ${FLEETS:-2500 5000 7500 10000 15000 20000 30000}; do for s in Reflection ReflectionInvoker CompiledPerProperty CompiledWhole Generated; do
  ${RT[$r]} sim $s $a ${BUDGET:-10} 200 $seed >> $OUT/sim.csv; done; done; done; done
for seed in $(seq 1 $SEEDS); do ${RT[net10]} sim Generated 2500 1000 200 $seed >> $OUT/sim.csv; done   # unconstrained reference
echo done > $OUT/DONE
