#!/usr/bin/env bash
# v3 additions (primary platform): repeated-process microbenchmarks, S4/S5 control (S5b), null materializer (c_u),
# decision-policy sensitivity, GC controls, long-horizon runs, theta below 0.0005, c_mc benchmark, snapshot verification.
# Usage: ./run_v3.sh A   (stages 0-3)   |   ./run_v3.sh B   (stages 4-7)
OUT=${OUT:-results/cloud-xeon/v3}; mkdir -p $OUT/micro_rep $OUT/microctl
J="build/jit/bin/Release"; declare -A RT=( [net8]="$J/net8.0/DtPerf.dll" [net10]="$J/net10.0/DtPerf.dll" [aot]="./bin-aot/DtPerf" )
run() { local r=$1; shift; if [ "$r" = aot ]; then ${RT[aot]} "$@"; else dotnet ${RT[$r]} "$@"; fi; }
export DT_THETA=${DT_THETA:-0.001}
FLEETS="2500 5000 7500 10000 15000 20000 30000"
if [ "$1" = A ]; then
  [ -f $OUT/S0_DONE ] || { for r in net8 net10 aot; do echo "$r,$(run $r verify)"; done > $OUT/verify.txt
    for rep in 1 2 3 4 5; do for r in net8 net10 aot; do echo "$r,$rep,$(run $r mcbench 2000000)"; done; done > $OUT/mcbench.csv; echo done > $OUT/S0_DONE; }
  [ -f $OUT/S1_DONE ] || { for rep in $(seq 1 10); do for r in net8 net10 aot; do
      DT_ITERLOG=$OUT/micro_rep/iterlog_${r}_$rep.csv run $r micro $OUT/micro_rep/${r}_$rep.csv 2>/dev/null; done; done; echo done > $OUT/S1_DONE; }
  [ -f $OUT/S2_DONE ] || { for rep in 1 2 3; do for r in net8 net10 aot; do run $r microctl $OUT/microctl/${r}_$rep.csv 2>/dev/null; done; done; echo done > $OUT/S2_DONE; }
  [ -f $OUT/S3_DONE ] || { for seed in 1 2 3 4 5; do for r in net10 net8 aot; do for a in $FLEETS; do run $r sim GeneratedLookup $a 10 200 $seed; done; done; done > $OUT/sim_s5b.csv
      for seed in 1 2 3; do for a in $FLEETS; do run net10 sim Null $a 10 200 $seed; done; done > $OUT/sim_null.csv; echo done > $OUT/S3_DONE; }
fi
if [ "$1" = B ]; then
  [ -f $OUT/S4_DONE ] || { for pol in fb2 jeffreys; do for seed in 1 2 3 4 5; do for a in $FLEETS; do for s in Reflection ReflectionInvoker CompiledWhole Generated; do
        echo "$pol,$(DT_POLICY=$pol run net10 sim $s $a 10 200 $seed)"; done; done; done; done > $OUT/policy.csv
      for seed in 1 2 3 4 5; do for a in $FLEETS; do echo "jeffreys,$(DT_POLICY=jeffreys run net10 sim Generated $a 1000 200 $seed)"; done; done > $OUT/policy_reference.csv
      for a in 2500 10000 30000; do echo "fb2,$(DT_POLICY=fb2 run net10 sim Generated $a 1000 200 1)"; done >> $OUT/policy_reference.csv
      echo done > $OUT/S4_DONE; }
  [ -f $OUT/S5_DONE ] || { for mode in base concurrent fence; do for seed in 1 2 3; do for a in 10000 20000; do for s in Reflection Generated; do
        case $mode in concurrent) e="DOTNET_gcConcurrent=1";; fence) e="DT_GCFENCE=1";; *) e="";; esac
        r=$(env $e DT_GCLOG=1 dotnet ${RT[net10]} sim $s $a 10 200 $seed 2>$OUT/gc.err); echo "$mode,$r,$(tr -d '\n' < $OUT/gc.err)"; done; done; done; done > $OUT/gc_modes.csv; echo done > $OUT/S5_DONE; }
  [ -f $OUT/S6_DONE ] || { for seed in 1 2 3; do for a in 7500 10000 15000 20000; do for s in Reflection CompiledWhole Generated; do
        DT_BURNIN=300 run net10 sim $s $a 10 600 $seed; done; DT_BURNIN=300 run net10 sim Generated $a 1000 600 $seed; done; done > $OUT/long.csv; echo done > $OUT/S6_DONE; }
  [ -f $OUT/S7_DONE ] || { for th in 0.0001 0.0002; do for seed in 1 2 3; do echo "$th,$(DT_THETA=$th run net10 sim Generated 2500 1000 200 $seed)"; done
        for seed in 1 2; do echo "$th,$(DT_THETA=$th run net10 sim Generated 10000 1000 200 $seed)"; done; done > $OUT/calibration_low.csv; echo done > $OUT/S7_DONE; }
fi
