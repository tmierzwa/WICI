#!/bin/zsh
# Odrzucone ramki na A: 20 min z samym A zasilonym (B, oba XIAO odłączone, węzeł wrogi bez nadawania), podsłuch jako świadek.
cd ~/WICI-L0/proby
H=~/Work/WICI/implementacja/.claude/worktrees/proby-przy-stole-l0-be3c91/hardware/xiao-wici
(cd $H && ~/WICI-L0/.venv/bin/python tools/monitor.py /dev/cu.usbmodem21301 --out $H/evidence/podsluch-cisza-a-l0-2026-11-17.jsonl \
   --ifac "$(cat ~/WICI-L0/st/ifac.txt)" --net-id 100 --duration 1230 > log/monitor-cisza.out 2>&1) &
sleep 5
for i in $(seq 0 10); do
  echo "A $(date +%T) $(./c P001 -w .7 P1 | grep -oE '"(rx_ok|rx_bad|rx_late|rx_ring_overflow|header_only|split_lost|tx_datagrams|cca_threshold_dbm)":-?[0-9]+' | tr '\n' ' ')"
  (( i < 10 )) && sleep 120
done
wait; tail -2 log/monitor-cisza.out; echo "DONE $(date +%T)"
