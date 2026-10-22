// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
#include "lxmf.h"

#include <string.h>

#include "destination.h"
#include "hash.h"
#include "identity.h"

namespace rnscore {

static_assert(sizeof(double) == 8, "czas LXMF to float64 (IEEE 754)");

namespace {

constexpr size_t PAYLOAD_OFFSET = TRUNCATED_HASH_SIZE + SIGNATURE_SIZE;
// Dane podpisane (signed_part): skrót odbiorcy, skrót nadawcy, payload, skrót wiadomości.
constexpr size_t SIGNED_MAX = 2 * TRUNCATED_HASH_SIZE + (LXMF_MAX_RECEIVED - PAYLOAD_OFFSET) + HASH_SIZE;
constexpr uint8_t TITLE[] = {'S', 'A', '1'};

// hashed_part i za nim skrót wiadomości (LXMessage.pack i unpack_from_bytes); zwraca długość signed_part.
size_t signedPart(const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t sourceHash[TRUNCATED_HASH_SIZE],
                  const uint8_t* payload, size_t payloadLength, uint8_t out[SIGNED_MAX], uint8_t hash[HASH_SIZE]) {
    memcpy(out, destinationHash, TRUNCATED_HASH_SIZE);
    memcpy(out + TRUNCATED_HASH_SIZE, sourceHash, TRUNCATED_HASH_SIZE);
    memcpy(out + 2 * TRUNCATED_HASH_SIZE, payload, payloadLength);
    const size_t hashed = 2 * TRUNCATED_HASH_SIZE + payloadLength;
    fullHash(out, hashed, hash);
    memcpy(out + hashed, hash, HASH_SIZE);
    return hashed + HASH_SIZE;
}

uint64_t bigEndian(const uint8_t* p, size_t n) {
    uint64_t value = 0;
    for (size_t i = 0; i < n; ++i) value = (value << 8) | p[i];
    return value;
}

// Odczyt payloadu w kształcie SA1, kodowania jak w RNS/vendor/umsgpack.py (_unpack_integer, _unpack_float,
// _unpack_binary). Każda funkcja sprawdza długość przed odczytem.
struct Cursor {
    const uint8_t* p;
    size_t left;

    bool take(size_t n, const uint8_t*& out) {
        if (n > left) return false;
        out = p;
        p += n;
        left -= n;
        return true;
    }

    // Czas: liczba całkowita (każde kodowanie) albo float32 lub float64; bool i inne typy odpadają.
    bool number(double& out) {
        const uint8_t* q;
        if (!take(1, q)) return false;
        const uint8_t code = q[0];
        if (code <= 0x7F || code >= 0xE0) {
            out = static_cast<int8_t>(code);
            return true;
        }
        if (code == 0xCA || code == 0xCB) {
            const size_t n = code == 0xCA ? 4 : 8;
            if (!take(n, q)) return false;
            const uint64_t bits = bigEndian(q, n);
            if (n == 4) {
                const uint32_t bits32 = static_cast<uint32_t>(bits);
                float f;
                memcpy(&f, &bits32, sizeof(f));
                out = f;
            } else {
                memcpy(&out, &bits, sizeof(out));
            }
            return true;
        }
        if (code >= 0xCC && code <= 0xD3) {
            const bool isSigned = code >= 0xD0;
            const size_t n = size_t(1) << ((code - (isSigned ? 0xD0 : 0xCC)) & 3);
            if (!take(n, q)) return false;
            uint64_t bits = bigEndian(q, n);
            if (isSigned && n < 8 && (bits >> (8 * n - 1))) bits |= ~uint64_t(0) << (8 * n);
            out = isSigned ? static_cast<double>(static_cast<int64_t>(bits)) : static_cast<double>(bits);
            return true;
        }
        return false;
    }

    // bin 8, 16 albo 32; str i inne typy odpadają.
    bool bin(const uint8_t*& data, size_t& length) {
        const uint8_t* q;
        if (!take(1, q) || q[0] < 0xC4 || q[0] > 0xC6) return false;
        const size_t n = size_t(1) << (q[0] - 0xC4);
        if (!take(n, q)) return false;
        const uint64_t declared = bigEndian(q, n);
        if (declared > left) return false;
        length = static_cast<size_t>(declared);
        return take(length, data);
    }
};

}  // namespace

size_t lxmfPackSa1(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
                   const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t sourceHash[TRUNCATED_HASH_SIZE],
                   double timestamp, const uint8_t* content, size_t contentLength, uint8_t* out, size_t capacity,
                   uint8_t hash[HASH_SIZE]) {
    if (contentLength == 0 || contentLength > SA1_CONTENT_MAX) return 0;
    // self.payload = [self.timestamp, self.title, self.content, self.fields] jak packb: tablica 4 elementów,
    // float64, bin 8 tytułu, bin 8 albo bin 16 treści, pusta mapa.
    uint8_t* payload = out + PAYLOAD_OFFSET;
    const size_t contentHeader = contentLength <= 0xFF ? 2 : 3;
    const size_t payloadLength = 1 + 9 + 2 + sizeof(TITLE) + contentHeader + contentLength + 1;
    if (capacity < PAYLOAD_OFFSET + payloadLength) return 0;
    uint8_t* p = payload;
    *p++ = 0x94;
    uint64_t bits;
    memcpy(&bits, &timestamp, sizeof(bits));
    *p++ = 0xCB;
    for (int i = 7; i >= 0; --i) *p++ = static_cast<uint8_t>(bits >> (8 * i));
    *p++ = 0xC4;
    *p++ = sizeof(TITLE);
    memcpy(p, TITLE, sizeof(TITLE));
    p += sizeof(TITLE);
    if (contentHeader == 2) {
        *p++ = 0xC4;
    } else {
        *p++ = 0xC5;
        *p++ = static_cast<uint8_t>(contentLength >> 8);
    }
    *p++ = static_cast<uint8_t>(contentLength);
    memcpy(p, content, contentLength);
    p += contentLength;
    *p = 0x80;

    uint8_t signedData[SIGNED_MAX];
    const size_t signedLength = signedPart(destinationHash, sourceHash, payload, payloadLength, signedData, hash);
    memcpy(out, sourceHash, TRUNCATED_HASH_SIZE);
    sign(privateKey, publicKey, signedData, signedLength, out + TRUNCATED_HASH_SIZE);
    return PAYLOAD_OFFSET + payloadLength;
}

bool lxmfReceiveSa1(const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                    const uint8_t senderPublicKey[KEY_SIZE], LxmfSa1& out, LxmfReject* reason) {
    LxmfReject ignored;
    LxmfReject& why = reason ? *reason : ignored;
    why = LxmfReject::SHAPE;
    if (length <= PAYLOAD_OFFSET || length > LXMF_MAX_RECEIVED) return false;
    const uint8_t* payload = data + PAYLOAD_OFFSET;
    const size_t payloadLength = length - PAYLOAD_OFFSET;

    // Kształt SA1: [liczba, bin "SA1", bin 1–256 B, {} albo nil]; bajty za wartością Python pomija
    // (unpackb czyta tylko pierwszą wartość), ale wchodzą do skrótu. Tablica 5 elementów to wiadomość
    // ze znaczkiem pracy (LXMessage.unpack_from_bytes zdejmuje go przed sprawdzeniem podpisu).
    Cursor c{payload, payloadLength};
    const uint8_t* q;
    LxmfSa1 m = {};
    const uint8_t* title;
    size_t titleLength;
    if (!c.take(1, q)) return false;
    if (q[0] == 0x95) {
        why = LxmfReject::STAMP;
        return false;
    }
    if (q[0] != 0x94 || !c.number(m.timestamp)) return false;
    if (!c.bin(title, titleLength) || titleLength != sizeof(TITLE) || memcmp(title, TITLE, sizeof(TITLE)) != 0) return false;
    if (!c.bin(m.content, m.contentLength) || m.contentLength == 0 || m.contentLength > SA1_CONTENT_MAX) return false;
    if (!c.take(1, q) || (q[0] != 0x80 && q[0] != 0xC0)) return false;

    // Nadawca: klucz, którego cel "lxmf.delivery" jest skrótem w danych (Identity.recall po ogłoszeniu tego celu).
    uint8_t identity[TRUNCATED_HASH_SIZE], expected[TRUNCATED_HASH_SIZE];
    identityHash(senderPublicKey, identity);
    rnscore::destinationHash("lxmf.delivery", identity, expected);
    why = LxmfReject::SOURCE;
    if (memcmp(expected, data + LXMF_SOURCE_OFFSET, TRUNCATED_HASH_SIZE) != 0) return false;

    uint8_t signedData[SIGNED_MAX];
    const size_t signedLength = signedPart(destinationHash, data, payload, payloadLength, signedData, m.hash);
    why = LxmfReject::SIGNATURE;
    if (!validate(senderPublicKey, data + TRUNCATED_HASH_SIZE, SIGNATURE_SIZE, signedData, signedLength)) return false;
    m.sourceHash = data + LXMF_SOURCE_OFFSET;
    out = m;
    why = LxmfReject::NONE;
    return true;
}

}  // namespace rnscore
