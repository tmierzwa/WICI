# SPDX-License-Identifier: MIT
"""Safety checks for the WICI envelope reference codec."""

import unittest

from cryptography.hazmat.primitives.asymmetric import x25519

import envelope


class EnvelopeTests(unittest.TestCase):
    A = bytes(range(32))
    B = bytes(range(32, 64))

    @classmethod
    def setUpClass(cls):
        cls.ap = x25519.X25519PrivateKey.from_private_bytes(cls.A).public_key().public_bytes_raw()
        cls.bp = x25519.X25519PrivateKey.from_private_bytes(cls.B).public_key().public_bytes_raw()
        cls.ab = envelope.derive_key(cls.A, cls.bp, 0x1234, 10, 20, own_id=10)
        cls.ba = envelope.derive_key(cls.B, cls.ap, 0x1234, 20, 10, own_id=20)

    def test_directional_keys_agree_only_in_same_direction(self):
        self.assertEqual(self.ab, envelope.derive_key(self.B, self.ap, 0x1234, 10, 20, own_id=20))
        self.assertNotEqual(self.ab, self.ba)
        self.assertNotEqual(self.ab, envelope.derive_key(self.A, self.bp, 0x1235, 10, 20, own_id=10))

    def test_whole_frame_round_trip_and_header_tamper(self):
        frame, = envelope.seal(self.ab, 10, 20, 7, b"[1,1,2]", 236)
        self.assertEqual(len(frame), 25 + len(b"[1,1,2]"))
        self.assertEqual(envelope.open_part(self.ab, frame), envelope.Part(10, 20, 7, 0, 0, b"[1,1,2]"))
        for index in (0, 1, 4, 8, len(frame) - 1):
            changed = bytearray(frame)
            changed[index] ^= 1
            with self.subTest(index=index), self.assertRaises(envelope.EnvelopeError):
                envelope.open_part(self.ab, changed)
        with self.assertRaises(envelope.EnvelopeError):
            envelope.open_part(self.ba, frame)

    def test_maximum_message_splits_into_distinct_nonce_parts(self):
        frames = envelope.seal(self.ab, 10, 20, 0xFFFFFFFF, bytes(range(256)), 153)
        self.assertEqual(tuple(map(len, frames)), (153, 153))
        parts = tuple(envelope.open_part(self.ab, frame) for frame in frames)
        self.assertEqual([part.number for part in parts], [1, 2])
        self.assertEqual(parts[0].plaintext + parts[1].plaintext, bytes(range(256)))
        self.assertNotEqual(envelope._nonce(frames[0][:9]), envelope._nonce(frames[1][:9]))
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(self.ab, 10, 20, 1, bytes(257), 153)
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(self.ab, 10, 20, 1, bytes(256), 152)

    def test_replay_window_is_committed_only_after_admission(self):
        state = envelope.ReplayWindow()
        proposed = state.accept(20)
        self.assertEqual(state, envelope.ReplayWindow())  # fragment receipt has no replay commit
        state = proposed.accept(19)
        self.assertEqual(state, envelope.ReplayWindow(20, 3))
        with self.assertRaises(envelope.EnvelopeError):
            state.accept(19)
        state = state.accept(84)
        with self.assertRaises(envelope.EnvelopeError):
            state.accept(20)

    def test_out_of_order_assembly_duplicate_and_expiry(self):
        frames = envelope.seal(self.ab, 10, 20, 9, bytes(range(256)), 153)
        first, second = (envelope.open_part(self.ab, frame) for frame in frames)
        pending = envelope.Assembly.start(second, 100)
        same, full = pending.add(second, 101)
        self.assertEqual((same, full), (pending, None))
        done, full = pending.add(first, 102)
        self.assertIsNone(done)
        self.assertEqual(full, bytes(range(256)))
        with self.assertRaises(envelope.EnvelopeError):
            pending.add(first, 221)
        with self.assertRaises(envelope.EnvelopeError):
            pending.add(envelope.Part(10, 20, 9, 0, 2, b"different"), 102)

    def test_reserved_ids_and_low_order_peer_are_rejected(self):
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(self.ab, 0, 20, 0, b"x", 236)
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(self.ab, 10, 10, 0, b"x", 236)
        with self.assertRaises(envelope.EnvelopeError):
            envelope.seal(self.ab, 10, 20, 2**32, b"x", 236)
        with self.assertRaises(ValueError):
            envelope.derive_key(self.A, bytes(32), 1, 10, 20, own_id=10)


if __name__ == "__main__":
    unittest.main()
