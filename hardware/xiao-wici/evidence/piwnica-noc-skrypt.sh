#!/bin/zsh
# Noc 15/16.11 w piwnicy: kandydaci CHANNEL 0 0 i 1 1 (po 2 h przy 50%), potem próba 17 (50/70/90% po 20 min).
# Każdy przebieg: własny podsłuch, węzeł wrogi bez klucza (-9 dBm, --conducted), zgłoszenia z A, P1/INFO co 10 s.
cd ~/WICI-L0/proby
H=~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/hardware/xiao-wici
EV=$H/evidence; DAY=2026-11-15
ALL=(P001 P002 X1 X2)

snap() {  # snap TAG: liczniki ze wszystkich
  for n in $ALL; do ./c $n -w 1 HACK P1 INFO | sed "s/^/$1 $n /"; done
  ./c P002 -w 1 RNS | grep '"rns"' | sed "s/^/$1 P002 /"
}

run() {  # run TAG OCC SEED DUR REQN CH_CAD CH_DEF
  local TAG=$1 OCC=$2 SEED=$3 DUR=$4 REQN=$5
  for n in $ALL; do ./c $n -w .5 "CHANNEL $6 $7" >/dev/null; ./c $n -w .5 "HACK 0" >/dev/null; done
  (cd $H && ~/WICI-L0/.venv/bin/python tools/monitor.py /dev/cu.usbmodem21201 --out $EV/podsluch-$TAG-l0-$DAY.jsonl \
     --ifac "$(cat ~/WICI-L0/st/ifac.txt)" --net-id 100 --duration $((DUR + 600)) > ~/WICI-L0/proby/log/monitor-$TAG.out 2>&1) &
  sleep 5
  echo "== $TAG occ $OCC CHANNEL $6 $7 start $(date +%T)"
  snap S0-$TAG
  (cd $H && ~/WICI-L0/stvenv/bin/python tools/hostile.py /dev/cu.usbmodem214101 --mode junk --occupancy $OCC \
     --duration $DUR --power -9 --seed $SEED --conducted --out $EV/wrogi-$TAG-l0-$DAY.jsonl > ~/WICI-L0/proby/log/hostile-$TAG.out 2>&1) &
  local HP=$!
  sleep 20
  ./c P001 -w .7 "REQ $REQN" | grep numbers | sed "s/^/REQ $TAG /"
  local t0=$(date +%s) done=0
  while kill -0 $HP 2>/dev/null || (( ! done && $(date +%s) < t0 + DUR + 600 )); do
    for n in $ALL; do ./c $n -w .4 P1 | grep no_gap | sed "s/^/P1 $TAG $n /"; done
    if (( ! done )); then
      c=$(./c P001 -w .5 APP | grep intents); echo "A $TAG $c"
      print -r -- "$c" | grep -q '"intents":0,' && { echo "ADONE $TAG $(date +%T) po $(( $(date +%s) - t0 )) s"; done=1; }
    fi
    for n in $ALL; do ./c $n -w .3 INFO | grep -o '"channel_jammed":[a-z]*' | sed "s/^/J $TAG $n $(date +%T) /"; done
    sleep 5
  done
  echo "HOSTILE end $TAG $(date +%T)"; grep -A3 '"occupancy"' log/hostile-$TAG.out | head -2
  snap S1-$TAG
  wait
}

sleep 300
run kand11 0.5 9202 2700 20 1 1
sleep 900
for n in $ALL; do ./c $n -w .5 "CHANNEL 0 0" >/dev/null; done
run jam50 0.5 9250 1200 5 0 0
sleep 600
run jam70 0.7 9270 1200 5 0 0
sleep 600
run jam90 0.9 9290 1200 5 0 0
echo "NIGHT DONE $(date +%T)"
