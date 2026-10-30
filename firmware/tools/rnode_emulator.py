# SPDX-License-Identifier: MIT
"""Emulator of an RNode radio for RNodeInterface of Reticulum (Python), without a radio.

A pseudo-terminal speaks the RNode serial protocol (KISS) exactly as RNodeInterface.py of Reticulum e40191b
reads it: CMD_DETECT answered with 0x46, firmware version 1.86 (at least 1.52 is required), platform 0x90 (AVR:
no display), MCU; every setting (frequency, bandwidth, TX power, spreading factor, coding rate, radio state,
airtime limits) is echoed at once, within the 0.25 s that RNodeInterface waits before it compares them; KISS data
frames go both ways; flow control is off (no CMD_READY needed).

A packet from the computer becomes on-air frames as the RNode firmware makes them (rnode_framing.rnode_transmit,
the same reference that tests/test_loraframe.py checks the station frame against): a header byte, a split above
254 B, a third header-only frame at exactly 508 B; packets over 508 B vanish without a message, as in RNode. Each
frame is one UDP datagram to the station program (node_host --link lora); frames from the station are assembled
as RNode does (rnode_framing.RNodeReceiver) and passed to the computer. Packets are not delayed by air time: the
silence debt belongs to the station side, the computer side of the link is only an adapter.

The emulator and the station frame come from the same reading of the RNode source, so a run proves interworking
with RNodeInterface, not conformance with the real firmware over the air (that is the hardware trial).

Usage: rnode_emulator.py --listen PORT --peer PORT
Prints one JSON line {"pty": "<port to give RNodeInterface>"} and runs until stdin closes or SIGTERM.
"""

import argparse
import json
import os
import random
import select
import socket
import sys
import tty

from rnode_framing import RNodeReceiver, rnode_transmit

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_BANDWIDTH, CMD_TXPOWER, CMD_SF, CMD_CR, CMD_RADIO_STATE = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06
CMD_DETECT, CMD_LEAVE, CMD_ST_ALOCK, CMD_LT_ALOCK = 0x08, 0x0A, 0x0B, 0x0C
CMD_PLATFORM, CMD_MCU, CMD_FW_VERSION = 0x48, 0x49, 0x50
DETECT_REQ, DETECT_RESP = 0x73, 0x46
PLATFORM_AVR = 0x90        # RNodeInterface: bez ekranu (ESP32 i nRF52 uruchamiają odczyt wyświetlacza)
MCU_NRF52 = 0x71
FIRMWARE = (1, 86)         # wydanie, z którym zgodny jest wzorzec (RNodeInterface wymaga co najmniej 1.52)
MTU = 508
# Ile bajtów danych ma polecenie: wartość odesłana jako echo bez zmian.
ECHOED = {CMD_FREQUENCY: 4, CMD_BANDWIDTH: 4, CMD_TXPOWER: 1, CMD_SF: 1, CMD_CR: 1, CMD_RADIO_STATE: 1,
          CMD_ST_ALOCK: 2, CMD_LT_ALOCK: 2}


def escape(data):
    return data.replace(bytes([FESC]), bytes([FESC, TFESC])).replace(bytes([FEND]), bytes([FESC, TFEND]))


def kiss(command, data=b""):
    return bytes([FEND, command]) + escape(data) + bytes([FEND])


class Emulator:
    def __init__(self, listen, peer):
        self.master, self.slave = os.openpty()
        tty.setraw(self.slave)   # ustawienia terminala zostają, dopóki trzymamy stronę podrzędną
        self.name = os.ttyname(self.slave)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", listen))
        self.peer = ("127.0.0.1", peer)
        self.on = False
        self.receiver = RNodeReceiver()
        self.buffer = b""          # bajty od komputera do rozpoznania ramki KISS
        self.stats = {"packets_out": 0, "packets_in": 0, "frames_out": 0, "frames_in": 0, "dropped_over_mtu": 0}

    def write(self, frame):
        while frame:
            frame = frame[os.write(self.master, frame):]

    # --- komputer -> radio -------------------------------------------------------------------
    def serial_input(self, data):
        # Ramki KISS: FEND polecenie dane FEND; to, co po ostatnim FEND, czeka na dalsze bajty.
        *frames, self.buffer = (self.buffer + data).split(bytes([FEND]))
        for body in frames:
            if body:
                self.command(body[0], self.unescape(body[1:]))

    @staticmethod
    def unescape(data):
        return data.replace(bytes([FESC, TFEND]), bytes([FEND])).replace(bytes([FESC, TFESC]), bytes([FESC]))

    def command(self, command, data):
        if command == CMD_DETECT:
            if data[:1] == bytes([DETECT_REQ]):
                self.write(kiss(CMD_DETECT, bytes([DETECT_RESP])))
        elif command == CMD_FW_VERSION:
            self.write(kiss(CMD_FW_VERSION, bytes(FIRMWARE)))
        elif command == CMD_PLATFORM:
            self.write(kiss(CMD_PLATFORM, bytes([PLATFORM_AVR])))
        elif command == CMD_MCU:
            self.write(kiss(CMD_MCU, bytes([MCU_NRF52])))
        elif command in ECHOED:
            if len(data) == ECHOED[command]:
                if command == CMD_RADIO_STATE:
                    self.on = data[0] == 1
                self.write(kiss(command, data))
        elif command == CMD_DATA:
            self.transmit(data)

    def transmit(self, packet):
        # RNode nadaje tylko 1..508 B; dłuższy pakiet przepada bez komunikatu (RNode_Firmware.ino:589, 628).
        if not self.on or not 1 <= len(packet) <= MTU:
            self.stats["dropped_over_mtu"] += len(packet) > MTU
            return
        self.stats["packets_out"] += 1
        for frame in rnode_transmit(packet, random.randrange(16)):
            self.sock.sendto(frame, self.peer)
            self.stats["frames_out"] += 1

    # --- radio -> komputer -------------------------------------------------------------------
    def air_input(self, frame):
        self.stats["frames_in"] += 1
        if not self.on or not frame:
            return
        packet = self.receiver.receive(frame)
        if packet:
            self.stats["packets_in"] += 1
            self.write(kiss(CMD_DATA, packet))

    def run(self):
        while True:
            ready, _, _ = select.select([self.master, self.sock, sys.stdin], [], [])
            if self.master in ready:
                self.serial_input(os.read(self.master, 4096))
            if self.sock in ready:
                self.air_input(self.sock.recv(2048))
            if sys.stdin in ready and not sys.stdin.readline():
                return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", type=int, required=True, help="UDP port of frames from the station")
    parser.add_argument("--peer", type=int, required=True, help="UDP port of the station program")
    args = parser.parse_args()
    emulator = Emulator(args.listen, args.peer)
    print(json.dumps({"pty": emulator.name}), flush=True)
    try:
        emulator.run()
    except (KeyboardInterrupt, OSError):
        pass


if __name__ == "__main__":
    main()
