#!/usr/bin/env bash
R="dotnet build/jit/bin/Release/net10.0/DtPerf.dll"
for seed in 1 2 3; do echo "$1,$(DT_THETA=$1 $R sim Generated 2500 1000 200 $seed)"; done
