# SPDX-License-Identifier: MIT
"""Stack of the receiving station: Reticulum e40191b and LXMF c3ff2d6 in Python behind the OSP node.

docs/spec/stanowisko-osp.md, „Komputer i aplikacja stanowiska”: one Reticulum interface, KISS to the
station over USB with flow control; transport, network interfaces and the shared instance off (the node
forwards); LXMF only opportunistic, without propagation and stamps. The receipt and retry time-outs of
the stack come from the `bitrate` of the KISS interface in the configuration alone (radio.md, criterion
`bitrate`), without changes in the stack code (condition of D19).

The receiver identity comes from the station medium (nosnik.py, sealed with its data key); the state
directory (siec/ on the medium) holds Reticulum and LXMF storage. Only messages with a checked signature go on to reception (przyjecie.py). LXMF cannot check the signature of
a sender whose identity it does not know yet (SOURCE_UNKNOWN); such a message waits in memory, the stack asks
for a path, and the message goes on when the announce or path response brings the identity („Przyjęcie”).
Waiting messages have the limits of the quarantine (4 per sender, 256 in total) and do not survive a restart,
which is safe: without RECEIVED the station sends them again.
"""

import sys
import threading
from pathlib import Path

# Reticulum i LXMF importuje dopiero Stos: konfigurację i resztę aplikacji da się sprawdzić bez stosu.

# Kryterium z radio.md („Ponowienia i limity prób”): 500 B × 8 / bitrate nie krócej niż odstęp dla 2 skoków
# (około 96 s), czyli najwyżej 41 b/s; T3 może obniżyć tę wartość po pomiarze.
BITRATE = 41
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

    received(source, content) is called from a Reticulum thread for every LXMF message with the SA1 title
    and a checked signature: source is the 16 B "lxmf.delivery" hash of the sender, content the SA1 bytes."""

    PENDING_PER_SENDER, PENDING_TOTAL = 4, 256   # jak kwarantanna (stanowisko-osp.md, O03)

    def __init__(self, state, port, received, identity_key, bitrate=BITRATE, log=None):
        self.state, self.port, self.bitrate = Path(state), port, bitrate
        self.identity_key = identity_key
        self.received = received
        self.log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self.router = self.destination = self.identity = None
        self.pending, self.lock = {}, threading.Lock()   # nadawca -> spakowane wiadomości LXMF do sprawdzenia
        self.dropped = {"bad_signature": 0, "pending_full": 0}

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
        self.identity = RNS.Identity.from_bytes(self.identity_key)
        if self.identity is None:
            raise RuntimeError("klucz tożsamości odbiorcy jest uszkodzony")
        # Bez propagacji, bez wymiany z węzłami propagacji i bez znaczków pracy.
        self.router = LXMF.LXMRouter(storagepath=str(self.state / "lxmf"), autopeer=False, enforce_stamps=False)
        self.destination = self.router.register_delivery_identity(self.identity)
        self.router.register_delivery_callback(self._delivered)
        RNS.Transport.register_announce_handler(self)
        self.announce()

    # Obsługa ogłoszeń dla RNS.Transport: także odpowiedzi na zapytania o trasę, bo o nie pyta _delivered.
    aspect_filter = "lxmf.delivery"
    receive_path_responses = True

    def received_announce(self, destination_hash, announced_identity, app_data):
        with self.lock:
            waiting = self.pending.pop(destination_hash, [])
        for packed in waiting:
            self._check(packed)

    def announce(self):
        """Announce of the receiver address; the station applies the announce limit and radio silence."""
        self.router.announce(self.destination.hash)

    def _delivered(self, message):
        import LXMF
        import RNS
        if message.title_as_string() != TITLE:
            return   # inne wiadomości LXMF nie należą do SA1
        if message.signature_validated:
            self.received(message.source_hash, message.content)
        elif message.unverified_reason == LXMF.LXMessage.SOURCE_UNKNOWN:
            with self.lock:
                waiting = self.pending.setdefault(message.source_hash, [])
                if len(waiting) >= self.PENDING_PER_SENDER or sum(map(len, self.pending.values())) >= self.PENDING_TOTAL:
                    self.dropped["pending_full"] += 1   # stacja ponowi, gdy miejsce się zwolni
                    return
                waiting.append(message.packed)
            RNS.Transport.request_path(message.source_hash)
            if RNS.Identity.recall(message.source_hash) is not None:   # ogłoszenie zdążyło przed wpisem
                self.received_announce(message.source_hash, None, None)
        else:
            self.dropped["bad_signature"] += 1

    def _check(self, packed):
        """A waiting message again, now that the sender identity is known."""
        import LXMF
        message = LXMF.LXMessage.unpack_from_bytes(packed)
        if message.signature_validated:
            self.received(message.source_hash, message.content)
        else:
            self.dropped["bad_signature"] += 1

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

    @staticmethod
    def outcome(message):
        """True after DELIVERED, False after FAILED (also rejected or cancelled), None while in flight."""
        import LXMF
        if message.state == LXMF.LXMessage.DELIVERED:
            return True
        if message.state in (LXMF.LXMessage.FAILED, LXMF.LXMessage.REJECTED, LXMF.LXMessage.CANCELLED):
            return False
        return None

    def stop(self):
        """Detach the interfaces, as Reticulum does at exit (without ending the process)."""
        import RNS
        for interface in list(RNS.Transport.interfaces):
            interface.detach()
