# SPDX-License-Identifier: MIT
"""The durable SA1 vectors (tests/vectors/sa1.json) against the station code and the receiving post's code.

The file is the only source of the bytes. Python reads it here and runs the codec the post uses
(wici.stanowisko.wzorzec, that is software/reference/reference.py); the station codec (firmware/src/sa1.cpp) gets the
same bytes through tests/native/sa1_check.cpp, under ASan and UBSan.
"""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "software" / "laptop"))
import test_envelope_cross_language as cross  # noqa: E402  (native build under sanitizers)
from wici.stanowisko import wzorzec  # noqa: E402

VECTORS = json.loads((ROOT / "tests" / "vectors" / "sa1.json").read_text(encoding="utf-8"))
VALID = VECTORS["valid"]["cases"]
REJECTED = VECTORS["rejected"]["cases"]
NONCANONICAL = VECTORS["accepted_noncanonical"]["cases"]
TYPES = range(6)

setUpModule, tearDownModule = cross.setUpModule, cross.tearDownModule


def wire(case):
    return bytes.fromhex(case["wire"])


def hex_or_dash(data):
    return data.hex() or "-"


def native_fields(message):
    """A message as tests/native/sa1_check.cpp prints and reads it, one column per field of sa1::Message."""
    kind, identifier = message[1], message[2]
    revision = category = people = urgency = event = state = 0
    location = text = ""
    if kind in (0, 5):
        revision, category, people, location, text, urgency = message[3:]
    elif kind in (1, 2):
        revision, event, state = message[3:]
    elif kind == 3:
        revision, event, text = message[3:]
    else:
        event, text = message[3:]
    return " ".join((str(kind), identifier, *map(str, (revision, category, people, urgency, event, state)),
                     hex_or_dash(location.encode()), hex_or_dash(text.encode())))


def python_error(data):
    """The reason in reference.py: the ValueError text, or the class of a JSON or UTF-8 error; None when accepted."""
    try:
        wzorzec.decode_message(data)
    except ValueError as error:
        cause = error.__cause__ or error
        return cause.args[0] if type(cause) is ValueError else type(cause).__name__
    return None


class VectorFile(unittest.TestCase):
    def test_every_type_has_valid_and_rejected_bytes(self):
        self.assertEqual({case["message"][1] for case in VALID}, set(TYPES))
        for kind in TYPES:
            self.assertTrue(any(case.get("text", "").startswith(f"[1,{kind},") for case in REJECTED), kind)

    def test_names_are_unique(self):
        names = [case["name"] for case in VALID + REJECTED + NONCANONICAL]
        self.assertEqual(len(names), len(set(names)))

    def test_text_shows_exactly_the_wire_bytes(self):
        for case in VALID + REJECTED + NONCANONICAL:
            with self.subTest(case["name"]):
                if "text" in case:
                    self.assertEqual(case["text"].encode(), wire(case))
                else:
                    with self.assertRaises(UnicodeError):
                        wire(case).decode()

    def test_valid_length(self):
        for case in VALID:
            self.assertEqual(case["length"], len(wire(case)), case["name"])


class PythonCodec(unittest.TestCase):
    def test_valid(self):
        for case in VALID:
            with self.subTest(case["name"]):
                self.assertEqual(wzorzec.decode_message(wire(case)), case["message"])
                self.assertEqual(wzorzec.encode_message(case["message"]), wire(case))

    def test_rejected(self):
        for case in REJECTED:
            with self.subTest(case["name"]):
                self.assertEqual(python_error(wire(case)), case["error_python"])

    def test_accepted_noncanonical(self):
        for case in NONCANONICAL:
            with self.subTest(case["name"]):
                self.assertEqual(wzorzec.decode_message(wire(case)), case["message"])
                self.assertEqual(wzorzec.encode_message(case["message"]).hex(), case["canonical"])
                self.assertNotEqual(case["canonical"], case["wire"])


class StationCodec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = cross.native("sa1_check", "sa1", "jsonlite")

    def answers(self, commands):
        return cross.run(self.binary, stdin="".join(line + "\n" for line in commands)).splitlines()

    def test_valid(self):
        decoded = self.answers(f"decode {case['wire']}" for case in VALID)
        encoded = self.answers(f"encode {native_fields(case['message'])}" for case in VALID)
        for case, read, written in zip(VALID, decoded, encoded, strict=True):
            with self.subTest(case["name"]):
                self.assertEqual(read, f"OK {native_fields(case['message'])}")
                self.assertEqual(written, f"OK {case['wire']}")

    def test_rejected(self):
        answers = self.answers(f"decode {case['wire'] or '-'}" for case in REJECTED)
        for case, answer in zip(REJECTED, answers, strict=True):
            with self.subTest(case["name"]):
                self.assertEqual(answer, f"REJECT {case['error_cpp']}")

    def test_accepted_noncanonical(self):
        decoded = self.answers(f"decode {case['wire']}" for case in NONCANONICAL)
        encoded = self.answers(f"encode {native_fields(case['message'])}" for case in NONCANONICAL)
        for case, read, written in zip(NONCANONICAL, decoded, encoded, strict=True):
            with self.subTest(case["name"]):
                self.assertEqual(read, f"OK {native_fields(case['message'])}")
                self.assertEqual(written, f"OK {case['canonical']}")


if __name__ == "__main__":
    unittest.main()
