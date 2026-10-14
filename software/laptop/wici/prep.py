# SPDX-License-Identifier: MIT
"""Preparation-mode operations on the connected station: read and write the configuration, read the card.

Each operation returns a JSON-ready dict for the panel and writes one journal entry. Errors become a
sentence for the person at the laptop; the station's own reason code stays in the journal.
"""

import hashlib
import json

from . import configdoc
from .usbproto import ProtocolError, Rejected

REASONS = {
    "prep_required": "Stacja nie jest w trybie przygotowania. Przytrzymaj przycisk pod naklejką serwisową.",
    "not_configured": "Stacja nie ma jeszcze konfiguracji.",
    "role": "Ta czynność nie dotyczy węzła stanowiska.",
    "busy": "Stacja wykonuje inną operację. Spróbuj za chwilę.",
    "memory": "Błąd pamięci stacji. Zapisz numer stacji i zgłoś usterkę.",
    "size": "Dokument jest za duży dla stacji.",
    "hash": "Dane uszkodziły się w drodze (suma kontrolna). Wyślij ponownie.",
    "not_confirmed": "Nie potwierdzono przyciskiem na stacji w ciągu 30 s.",
    "contract": "Stacja ma niezgodną wersję oprogramowania.",
    "unknown_type": "Ta wersja oprogramowania stacji nie zna tego polecenia.",
    "migration": "Stacja jest w trakcie przenoszenia (PRZENIEŚ STACJĘ).",
}
FIELDS = {
    "role": "rola", "addresses": "adresy", "receiver": "karta odbiorcy", "stations": "liczba stacji w sieci",
    "phrases": "gotowe frazy", "ifac": "kod dostępu sieci", "radio": "profil radiowy",
    "worst_request": "najdłuższe zgłoszenie z przycisków",
}


class OperationError(Exception):
    def __init__(self, message, field=None, code=""):
        super().__init__(message)
        self.message, self.field, self.code = message, field, code


def explain(error):
    if isinstance(error, Rejected):
        if error.reason == "invalid" and error.detail:
            if error.detail == "radio":
                return OperationError("Profil radiowy nie pasuje do układu radiowego tej stacji.", "radio", "invalid")
            name = FIELDS.get(error.detail, error.detail)
            return OperationError(f"Stacja odrzuciła pole: {name}.", error.detail, "invalid")
        return OperationError(REASONS.get(error.reason, f"Stacja odmówiła ({error.reason})."), None, error.reason)
    if isinstance(error, ProtocolError):
        return OperationError("Brak odpowiedzi stacji. Sprawdź przewód USB; połączenie zostanie odnowione.", None, "timeout")
    if isinstance(error, OSError):
        return OperationError("Połączenie ze stacją zostało przerwane.", None, "closed")
    raise error


class Prep:
    def __init__(self, station, journal):
        self.station, self.journal = station, journal

    def _identity(self):
        hello = self.station.state.get("hello") or {}
        return hello.get("name", ""), hello.get("lxmf", "")

    def _run(self, op, fn, detail=lambda r: ""):
        name, lxmf = self._identity()
        try:
            result = self.station.call(fn)
        except (Rejected, ProtocolError, OSError) as e:
            err = explain(e)
            self.journal.add(name, lxmf, op, False, err.code + (f" {err.field}" if err.field else ""))
            raise err from e
        self.journal.add(name, lxmf, op, True, detail(result))
        return result

    def read_config(self):
        data = self._run("config_get", lambda link: link.read_transfer("config_get"),
                         lambda d: "sha256 " + hashlib.sha256(d).hexdigest()[:16])
        return {"doc": json.loads(data.decode("utf-8"))}

    def write_config(self, doc):
        doc = configdoc.normalize(doc)
        problems = configdoc.check(doc)
        if problems:
            raise OperationError("Popraw zaznaczone pola.", problems[0][0], "check")
        data = configdoc.encode(doc)
        reply = self._run("configure", lambda link: link.write_transfer("configure", data),
                          lambda r: f"config_seq {r.get('config_seq')} sha256 {hashlib.sha256(data).hexdigest()[:16]}")
        return {"config_seq": reply.get("config_seq"), "worst_request": reply.get("worst_request"),
                "sha256": hashlib.sha256(data).hexdigest(), "doc": doc}

    def card(self):
        reply = self._run("card", lambda link: link.request("card"), lambda r: "fingerprint " + r.get("fingerprint", ""))
        return {"card": {k: reply[k] for k in ("name", "lxmf", "key", "address", "fingerprint") if k in reply}}
