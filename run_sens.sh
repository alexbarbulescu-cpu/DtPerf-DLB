#!/usr/bin/env bash
OUT=results/cloud-xeon; R="dotnet build/jit/bin/Release/net10.0/DtPerf.dll"
echo "Theta,Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare" > $OUT/sensitivity.csv
for th in 0.0005 0.005; do
  for seed in 1 2; do
    for a in 2500 5000 7500 10000 15000 20000 30000; do
      for s in Reflection CompiledWhole Generated; do
        echo "$th,$(DT_THETA=$th $R sim $s $a 10 200 $seed)" >> $OUT/sensitivity.csv
      done
    done
    echo "$th,$(DT_THETA=$th $R sim Generated 2500 1000 200 $seed)" >> $OUT/sensitivity.csv
  done
done
echo done > $OUT/SENS_DONE
