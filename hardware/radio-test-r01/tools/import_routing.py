# SPDX-License-Identifier: MIT
"""Import a local Specctra session into the placed controller candidate."""
from pathlib import Path
import sys
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / 'cad/radio-usb-controller.kicad_pcb'
board = k.LoadBoard(str(target))
if not k.ImportSpecctraSES(board, sys.argv[1]):
    raise RuntimeError('Specctra session import failed')
board.BuildConnectivity()
k.SaveBoard(str(target), board)
print('Imported routing. DRC and release gates remain required.')
