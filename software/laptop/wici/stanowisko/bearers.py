# SPDX-License-Identifier: MIT
"""Receiver-side collection of authenticated bearers.

The database thread selects a bearer for each reply. A receive path records its
choice in the same durable transaction as admission, so unauthenticated traffic
cannot move the reply route and a reboot preserves the last verified path.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Delivery:
    bearer: str
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

    def send(self, dest, content):
        if self.reception is None:
            raise RuntimeError("receiver not bound")
        chosen = self.reception.bearer_override.get(
            dest, self.reception.last_bearer.get(dest, self.primary))
        bearer = self.bindings.get(chosen)
        if bearer is None:
            return None
        if chosen == "wici":
            message = self.reception.send_wici(bearer, dest, content)
        else:
            message = bearer.send(dest, content)
        return Delivery(chosen, message) if message is not None else None

    def outcome(self, delivery):
        return self.bindings[delivery.bearer].outcome(delivery.message)
