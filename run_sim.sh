#!/usr/bin/env bash
OUT=results/cloud-xeon
declare -A RT=( [net8]="dotnet build/jit/bin/Release/net8.0/DtPerf.dll" [net10]="dotnet build/jit/bin/Release/net10.0/DtPerf.dll" [aot]="./bin-aot/DtPerf" )
echo "Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare" > $OUT/sim.csv
for seed in 1 2 3; do for r in net10 net8 aot; do for a in 2500 5000 7500 10000 15000 20000 30000; do for s in Reflection ReflectionInvoker CompiledPerProperty CompiledWhole Generated; do
  ${RT[$r]} sim $s $a 10 200 $seed >> $OUT/sim.csv; done; done; done; done
for seed in 1 2 3; do ${RT[net10]} sim Generated 2500 1000 200 $seed >> $OUT/sim.csv; done
echo "Theta,Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare" > $OUT/sensitivity.csv
for th in 0.0005 0.005; do for seed in 1 2; do for a in 2500 5000 7500 10000 15000 20000 30000; do for s in Reflection CompiledWhole Generated; do
  echo "$th,$(DT_THETA=$th ${RT[net10]} sim $s $a 10 200 $seed)" >> $OUT/sensitivity.csv; done; done; done
  echo "$th,$(DT_THETA=$th ${RT[net10]} sim Generated 2500 1000 200 $seed)" >> $OUT/sensitivity.csv; done; done
echo done > $OUT/SIM_DONE
