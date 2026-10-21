#!/usr/bin/env bash
# Regenerates every table (CSV) and figure (PNG + PDF) of the manuscript from the raw results in results/.
# Usage: ./reproduce.sh [out_dir]      (requires the packages in requirements.txt; no .NET needed)
set -e
OUT=${1:-out}
python3 analysis/analyze.py results "$OUT/cloud-xeon" cloud-xeon
python3 analysis/analyze_v3.py results "$OUT/cloud-xeon" cloud-xeon
for p in legion-i9-14900hx t14s-ryzen7pro; do python3 analysis/analyze.py results "$OUT/$p" $p; done
echo "Tables and figures written to $OUT/ (see MANIFEST.md for the mapping to the manuscript)."
