# SPDX-License-Identifier: MIT
"""SA1 between the station Reticulum core and Python LXMF (shared by rns_interop.py and rns_osp_node.py).

The station application layer passes an envelope ["WICI",1,"<from>","<to>",<SA1>] with "wici.sa1"
destinations of the card receiver; the core (firmware/src/rns_node_core.cpp) carries the SA1 part as an
LXMF message to "lxmf.delivery" and back. Needs Reticulum at e40191b and LXMF at c3ff2d6.
"""


def envelope(sender: bytes, receiver: bytes, content: bytes) -> bytes:
    """Application-layer envelope (station.cpp, Station::transmit)."""
    return b'["WICI",1,"' + sender.hex().encode() + b'","' + receiver.hex().encode() + b'",' + content + b"]"


def sa1_of(identity) -> bytes:
    """The "wici.sa1" destination of an identity: how the station application layer addresses the card receiver."""
    import RNS
    return RNS.Destination.hash(identity, "wici", "sa1")


def carried(destination_hash: bytes, data: bytes, content: bytes) -> bool:
    """Packet data received in Python is an LXMF SA1 message with exactly this content."""
    import LXMF
    try:
        message = LXMF.LXMessage.unpack_from_bytes(destination_hash + data)
    except Exception:
        return False
    return message.title == b"SA1" and message.content == content


def packed(out, source, content: bytes) -> bytes:
    """Packet data of an opportunistic LXMF SA1 message from source to out (LXMessage.pack)."""
    import LXMF
    import RNS
    message = LXMF.LXMessage(out, source, content.decode(), "SA1", desired_method=LXMF.LXMessage.OPPORTUNISTIC)
    message.pack()
    return message.packed[RNS.Identity.TRUNCATED_HASHLENGTH // 8:]
