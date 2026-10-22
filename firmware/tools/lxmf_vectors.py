# SPDX-License-Identifier: MIT
"""Test vectors for MessagePack and LXMF in the station Reticulum core, made by reference Python code.

Stage R3 of the core (firmware/reticulum-core.md): MessagePack as LXMF uses it (u-msgpack-python 2.7.1
vendored in Reticulum e40191b, RNS/vendor/umsgpack.py). Every expected value is what the reference code
computes or returns: for each input, whether unpackb accepts it and how many bytes the first value takes
(unpack from a stream; unpackb ignores the rest), and what packb makes of the values the core writes. Inputs the core rejects on
purpose (firmware/lib/reticulum_core/src/msgpack.h) carry the reason in "core_deviation"; the reference
must accept them, otherwise they would not be deviations.

Run with a Python that has Reticulum at the pinned commit (e40191b, version 1.5.5):
  .venv-rns/bin/python firmware/tools/lxmf_vectors.py > tests/vectors/lxmf.json
tests/test_rnscore_lxmf.py compares the committed file with a fresh run when WICI_RNS_PYTHON is set.
"""

import io
import json
import struct
import sys

import RNS
import RNS.vendor.umsgpack as umsgpack

RNS_VERSION = "1.5.5"
RNS_COMMIT = "e40191b3d193b46b7f2d8a44424a594cd758839b"
# Głębokość zagnieżdżenia tablic i map, którą rdzeń przyjmuje w LXMF (lxmf.h: LXMF_MAX_DEPTH).
MAX_DEPTH = 8


def packb(value) -> bytes:
    return umsgpack.packb(value)


def depth(data: bytes) -> int:
    """Nesting depth of the first value (containers only), by walking the encoding like _unpack."""
    fp = io.BytesIO(data)

    def walk() -> int:
        code = fp.read(1)[0]
        count = 0
        if 0x80 <= code <= 0x8F or 0x90 <= code <= 0x9F:
            count = (code & 0x0F) * (2 if code < 0x90 else 1)
        elif code in (0xDC, 0xDE):
            count = struct.unpack(">H", fp.read(2))[0] * (2 if code == 0xDE else 1)
        elif code in (0xDD, 0xDF):
            count = struct.unpack(">I", fp.read(4))[0] * (2 if code == 0xDF else 1)
        else:
            fp.seek(fp.tell() - 1)
            umsgpack.unpack(fp)
            return 0
        return 1 + max((walk() for _ in range(count)), default=0)

    return walk()


def key_types(value):
    """Types of all map keys in an unpacked value (tuples come from array keys)."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield type(k)
            yield from key_types(k)
            yield from key_types(v)
    elif isinstance(value, (list, tuple)):
        for e in value:
            yield from key_types(e)


def msgpack_case(name: str, data: bytes) -> dict:
    case = {"name": name, "data": data.hex()}
    fp = io.BytesIO(data)
    try:
        value = umsgpack.unpack(fp)
    except Exception as e:   # błąd rozbioru, RecursionError, OverflowError: unpackb odrzuca
        case.update(accepted=False, error=type(e).__name__)
        return case
    case.update(accepted=True, consumed=fp.tell())
    deviation = None
    if depth(data) > MAX_DEPTH:
        deviation = "depth"
    elif has_ext(data):
        deviation = "ext"
    elif any(t not in (type(None), bool, int, str, bytes) for t in key_types(value)):
        deviation = "map_key"
    case["core_deviation"] = deviation
    return case


def has_ext(data: bytes) -> bool:
    """Whether the first value contains an ext (also a timestamp), by walking the encoding like _unpack."""
    fp = io.BytesIO(data)
    pending = 1
    while pending:
        code = fp.read(1)[0]
        pending -= 1
        if 0xC7 <= code <= 0xC9 or 0xD4 <= code <= 0xD8:
            return True
        if 0x80 <= code <= 0x9F or code in (0xDC, 0xDD, 0xDE, 0xDF):
            if code <= 0x9F:
                count = code & 0x0F
            else:
                count = int.from_bytes(fp.read(2 if code in (0xDC, 0xDE) else 4), "big")
            pending += count * (2 if code in (0xDE, 0xDF) or code <= 0x8F else 1)
        else:
            fp.seek(fp.tell() - 1)
            umsgpack.unpack(fp)
    return False


def writer_vectors():
    """What packb makes of each value the core writer handles (LXMessage.pack: array, map, float64, bin).
    Lengths above 65 535 the core refuses (no packet holds them); packb uses the 32-bit forms."""
    out = []
    for count in (0, 4, 15, 16, 65535, 65536):
        array = packb([0] * count)
        out.append({"op": "a", "value": count, "packed": array[:len(array) - count].hex()})
        pairs = packb({i: 0 for i in range(count)})
        out.append({"op": "m", "value": count,
                    "packed": pairs[:len(pairs) - sum(len(packb(i)) + 1 for i in range(count))].hex()})
    for value in (0.0, -0.0, 1.5, 1790000000.123456, -1e300, float("inf"), 2.0**53):
        out.append({"op": "f", "value": struct.pack(">d", value).hex(), "packed": packb(value).hex()})
    for length in (0, 1, 255, 256, 65535, 65536):
        data = bytes(range(256)) * (length // 256) + bytes(range(length % 256))
        out.append({"op": "b", "value": length, "packed": packb(data)[:len(packb(data)) - length].hex()})
    return out


def nested(levels: int, inner: bytes = b"\xc0", map_level: int = 0) -> bytes:
    """levels nested containers around inner; map_level: which level is a one-pair map with key 0."""
    out = inner
    for level in range(levels, 0, -1):
        out = (b"\x81\x00" if level == map_level else b"\x91") + out
    return out


def timestamp96(seconds: int, nanoseconds: int = 0) -> bytes:
    return b"\xc7\x0c\xff" + struct.pack(">Iq", nanoseconds, seconds)


def msgpack_vectors():
    ints = [0, 1, 127, 128, 255, 256, 65535, 65536, 2**32 - 1, 2**32, 2**64 - 1,
            -1, -32, -33, -128, -129, -32768, -32769, -2**31, -2**31 - 1, -2**63]
    cases = {f"int_{v}": packb(v) for v in ints}
    cases.update({
        "nil": packb(None), "true": packb(True), "false": packb(False),
        # Liczby w kodowaniu dłuższym niż trzeba albo ze znakiem: unpackb daje zwykły int.
        "uint8_small": b"\xcc\x05", "uint16_small": b"\xcd\x00\x05", "uint64_small": b"\xcf" + (5).to_bytes(8, "big"),
        "int8_positive": b"\xd0\x05", "int8_minus_one": b"\xd0\xff", "int64_positive": b"\xd3" + (5).to_bytes(8, "big"),
        "int16_minus_one": b"\xd1\xff\xff", "int32_min": b"\xd2\x80\x00\x00\x00",
        "float64": packb(1.5), "float64_negative_zero": packb(-0.0), "float64_inf": packb(float("inf")),
        "float64_time": packb(1790000000.123456),
        "float32": b"\xca" + struct.pack(">f", 1.5), "float32_inexact": b"\xca" + struct.pack(">f", 0.1),
        "str_empty": packb(""), "str_wici": packb("WICI"), "str_31": packb("a" * 31), "str_32": packb("a" * 32),
        "str_255": packb("b" * 255), "str_256": packb("c" * 256), "str_polish": packb("zażółć gęślą jaźń"),
        "str_ukrainian": packb("Пожежа"), "str_4_byte": packb("\U0001F525"), "str_max_code_point": packb("\U0010FFFF"),
        "str8_short": b"\xd9\x04WICI", "str16_short": b"\xda\x00\x04WICI", "str32_short": b"\xdb\x00\x00\x00\x04WICI",
        "str_overlong_nul": b"\xa2\xc0\x80", "str_overlong_3_byte": b"\xa3\xe0\x80\x80",
        "str_overlong_4_byte": b"\xa4\xf0\x80\x80\x80", "str_surrogate": b"\xa3\xed\xa0\x80",
        "str_above_max": b"\xa4\xf4\x90\x80\x80", "str_f5": b"\xa4\xf5\x80\x80\x80", "str_lone_continuation": b"\xa1\x80",
        "str_truncated_sequence": b"\xa2\xe2\x82", "str_bad_continuation": b"\xa3\xe2\x28\xa1", "str_ff": b"\xa1\xff",
        "bin_empty": packb(b""), "bin_1": packb(b"\x00"), "bin_255": packb(bytes(255)), "bin_256": packb(bytes(256)),
        "bin16_short": b"\xc5\x00\x02ab", "bin32_short": b"\xc6\x00\x00\x00\x02ab", "bin_invalid_utf8": packb(b"\xff\xfe"),
        **{f"fixext_{n}": packb(umsgpack.Ext(5, bytes(range(n)))) for n in (1, 2, 4, 8, 16)},
        "ext8_empty": packb(umsgpack.Ext(-5, b"")), "ext8_3": packb(umsgpack.Ext(127, b"abc")),
        "ext16_300": packb(umsgpack.Ext(-128, bytes(300))), "ext8_long_form_of_4": b"\xc7\x04\x05abcd",
        "timestamp32": b"\xd6\xff" + struct.pack(">I", 1790000000),
        "timestamp64": b"\xd7\xff" + struct.pack(">Q", (123456000 << 34) | 1790000000),
        "timestamp64_nanoseconds_above_second": b"\xd7\xff" + struct.pack(">Q", ((2**30 - 1) << 34) | (2**34 - 1)),
        "timestamp96": timestamp96(-1, 999999999), "timestamp96_min": timestamp96(-62135596800),
        "timestamp96_below_min": timestamp96(-62135596801, 999999), "timestamp96_min_by_nanoseconds": timestamp96(-62135596804, 4294967295),
        "timestamp96_max": timestamp96(253402300799, 999999999), "timestamp96_above_max": timestamp96(253402300800),
        "timestamp96_int64_min": timestamp96(-2**63), "timestamp96_int64_max": timestamp96(2**63 - 1),
        "timestamp_3_bytes": b"\xc7\x03\xffabc", "timestamp_16_bytes": b"\xd8\xff" + bytes(16),
        "array_empty": packb([]), "array_15": packb(list(range(15))), "array_16": packb(list(range(16))),
        "array16_short": b"\xdc\x00\x01\x01", "array32_short": b"\xdd\x00\x00\x00\x01\x01",
        "map_empty": packb({}), "map_int": packb({1: 2}), "map_15": packb({i: i for i in range(15)}),
        "map_16": packb({i: i for i in range(16)}), "map16_short": b"\xde\x00\x01\x01\x02",
        "map_str_keys": packb({"a": 1, "b": [b"x", None]}), "map_nested": packb({1: {2: {3: [4]}}}),
        "map_nil_bool_keys": packb({None: 1, True: 2, b"k": 3, "k": 4, -1: 5}),
        # Klucz powtórzony według równości Pythona (DuplicateKeyException).
        "map_duplicate_int": b"\x82\x01\x01\x01\x02", "map_duplicate_true_one": b"\x82\xc3\x01\x01\x02",
        "map_duplicate_false_zero": b"\x82\x00\x01\xc2\x02", "map_duplicate_nil": b"\x82\xc0\x01\xc0\x02",
        "map_duplicate_str": b"\x82\xa1a\x01\xa1a\x02", "map_duplicate_bin": b"\x82\xc4\x01a\x01\xc4\x01a\x02",
        "map_duplicate_non_canonical": b"\x82\xff\x01\xd0\xff\x02", "map_duplicate_uint64": b"\x82\x05\x01\xcf" + (5).to_bytes(8, "big") + b"\x02",
        "map_duplicate_after_nested": b"\x83\x01\x81\x02\x03\x02\x92\x81\x01\x02\x80\x01\x04",
        "map_duplicate_in_value": b"\x81\x01\x82\x02\x00\x02\x00",
        "map_str_and_bin_same_bytes": b"\x82\xa1a\x01\xc4\x01a\x02", "map_one_and_minus_one": b"\x82\x01\x01\xff\x02",
        "map_int64_min_and_uint64_max": b"\x82\xd3\x80" + bytes(7) + b"\x01\xcf" + b"\xff" * 8 + b"\x02",
        # Klucze, które Python przyjmuje, a rdzeń nie (odstępstwo).
        "map_float_key": packb({1.5: 1}), "map_float_key_equal_to_int": b"\x82\x01\x01\xcb" + struct.pack(">d", 1.0) + b"\x02",
        "map_array_key": b"\x81\x91\x01\x02", "map_ext_key": b"\x81\xd4\x05\x00\x01", "map_timestamp_key": b"\x81\xd6\xff\x00\x00\x00\x01\x01",
        "map_map_key": b"\x81\x80\x01", "map_array_key_with_map": b"\x81\x91\x80\x01",
        # Kody i długości spoza danych.
        "reserved_c1": b"\xc1", "reserved_in_array": b"\x92\x01\xc1", "empty": b"",
        "array32_huge": b"\xdd\xff\xff\xff\xff", "map32_huge": b"\xdf\xff\xff\xff\xff", "str32_huge": b"\xdb\xff\xff\xff\xff",
        "bin32_huge": b"\xc6\xff\xff\xff\xff", "ext32_huge": b"\xc9\xff\xff\xff\xff\x01", "array_short_by_one": b"\x93\x01\x02",
        "map_missing_value": b"\x81\x01", "float64_truncated": b"\xcb\x00\x00", "uint64_truncated": b"\xcf\x00",
        "ext_missing_type": b"\xc7\x01", "fixext_missing_data": b"\xd5\x01\x00",
        # Pierwsza wartość i bajty za nią (unpackb je pomija).
        "trailing_bytes": b"\x01\x02\x03", "trailing_garbage_after_array": packb([1, "a"]) + b"\xc1\xff",
        # Zagnieżdżenie: do MAX_DEPTH rdzeń przyjmuje, głębiej nie (Python do granicy rekurencji).
        "depth_8": nested(8), "depth_8_maps": nested(8, map_level=8), "depth_9": nested(9), "depth_9_map": nested(9, map_level=9),
        "depth_200": nested(200), "depth_9_empty": nested(8, b"\x90"), "depth_2000": nested(2000),
    })
    out = [msgpack_case(name, data) for name, data in cases.items()]
    # Każdy przedrostek złożonej wartości: odrzucony bez błędu pamięci.
    whole = packb([1790000000.5, b"SA1", "zażółć".encode(), {1: [b"x" * 40, None, True], "k": umsgpack.Ext(3, b"ab")}])
    out += [msgpack_case(f"prefix_{n}", whole[:n]) for n in range(len(whole) + 1)]
    return out


def main():
    if RNS.__version__ != RNS_VERSION:
        sys.exit(f"Reticulum {RNS.__version__}, expected {RNS_VERSION} ({RNS_COMMIT})")
    if umsgpack.__version__ != "2.7.1":
        sys.exit(f"umsgpack {umsgpack.__version__}, expected 2.7.1")
    vectors = {
        "source": {"reticulum": RNS_VERSION, "commit": RNS_COMMIT, "umsgpack": umsgpack.__version__,
                   "tool": "firmware/tools/lxmf_vectors.py"},
        "msgpack_max_depth": MAX_DEPTH,
        "msgpack": msgpack_vectors(),
        "msgpack_writer": writer_vectors(),
    }
    json.dump(vectors, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
