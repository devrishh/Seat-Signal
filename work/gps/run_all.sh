#!/bin/bash
cd "$(dirname "$0")/../.."   # repo root
for d in 16 14 15 18; do
  if [ ! -f work/gps/speed_2026_10_$d.npz ]; then
    python3 pipeline/gps_speed.py ../gps/bus_movements_2026_10_$d.db work/gps/speed_2026_10_$d.npz 3 > work/gps/log_$d.txt 2>&1
  fi
done
echo ALLDONE > work/gps/status.txt
