#!/bin/zsh
cd ~/WICI-L0/proby
./prepwait.sh P001 || exit 1
echo "EMC start $(date +%T)"; ./c P001 -w 1 'EMC 6 255' | tail -1
sleep 66
./c P001 -w 1 EMC | tail -1; ./c P001 -w 1 'EMC 0' | tail -1; echo "EMC stop $(date +%T)"
./c P001 -w .5 'PREP 0' > /dev/null; ./c P001 -w .7 INFO | grep -oE '"prep":[a-z]+'
