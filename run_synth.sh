#!/usr/bin/env bash
OUT=results/cloud-xeon; R="dotnet build/jit/bin/Release/net10.0/DtPerf.dll"
echo "Runtime,Strategy,Assets,BudgetMs,Seed,Ticks,CostPer1kAssetTicks,FailuresPer1k,PmPer1k,IngestMs,IngestShare,DroppedShare,Candidates,UnsampledCandShare,SamplesPerCand,OverrunShare" > $OUT/synthetic.csv
for seed in 1 2; do
  for x in 0 250 500 1000 2000 4000; do
    for a in 1000 2500 5000 7500 10000 15000 20000 30000; do
      $R sim Synthetic$x $a 10 200 $seed >> $OUT/synthetic.csv
    done
  done
done
echo done > $OUT/SYNTH_DONE
