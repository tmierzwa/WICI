#!/bin/zsh
# Próba 17, krok 3: 24 h zwykłego ruchu bez węzła wrogiego. REQ 1 na XIAO nr 2 co 30 min (rejestr A pełny: 256 zgłoszeń bez decyzji z poprzednich prób), BEACON-y.
# Co minutę skrót P1/INFO ze wszystkich węzłów, co godzinę pełne P1, INFO, RNS (pamięć). Root z main 86c0e44a, reszta z 29d15b10.
cd ~/WICI-L0/proby
caffeinate -i -w $$ &
H=~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/hardware/xiao-wici
EV=$H/evidence; DAY=2026-11-16; TAG=doba; DUR=86400
ALL=(P001 P002 X2 X1)
(cd $H && ~/WICI-L0/.venv/bin/python tools/monitor.py /dev/cu.usbmodem21301 --out $EV/podsluch-$TAG-l0-$DAY.jsonl \
   --ifac "$(cat ~/WICI-L0/st/ifac.txt)" --net-id 100 --duration $((DUR + 300)) > ~/WICI-L0/proby/log/monitor-$TAG.out 2>&1) &
full() { for n in $ALL; do ./c $n -w 1 P1 INFO RNS | grep -E 'no_gap|channel_jammed|heap_free' | sed "s/^/$1 $n /"; done; }
sleep 5
full S0
t0=$(date +%s); echo "== start $(date '+%F %T')"
k=0
while (( $(date +%s) < t0 + DUR )); do
  if (( k % 30 == 0 )); then echo "REQ $(date +%T) $(./c X2 -w .7 'REQ 1' | grep -oE '"numbers":[^]]*]' )"; fi
  if (( k % 60 == 0 && k > 0 )); then full H$((k / 60)); fi
  for n in $ALL; do
    echo "M $(date +%T) $n $(./c $n -w .5 P1 INFO | grep -oE '"(tx_datagrams|tx_drop|deferrals|no_gap_ms|no_gap_ms_max|channel_jammed|probes|probe_busy|restarts)":[a-z0-9-]*' | sort -u | tr '\n' ' ')"
  done
  echo "A $(date +%T) $(./c X2 -w .5 APP | grep -oE '"intents":[0-9]*')"
  k=$((k + 1))
  sleep $(( t0 + k * 60 - $(date +%s) > 0 ? t0 + k * 60 - $(date +%s) : 1 ))
done
full S1
echo "DONE $(date '+%F %T')"
