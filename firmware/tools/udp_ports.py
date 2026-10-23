# SPDX-License-Identifier: MIT
"""Free local UDP ports for the trials with the host program (rns_interop.py, rns_osp_node.py).

Fixed ports collide when two trials run on one machine at the same time (Reticulum then fails to create
its UDP interface and ends the process with code 255). The system assigns each port (bind to port 0);
the sockets are closed before the programs bind them, which leaves a short window, but no fixed number.
"""
import socket


def free_udp_ports(count: int) -> list[int]:
    sockets = []
    try:
        for _ in range(count):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", 0))
            sockets.append(s)
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()
