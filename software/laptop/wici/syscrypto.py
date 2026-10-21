# SPDX-License-Identifier: MIT
"""AES-256-CBC + HMAC-SHA256 and PBKDF2-HMAC-SHA256 from the operating system (PLAN.md, decision 2026-10-21).

The standard library has no AES, and the bundled interpreters keep their OpenSSL private, so the
cipher comes from the system: Windows CNG (bcrypt.dll), macOS CommonCrypto (libSystem), Linux
libcrypto. HMAC-SHA256 comes from the standard library. The sealed format is the same everywhere,
so a copy written on one system opens on another.
"""

import ctypes
import hashlib
import hmac
import os
import sys
import threading

VERSION = b"\x01"
_impl = None
_lock = threading.Lock()


class CryptoError(Exception):
    pass


class _Windows:
    def __init__(self):
        from ctypes import wintypes
        b = ctypes.WinDLL("bcrypt")
        h, p = ctypes.c_void_p, ctypes.c_void_p
        b.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(h), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.ULONG]
        b.BCryptSetProperty.argtypes = [h, wintypes.LPCWSTR, p, wintypes.ULONG, wintypes.ULONG]
        b.BCryptGenerateSymmetricKey.argtypes = [h, ctypes.POINTER(h), p, wintypes.ULONG, p, wintypes.ULONG,
                                                 wintypes.ULONG]
        for name in ("BCryptEncrypt", "BCryptDecrypt"):
            getattr(b, name).argtypes = [h, p, wintypes.ULONG, p, p, wintypes.ULONG, p, wintypes.ULONG,
                                         ctypes.POINTER(wintypes.ULONG), wintypes.ULONG]
        b.BCryptDeriveKeyPBKDF2.argtypes = [h, p, wintypes.ULONG, p, wintypes.ULONG, ctypes.c_ulonglong, p,
                                            wintypes.ULONG, wintypes.ULONG]
        b.BCryptDestroyKey.argtypes = [h]
        for name in ("BCryptOpenAlgorithmProvider", "BCryptSetProperty", "BCryptGenerateSymmetricKey",
                     "BCryptEncrypt", "BCryptDecrypt", "BCryptDeriveKeyPBKDF2"):
            getattr(b, name).restype = ctypes.c_long            # NTSTATUS, 0 = sukces
        self.b, self.h, self.ulong = b, h, wintypes.ULONG
        # dostawcy otwierani raz na proces: Microsoft zaleca trzymać uchwyty, bo otwarcie jest kosztowne
        self.aes, self.sha = h(), h()
        self._check(b.BCryptOpenAlgorithmProvider(ctypes.byref(self.aes), "AES", None, 0), "AES")
        mode = ctypes.create_unicode_buffer("ChainingModeCBC")
        self._check(b.BCryptSetProperty(self.aes, "ChainingMode", mode, ctypes.sizeof(mode), 0), "CBC")
        self._check(b.BCryptOpenAlgorithmProvider(ctypes.byref(self.sha), "SHA256", None, 0x8), "HMAC-SHA256")

    def _check(self, status, what):
        if status != 0:
            raise CryptoError(f"{what}: 0x{status & 0xFFFFFFFF:08X}")

    def aes_cbc(self, encrypt, key, iv, data):
        b, kh = self.b, self.h()
        self._check(b.BCryptGenerateSymmetricKey(self.aes, ctypes.byref(kh), None, 0, key, len(key), 0), "klucz")
        try:
            out = ctypes.create_string_buffer(len(data) + 16)
            n = self.ulong()
            fn = b.BCryptEncrypt if encrypt else b.BCryptDecrypt
            ivbuf = ctypes.create_string_buffer(iv, 16)      # CNG nadpisuje IV
            status = fn(kh, data, len(data), None, ivbuf, 16, out, len(out), ctypes.byref(n), 1)
            self._check(status, "szyfrowanie" if encrypt else "odszyfrowanie")
            return out.raw[:n.value]
        finally:
            b.BCryptDestroyKey(kh)

    def pbkdf2(self, password, salt, rounds, size):
        out = ctypes.create_string_buffer(size)
        self._check(self.b.BCryptDeriveKeyPBKDF2(self.sha, password, len(password), salt, len(salt), rounds, out, size,
                                                 0), "PBKDF2")
        return out.raw


class _Mac:
    def __init__(self):
        c = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
        u32, sz, cp, vp = ctypes.c_uint32, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_void_p
        c.CCCrypt.argtypes = [u32, u32, u32, cp, sz, cp, cp, sz, vp, sz, ctypes.POINTER(sz)]
        c.CCCrypt.restype = ctypes.c_int32
        c.CCKeyDerivationPBKDF.argtypes = [u32, cp, sz, cp, sz, u32, u32, vp, sz]
        c.CCKeyDerivationPBKDF.restype = ctypes.c_int
        self.c = c

    def aes_cbc(self, encrypt, key, iv, data):
        out = ctypes.create_string_buffer(len(data) + 16)
        n = ctypes.c_size_t()
        # kCCEncrypt/kCCDecrypt, kCCAlgorithmAES, kCCOptionPKCS7Padding (CBC jest domyślny)
        status = self.c.CCCrypt(0 if encrypt else 1, 0, 1, key, len(key), iv, data, len(data), out, len(out),
                                ctypes.byref(n))
        if status != 0:
            raise CryptoError(f"CommonCrypto {status}")
        return out.raw[:n.value]

    def pbkdf2(self, password, salt, rounds, size):
        out = ctypes.create_string_buffer(size)
        # kCCPBKDF2, kCCPRFHmacAlgSHA256
        if self.c.CCKeyDerivationPBKDF(2, password, len(password), salt, len(salt), 3, rounds, out, size) != 0:
            raise CryptoError("PBKDF2")
        return out.raw


class _Linux:
    def __init__(self):
        for name in ("libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so.10"):
            try:
                lib = ctypes.CDLL(name)
                break
            except OSError:
                continue
        else:
            raise CryptoError("brak systemowej biblioteki libcrypto (OpenSSL): użyj systemu Linux z pamięci USB "
                              "albo innego laptopa")
        p, i = ctypes.c_void_p, ctypes.c_int
        for name, res, args in (("EVP_CIPHER_CTX_new", p, []), ("EVP_CIPHER_CTX_free", None, [p]),
                                ("EVP_aes_256_cbc", p, []), ("EVP_sha256", p, []),
                                ("EVP_CipherInit_ex", i, [p, p, p, p, p, i]),
                                ("EVP_CipherUpdate", i, [p, p, ctypes.POINTER(i), p, i]),
                                ("EVP_CipherFinal_ex", i, [p, p, ctypes.POINTER(i)]),
                                ("PKCS5_PBKDF2_HMAC", i, [p, i, p, i, i, p, i, p])):
            fn = getattr(lib, name)
            fn.restype, fn.argtypes = res, args
        self.lib = lib

    def aes_cbc(self, encrypt, key, iv, data):
        lib = self.lib
        ctx = lib.EVP_CIPHER_CTX_new()
        if not ctx:
            raise CryptoError("EVP_CIPHER_CTX_new")
        try:
            out = ctypes.create_string_buffer(len(data) + 16)
            n, m = ctypes.c_int(), ctypes.c_int()
            ok = (lib.EVP_CipherInit_ex(ctx, lib.EVP_aes_256_cbc(), None, key, iv, 1 if encrypt else 0) == 1
                  and lib.EVP_CipherUpdate(ctx, out, ctypes.byref(n), data, len(data)) == 1
                  and lib.EVP_CipherFinal_ex(ctx, ctypes.byref(out, n.value), ctypes.byref(m)) == 1)
            if not ok:
                raise CryptoError("szyfrowanie" if encrypt else "odszyfrowanie")
            return out.raw[:n.value + m.value]
        finally:
            lib.EVP_CIPHER_CTX_free(ctx)

    def pbkdf2(self, password, salt, rounds, size):
        out = ctypes.create_string_buffer(size)
        if self.lib.PKCS5_PBKDF2_HMAC(password, len(password), salt, len(salt), rounds, self.lib.EVP_sha256(),
                                      size, out) != 1:
            raise CryptoError("PBKDF2")
        return out.raw


def _system():
    global _impl
    with _lock:
        if _impl is None:
            _impl = _Windows() if sys.platform == "win32" else _Mac() if sys.platform == "darwin" else _Linux()
    return _impl


def aes_cbc(encrypt, key, iv, data):
    if len(key) != 32 or len(iv) != 16:
        raise CryptoError("klucz 32 B, IV 16 B")
    return _system().aes_cbc(encrypt, bytes(key), bytes(iv), bytes(data))


def pbkdf2(password, salt, rounds, size=32):
    return _system().pbkdf2(bytes(password), bytes(salt), rounds, size)


def _keys(key):
    # jeden klucz 32 B (np. z PBKDF2) rozwinięty na klucz szyfru i klucz MAC z etykietami
    if len(key) != 32:
        raise CryptoError("klucz 32 B")
    return hmac.digest(key, b"wici enc", "sha256"), hmac.digest(key, b"wici mac", "sha256")


def _mac(key, body, aad):
    return hmac.digest(key, len(aad).to_bytes(8, "big") + aad + body, "sha256")


def seal(key, data, aad=b""):
    """VERSION | IV | AES-256-CBC(PKCS7) | HMAC-SHA256 over aad (length-prefixed) and everything before it."""
    enc, mac = _keys(key)
    iv = os.urandom(16)
    body = VERSION + iv + aes_cbc(True, enc, iv, data)
    return body + _mac(mac, body, aad)


def open_(key, sealed, aad=b""):
    enc, mac = _keys(key)
    if len(sealed) < 1 + 16 + 16 + 32 or sealed[:1] != VERSION:
        raise CryptoError("nieznany format")
    body = sealed[:-32]
    if not hmac.compare_digest(sealed[-32:], _mac(mac, body, aad)):
        raise CryptoError("zły klucz albo uszkodzone dane")       # najpierw MAC, potem odszyfrowanie
    return aes_cbc(False, enc, body[1:17], body[17:])


def _expect(ok, what):
    if not ok:      # nie assert: python -O usunąłby sprawdzenie
        raise CryptoError(f"samosprawdzenie: {what}")


def selfcheck():
    """Known answers: AES-256-CBC as OpenSSL `enc`, PBKDF2-HMAC-SHA256 from RFC 7914 section 11; then seal/open."""
    ct = aes_cbc(True, bytes(range(32)), bytes(16), b"Szkola nr 5, wejscie od podworza")
    _expect(ct.hex() == ("5c7f4bb144d7fd5015e17c2695a236214fc5d2e6be5903aaab35a8650779c1a8"
                         "743bb88b43ad8b5e3acba0e62687c9ea"), "AES-256-CBC")
    _expect(aes_cbc(False, bytes(range(32)), bytes(16), ct) == b"Szkola nr 5, wejscie od podworza", "AES odszyfrowanie")
    _expect(pbkdf2(b"passwd", b"salt", 1, 64).hex() == (
        "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc"
        "49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783"), "PBKDF2")
    key = hashlib.sha256(b"wici").digest()
    text = "Szkoła, wejście od podwórza".encode()
    sealed = seal(key, text, b"kopia")
    _expect(open_(key, sealed, b"kopia") == text, "kopia")
    for bad, aad in ((sealed[:-1] + bytes([sealed[-1] ^ 1]), b"kopia"), (sealed, b"inna")):
        try:
            open_(key, bad, aad)
        except CryptoError:
            continue
        raise CryptoError("samosprawdzenie: przyjęta zmieniona kopia")
    return type(_system()).__name__.strip("_").lower()
