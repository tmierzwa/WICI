# SPDX-License-Identifier: MIT
"""Receiver-side collection of authenticated bearers (stanowisko-osp.md, „Nośniki odpowiedzi”).

The database thread selects a bearer for each reply: the operator's choice, else
the bearer of the last fresh authenticated message from that station, else the
primary. A receive path records its choice in the same durable transaction as
admission, so unauthenticated or replayed traffic cannot move the reply route
and a reboot preserves the last verified path. The selected bearer never changes
by itself: a reply it cannot carry now, or whose delivery failed, waits in the
queue (wysylka.py) and retries on the same bearer, and only the duty officer
moves a station to another one (WICI-INV-048).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Delivery:
    bearer: str
    dest: bytes
    message: object


class Bearers:
    def __init__(self, bindings, primary):
        self.bindings = dict(bindings)
        if not self.bindings or primary not in self.bindings:
            raise ValueError("invalid primary bearer")
        self.primary = primary
        self.reception = None
        self.address = self.bindings[primary].address

    def start(self):
        started = []
        try:
            for bearer in self.bindings.values():
                bearer.start()
                started.append(bearer)
        except Exception:
            for bearer in reversed(started):
                bearer.stop()
            raise

    def stop(self):
        for bearer in self.bindings.values():
            bearer.stop()

    def announce(self):
        for bearer in self.bindings.values():
            bearer.announce()

    def status(self, now):
        states = {name: bearer.status(now) for name, bearer in self.bindings.items()}
        return {"online": any(state["online"] for state in states.values()),
                "since_rx": min((state["since_rx"] for state in states.values()
                                 if state.get("since_rx") is not None), default=None),
                "dropped": {name: state.get("dropped", {}) for name, state in states.items()},
                "bearers": states}

    def _send(self, chosen, dest, content):
        bearer = self.bindings[chosen]
        return self.reception.send_wici(bearer, dest, content) if chosen == "wici" else bearer.send(dest, content)

    def send(self, dest, content):
        if self.reception is None:
            raise RuntimeError("receiver not bound")
        override = self.reception.bearer_override.get(dest)
        if override is not None:
            message = self._send(override, dest, content) if override in self.bindings else None
            return Delivery(override, dest, message) if message is not None else None
        chosen = self.reception.last_bearer.get(dest, self.primary)
        if chosen not in self.bindings:
            chosen = self.primary
        message = self._send(chosen, dest, content)
        return Delivery(chosen, dest, message) if message is not None else None

    def outcome(self, delivery):
        return self.bindings[delivery.bearer].outcome(delivery.message)
