# SPDX-License-Identifier: MIT
"""Transcription of the framing of the official RNode firmware (the reference of the LoRa frame of the station).

One source for two users: tests/test_loraframe.py (against firmware/src/loraframe.cpp) and
firmware/tools/rnode_emulator.py (the RNode that RNodeInterface of Reticulum talks to). Also the RNodeInterface
section of the Reticulum config in the pilot LoRa profile, for rns_interop.py (emulator) and rnode_trial.py (radio)."""

# RNode firmware: markqvist/RNode_Firmware commit 56775c51b60a6190242e324c210997dcc7637e53
FLAG_SPLIT = 0x01      # Framing.h:107
SEQ_UNSET = 0xFF       # Framing.h:108
MTU = 508              # Config.h:59
SINGLE_MTU = 255       # Config.h:60
HEADER_L = 1           # Config.h:61

# Profil LoRa pilotażu (lora_profile.h, radio.md): 869,525 MHz, 125 kHz, SF7, CR 4/5, 13 dBm.
FREQUENCY_HZ = 869525000
IFAC_BITS = 128        # IFAC 16 B jak w stacji; domyślne 8 B stacja odrzuci jako ifac_invalid


def rnode_interface(port, passphrase, txpower=13):
    """Section [[LoRa RNode]] of the Reticulum config: an RNodeInterface in the pilot LoRa profile with the station
    network key as IFAC (16 B). Flow control off: the emulator never sends CMD_READY, and the trial needs none."""
    if any(c in str(port) for c in "\r\n[]"):
        raise ValueError("port: forbidden characters")
    return f"""  [[LoRa RNode]]
    type = RNodeInterface
    enabled = Yes
    port = {port}
    frequency = {FREQUENCY_HZ}
    bandwidth = 125000
    txpower = {int(txpower)}
    spreadingfactor = 7
    codingrate = 5
    flow_control = No
    passphrase = {passphrase}
    ifac_size = {IFAC_BITS}
"""


def rnode_transmit(data, header_nibble):
    """transmit() in RNode_Firmware.ino:716-745: the header is `random(256) & 0xF0` (here: the nibble given),
    FLAG_SPLIT above SINGLE_MTU - HEADER_L = 254 B; after 255 written bytes of a split packet the frame ends
    and a new one starts with the same header. A packet of exactly 508 B ends with a third, header-only frame."""
    header = (header_nibble << 4) & 0xF0
    if len(data) > SINGLE_MTU - HEADER_L:
        header |= FLAG_SPLIT
    frames = []
    frame = bytearray([header])
    written = 1
    for byte in data:
        frame.append(byte)
        written += 1
        if written == 255 and header & FLAG_SPLIT:
            frames.append(bytes(frame))
            frame = bytearray([header])
            written = 1
    frames.append(bytes(frame))
    return frames


class RNodeReceiver:
    """receive_callback() in RNode_Firmware.ino:365-440 with getPacketData() (lines 345-357): `read_len < MTU`."""

    def __init__(self):
        self.seq = SEQ_UNSET
        self.buffer = bytearray()

    def receive(self, frame):
        header, body = frame[0], frame[1:]
        sequence = header >> 4
        ready = False
        if header & FLAG_SPLIT and self.seq == SEQ_UNSET:
            self.buffer = bytearray()
            self.seq = sequence
            self.append(body)
        elif header & FLAG_SPLIT and self.seq == sequence:
            self.append(body)
            self.seq = SEQ_UNSET
            ready = True
        elif header & FLAG_SPLIT and self.seq != sequence:
            self.buffer = bytearray()
            self.seq = sequence
            self.append(body)
        elif not header & FLAG_SPLIT:
            if self.seq != SEQ_UNSET:
                self.buffer = bytearray()
                self.seq = SEQ_UNSET
            self.append(body)
            ready = True
        if ready:
            packet, self.buffer = bytes(self.buffer), bytearray()
            return packet
        return None

    def append(self, body):
        for byte in body:
            if len(self.buffer) < MTU:
                self.buffer.append(byte)
