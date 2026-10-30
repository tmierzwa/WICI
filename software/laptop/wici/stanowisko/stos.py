# SPDX-License-Identifier: MIT
"""Stack of the receiving station: Reticulum e40191b and LXMF c3ff2d6 in Python behind the OSP node.

docs/spec/stanowisko-osp.md, „Komputer i aplikacja stanowiska”: one Reticulum interface, KISS to the
station over USB with flow control; transport, network interfaces and the shared instance off (the node
forwards); LXMF only opportunistic, without propagation and stamps. The receipt and retry time-outs of
the stack come from the `bitrate` of the KISS interface in the configuration alone (radio.md, criterion
`bitrate`), without changes in the stack code (condition of D19).

The receiver identity lives in the state directory; from stage S4 that is the encrypted station medium.
Messages that reach the delivery callback are passed on unfiltered: trust, quarantine and RECEIVED
are stage S2 (software/laptop/PLAN.md).
"""

import os
import sys
from pathlib import Path

# Reticulum i LXMF importuje dopiero Stos: konfigurację i resztę aplikacji da się sprawdzić bez stosu.

# Kryterium z radio.md („Ponowienia i limity prób”): 500 B × 8 / bitrate nie krócej niż odstęp dla 2 skoków
# (około 95 s), czyli najwyżej 42 b/s; T3 może obniżyć tę wartość po pomiarze.
BITRATE = 42
TITLE = "SA1"   # tytuł wiadomości LXMF z treścią SA1, jak w rdzeniu stacji (rns_node_core.cpp)


def config(port, bitrate=BITRATE):
    """Text of the Reticulum configuration: the KISS interface to the node and nothing else."""
    if not 1 <= int(bitrate) <= 1200:
        raise ValueError("bitrate: od 1 do 1200 b/s")
    if any(c in str(port) for c in "\r\n[]"):
        raise ValueError("port: niedozwolone znaki")
    return f"""# Wygenerowane przez aplikację stanowiska przy każdym starcie; zmiany ręczne nie przetrwają.
[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = No

[logging]
  loglevel = 3

[interfaces]
  [[Stacja stanowiska]]
    type = KISSInterface
    enabled = Yes
    port = {port}
    speed = 115200
    flow_control = Yes
    bitrate = {int(bitrate)}
"""


class Stos:
    """Reticulum and LXMF of the receiving station. One per process (Reticulum is a process singleton).

    received(source, content, signature_ok) is called from a Reticulum thread for every LXMF message with
    the SA1 title: source is the 16 B "lxmf.delivery" hash of the sender, content the SA1 bytes."""

    def __init__(self, state, port, received, bitrate=BITRATE, log=None):
        self.state, self.port, self.bitrate = Path(state), port, bitrate
        self.received = received
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.router = self.destination = self.identity = None

    @property
    def address(self):
        """Address (destination hash) of the receiver: the "lxmf.delivery" destination of its identity."""
        return self.destination.hash

    def start(self):
        import RNS
        import LXMF
        rns_dir = self.state / "rns"
        rns_dir.mkdir(parents=True, exist_ok=True)
        (rns_dir / "config").write_text(config(self.port, self.bitrate), encoding="utf-8")
        # Funkcja jako logdest: RNS/Reticulum.py, Reticulum.__init__ w e40191b ustawia wtedy RNS.logdest =
        # RNS.LOG_CALLBACK i RNS.logcall = ta funkcja (RNS/__init__.py, log).
        RNS.Reticulum(str(rns_dir), logdest=self.log)
        self.identity = self._identity(self.state / "tozsamosc")
        # Bez propagacji, bez wymiany z węzłami propagacji i bez znaczków pracy.
        self.router = LXMF.LXMRouter(storagepath=str(self.state / "lxmf"), autopeer=False, enforce_stamps=False)
        self.destination = self.router.register_delivery_identity(self.identity)
        self.router.register_delivery_callback(self._delivered)
        self.announce()

    @staticmethod
    def _identity(path):
        """The receiver identity from the file, or a new one written there (fsync before use).

        Only the main identity: the backup one is made at the preparation of the station and leaves it
        in sealed envelopes (stanowisko-osp.md, O10; PLAN.md, stage S4). The private key file is readable
        only by the user (0600) until stage S4 moves it to the encrypted station medium."""
        import RNS
        if path.exists():
            identity = RNS.Identity.from_file(str(path))
            if identity is None:
                raise RuntimeError(f"plik tożsamości odbiorcy jest uszkodzony: {path}")
            return identity
        identity = RNS.Identity()
        tmp = path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)   # pozostałość przerwanego zapisu
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(identity.get_private_key())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return identity

    def announce(self):
        """Announce of the receiver address; the station applies the announce limit and radio silence."""
        self.router.announce(self.destination.hash)

    def _delivered(self, message):
        if message.title_as_string() != TITLE:
            return   # inne wiadomości LXMF nie należą do SA1
        self.received(message.source_hash, message.content, bool(message.signature_validated))

    def send(self, target, content):
        """Opportunistic LXMF message with SA1 content to the "lxmf.delivery" destination target (16 B).

        Returns the LXMessage (its state shows DELIVERED or FAILED), or None while the identity of the
        target is unknown: a path request is sent and the caller tries again later."""
        import RNS
        import LXMF
        identity = RNS.Identity.recall(target)
        if identity is None:
            RNS.Transport.request_path(target)
            return None
        out = RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        message = LXMF.LXMessage(out, self.destination, content.decode("utf-8"), TITLE,
                                 desired_method=LXMF.LXMessage.OPPORTUNISTIC)
        self.router.handle_outbound(message)
        return message

    def stop(self):
        """Detach the interfaces, as Reticulum does at exit (without ending the process)."""
        import RNS
        for interface in list(RNS.Transport.interfaces):
            interface.detach()
