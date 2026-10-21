#!/usr/bin/env bash
# completes the v2 pipeline after the time-limited run: missing synthetic rows, then the remaining stages of run_v2.sh
OUT=${OUT:-results/cloud-xeon}; export DT_THETA=$(cat $OUT/theta.txt)
while read B s x a; do dotnet build/jit/bin/Release/net10.0/DtPerf.dll sim Synthetic$x $a $B 200 $s >> $OUT/synthetic.csv; done < "$1"
echo done > $OUT/SYN_DONE
./run_v2.sh
