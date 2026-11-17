#!/bin/zsh
# Próba 17: root bez ruchu przy 90% (R3-46), obraz roota main 86c0e44a z licznikami probes/probe_busy; konsola roota zamiast panelu.
cd ~/WICI-L0/proby
H=~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/hardware/xiao-wici
EV=$H/evidence; DAY=2026-11-16; TAG=jam90probe; DUR=1200
ALL=(P001 P002 X2 X1)
(cd $H && ~/WICI-L0/.venv/bin/python tools/monitor.py /dev/cu.usbmodem21301 --out $EV/podsluch-$TAG-l0-$DAY.jsonl \
   --ifac "$(cat ~/WICI-L0/st/ifac.txt)" --net-id 100 --duration $((DUR + 600)) > ~/WICI-L0/proby/log/monitor-$TAG.out 2>&1) &
sleep 5
for n in $ALL; do ./c $n -w 1 P1 INFO | sed "s/^/S0 $n /"; done
echo "== start $(date +%T)"
(cd $H && ~/WICI-L0/stvenv/bin/python tools/hostile.py /dev/cu.usbmodem214201 --mode junk --occupancy 0.9 \
   --duration $DUR --power -9 --seed 9491 --conducted --out $EV/wrogi-$TAG-l0-$DAY.jsonl > ~/WICI-L0/proby/log/hostile-$TAG.out 2>&1) &
HP=$!
end=0
while true; do
  for n in $ALL; do ./c $n -w .4 P1 | grep no_gap | sed "s/^/P1 $(date +%T) $n /"; done
  for n in $ALL; do ./c $n -w .3 INFO | grep -o '"channel_jammed":[a-z]*' | sed "s/^/J $(date +%T) $n /"; done
  if ! kill -0 $HP 2>/dev/null; then (( end == 0 )) && { echo "HOSTILE end $(date +%T)"; end=$(date +%s); }; fi
  (( end && $(date +%s) > end + 360 )) && break
  sleep 5
done
for n in $ALL; do ./c $n -w 1 P1 INFO | sed "s/^/S1 $n /"; done
grep -A1 '"occupancy"' log/hostile-$TAG.out | head -2
echo "DONE $(date +%T)"
