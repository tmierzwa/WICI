// SPDX-License-Identifier: MIT
// Cel libFuzzera dla rdzenia Reticulum stacji (firmware/tools/core_fuzz.py, kryterium odbioru 4 w
// firmware/reticulum-core.md). Każde wejście to nowa stacja z tablicą znanych celów w RAM i ciąg rekordów:
// rodzaj (1 B), przesunięcie zegara (1 B: n x 100 ms, 255 = doba), długość (2 B, little-endian, najwyżej
// MAX_RECORD) i dane. Rodzaje: pakiet bez IFAC do Transport::inbound, datagram z kodem IFAC (ifacCheck,
// potem inbound), dane wiadomości LXMF (lxmfReceiveSa1 kluczem nadawcy z wektorów), poll, zapis danych
// w obszar tablicy i restart stacji (wroga treść FRAM), pakiet stacji (send, requestPath, announce).
// Rdzeń nie ma stanu globalnego, więc wynik zależy tylko od wejścia (powtarzalne awarie).
// Z -DWICI_FUZZ_DRIVER własny main: odtwarza pliki z argumentów, a z --mutate SEKUNDY dodatkowo prosto je
// mutuje (bez libFuzzera, np. Apple clang); awaria tak samo przerywa program sanitizerem.
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <new>

#include "destination.h"
#include "identity.h"
#include "ifac.h"
#include "lxmf.h"
#include "transport.h"

namespace {

constexpr size_t MAX_RECORD = 1024;   // ponad MTU z IFAC: także pakiety za długie

// Klucze z tests/vectors (reticulum.json: identity[0].private_key i ifac.ifac_key, lxmf.json: sender_public_key
// i destination_hash), żeby korpus z wektorów przechodził sprawdzenia; core_fuzz.py sprawdza, że są te same.
const uint8_t STATION_KEY[rnscore::KEY_SIZE] = {
    0x3d, 0x2c, 0xbb, 0x9d, 0x7d, 0xec, 0x81, 0x87, 0xb4, 0xe4, 0x39, 0xe8, 0xf7, 0xb6, 0xf0, 0x9a,
    0xc8, 0xb3, 0x40, 0xaa, 0x1c, 0x96, 0x23, 0xd7, 0xe6, 0xdc, 0xc7, 0x22, 0x3c, 0xe5, 0xf4, 0x96,
    0xb4, 0x99, 0x7c, 0x11, 0xdb, 0x3f, 0xf4, 0x93, 0x3c, 0xfd, 0xd0, 0xdd, 0x33, 0xae, 0xf3, 0xe7,
    0xb2, 0x26, 0x77, 0x91, 0xf0, 0x97, 0xbd, 0xca, 0x8d, 0xd8, 0x3c, 0xcd, 0x18, 0xba, 0x24, 0x8f,
};
const uint8_t IFAC_KEY[rnscore::KEY_SIZE] = {
    0xbf, 0xce, 0xb2, 0xae, 0xdd, 0xff, 0x69, 0x99, 0xa5, 0x4f, 0x52, 0x42, 0x2a, 0x9c, 0xf3, 0x2a,
    0xa2, 0x8f, 0xc7, 0xef, 0xe1, 0x07, 0xec, 0xf8, 0x4e, 0x15, 0xed, 0x4d, 0xba, 0xa2, 0x36, 0x13,
    0x13, 0x27, 0x5d, 0x46, 0x39, 0xee, 0xce, 0xe3, 0xb4, 0xa3, 0x63, 0x7e, 0x72, 0xe7, 0x6d, 0x46,
    0xbf, 0x0e, 0xa2, 0xe6, 0xfb, 0xc0, 0x58, 0xe8, 0x85, 0x38, 0x3b, 0xb0, 0xc4, 0x93, 0x07, 0x05,
};
const uint8_t SENDER_KEY[rnscore::KEY_SIZE] = {
    0x97, 0x1a, 0xa9, 0x0e, 0xd0, 0x5f, 0xab, 0x63, 0x29, 0x49, 0x7c, 0x5f, 0xd6, 0xd3, 0x52, 0xd0,
    0x47, 0x15, 0x0a, 0x42, 0xe8, 0x50, 0xa8, 0xe6, 0x9e, 0x1f, 0x5e, 0xb5, 0x63, 0x47, 0x90, 0x01,
    0xfc, 0xd3, 0x1d, 0xa9, 0x45, 0xa5, 0x52, 0xa1, 0xd9, 0xce, 0x77, 0x4a, 0xf6, 0x92, 0x39, 0x61,
    0xf4, 0x62, 0xf7, 0x89, 0x70, 0xa9, 0x84, 0x73, 0xbd, 0x23, 0x8e, 0x0f, 0xa4, 0xfa, 0xf1, 0xa4,
};
const uint8_t LXMF_DESTINATION[rnscore::TRUNCATED_HASH_SIZE] = {
    0xa1, 0x2e, 0x4e, 0x10, 0x09, 0xc6, 0xd1, 0x59, 0xa9, 0xce, 0xfc, 0xfd, 0xb9, 0x5e, 0x34, 0xff,
};

struct MemoryTable : rnscore::TableStorage {
    uint8_t bytes[rnscore::TABLE_AREA];
    bool read(uint32_t offset, uint8_t* data, size_t count) override {
        if (offset > sizeof(bytes) || count > sizeof(bytes) - offset) return false;
        memcpy(data, bytes + offset, count);
        return true;
    }
    bool write(uint32_t offset, const uint8_t* data, size_t count) override {
        if (offset > sizeof(bytes) || count > sizeof(bytes) - offset) return false;
        memcpy(bytes + offset, data, count);
        return true;
    }
};

struct Station {
    MemoryTable table;
    rnscore::Transport transport;
    rnscore::TransportHooks hooks;
    rnscore::Ifac ifac;
    uint8_t publicKey[rnscore::KEY_SIZE];
    uint8_t identity[rnscore::TRUNCATED_HASH_SIZE];
    uint8_t address[rnscore::TRUNCATED_HASH_SIZE];
    uint8_t nameHash[rnscore::NAME_HASH_SIZE];
    uint32_t random = 0;
    uint64_t nowMs = 1000;
};

bool onTransmit(const uint8_t*, size_t, void*) { return true; }
bool onPacket(const uint8_t*, size_t, void*) { return true; }
// Losowość z licznika: wynik zależy tylko od wejścia.
bool onRandom(uint8_t* out, size_t length, void* context) {
    Station& s = *static_cast<Station*>(context);
    for (size_t i = 0; i < length; ++i) out[i] = static_cast<uint8_t>(++s.random * 167u);
    return true;
}

// Start stacji jak po włączeniu zasilania: nowy obiekt w tym samym miejscu (clear() zostawia liczniki
// i kursor wygasania tras, więc wynik zależałby od poprzednich wejść).
void start(Station& s) {
    s.transport.~Transport();
    new (&s.transport) rnscore::Transport();
    s.transport.begin(STATION_KEY, s.publicKey, s.identity, s.address, s.nameHash, s.hooks, s.table, s.nowMs);
}

Station& station() {
    static Station* s = nullptr;   // jeden bufor na cały przebieg (tablica 146 KB), stan od nowa w każdym wejściu
    if (!s) {
        s = new Station();
        rnscore::publicKey(STATION_KEY, s->publicKey);
        rnscore::identityHash(s->publicKey, s->identity);
        rnscore::nameHash("lxmf.delivery", s->nameHash);
        rnscore::destinationHashFrom(s->nameHash, s->identity, s->address);
        memcpy(s->ifac.key, IFAC_KEY, sizeof(IFAC_KEY));
        rnscore::publicKey(s->ifac.key, s->ifac.publicKey);
        s->ifac.size = 16;
        s->hooks.transmit = onTransmit;
        s->hooks.packet = onPacket;
        s->hooks.random = onRandom;
        s->hooks.context = s;
    }
    return *s;
}


void record(Station& s, uint8_t kind, const uint8_t* data, size_t length) {
    switch (kind % 6) {
        case 0:
            s.transport.inbound(data, length, s.nowMs);
            break;
        case 1: {
            uint8_t raw[MAX_RECORD];
            const size_t n = rnscore::ifacCheck(s.ifac, data, length, raw, sizeof(raw));
            if (n) s.transport.inbound(raw, n, s.nowMs);
            break;
        }
        case 2: {
            rnscore::LxmfSa1 message;
            rnscore::LxmfReject reason;
            rnscore::lxmfReceiveSa1(LXMF_DESTINATION, data, length, SENDER_KEY, message, &reason);
            break;
        }
        case 3:
            s.transport.poll(s.nowMs, length == 0 || data[0] & 1);
            break;
        case 4: {   // 3 B przesunięcia w obszarze tablicy, reszta to treść; potem restart stacji
            if (length < 3) break;
            const uint32_t at = ((uint32_t(data[0]) << 16) | (uint32_t(data[1]) << 8) | data[2]) % rnscore::TABLE_AREA;
            const size_t n = length - 3 < rnscore::TABLE_AREA - at ? length - 3 : rnscore::TABLE_AREA - at;
            memcpy(s.table.bytes + at, data + 3, n);
            start(s);
            break;
        }
        default: {   // 1 B wyboru, 16 B celu, reszta to dane
            if (length < 1 + rnscore::TRUNCATED_HASH_SIZE) break;
            const uint8_t* destination = data + 1;
            const uint8_t* rest = destination + rnscore::TRUNCATED_HASH_SIZE;
            const size_t restLength = length - 1 - rnscore::TRUNCATED_HASH_SIZE;
            if (data[0] % 3 == 0) {
                uint8_t ephemeral[rnscore::KEY_SIZE / 2], iv[16];
                onRandom(ephemeral, sizeof(ephemeral), &s);
                onRandom(iv, sizeof(iv), &s);
                s.transport.send(destination, rest, restLength, ephemeral, iv, s.random, 30000, s.nowMs);
            } else if (data[0] % 3 == 1) {
                s.transport.requestPath(destination, destination, s.nowMs);
            } else {
                s.transport.announce(destination, rest, restLength, s.nowMs);
            }
            break;
        }
    }
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    Station& s = station();
    memset(s.table.bytes, 0xFF, sizeof(s.table.bytes));   // nowa pamięć FRAM
    s.random = 0;
    s.nowMs = 1000;
    start(s);
    size_t at = 0;
    while (size - at >= 4) {
        const uint8_t kind = data[at];
        const uint8_t step = data[at + 1];
        size_t length = data[at + 2] | (size_t(data[at + 3]) << 8);
        at += 4;
        if (length > MAX_RECORD) length = MAX_RECORD;
        if (length > size - at) length = size - at;
        s.nowMs += step == 255 ? 86400000ull : step * 100ull;
        // Kopia o dokładnej długości: ASan wykrywa czytanie poza danymi rekordu.
        uint8_t* copy = new uint8_t[length ? length : 1];
        memcpy(copy, data + at, length);
        record(s, kind, copy, length);
        delete[] copy;
        at += length;
    }
    return 0;
}

#ifdef WICI_FUZZ_DRIVER
#include <stdlib.h>
#include <time.h>

#include <vector>

namespace {

bool load(const char* path, std::vector<uint8_t>& out) {
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    out.clear();
    uint8_t buffer[4096];
    size_t n;
    while ((n = fread(buffer, 1, sizeof(buffer), f)) > 0) out.insert(out.end(), buffer, buffer + n);
    fclose(f);
    return true;
}

}  // namespace

// rnscore_fuzz [--mutate SEKUNDY] PLIK...: każdy plik raz, potem mutacje (odwrócony bit, losowy bajt, wycięcie
// albo sklejenie z innym plikiem) do końca czasu. Wynik: liczba wykonań.
int main(int argc, char** argv) {
    long seconds = 0;
    std::vector<std::vector<uint8_t>> corpus;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--mutate") && i + 1 < argc) {
            seconds = strtol(argv[++i], nullptr, 10);
            continue;
        }
        std::vector<uint8_t> input;
        if (!load(argv[i], input)) {
            fprintf(stderr, "cannot read %s\n", argv[i]);
            return 2;
        }
        LLVMFuzzerTestOneInput(input.data(), input.size());
        if (!seconds) {   // samo odtworzenie: co rdzeń zrobił z wejściem (core_fuzz.py --replay sprawdza korpus)
            const rnscore::TransportCounters& c = station().transport.counters();
            printf("{\"file\":\"%s\",\"announces\":%u,\"invalid\":%u,\"ignored\":%u,\"received\":%u,\"sent\":%u,"
                   "\"forwarded\":%u,\"no_path\":%u,\"path_requests\":%u,\"known\":%u}\n",
                   argv[i], static_cast<unsigned>(c.announces), static_cast<unsigned>(c.invalid), static_cast<unsigned>(c.ignored),
                   static_cast<unsigned>(c.received), static_cast<unsigned>(c.sent), static_cast<unsigned>(c.forwarded),
                   static_cast<unsigned>(c.noPath), static_cast<unsigned>(c.pathRequests),
                   static_cast<unsigned>(station().transport.known()));
        }
        corpus.push_back(input);
    }
    unsigned long runs = corpus.size();
    const time_t end = time(nullptr) + seconds;
    uint32_t r = 2463534242u;
    const auto next = [&r] {
        r ^= r << 13;
        r ^= r >> 17;
        r ^= r << 5;
        return r;
    };
    while (seconds > 0 && !corpus.empty() && time(nullptr) < end) {
        std::vector<uint8_t> input = corpus[next() % corpus.size()];
        for (int k = 1 + next() % 4; k > 0; --k) {
            switch (next() % 4) {
                case 0:
                    if (!input.empty()) input[next() % input.size()] ^= static_cast<uint8_t>(1u << (next() % 8));
                    break;
                case 1:
                    if (!input.empty()) input[next() % input.size()] = static_cast<uint8_t>(next());
                    break;
                case 2:
                    if (!input.empty()) input.resize(next() % input.size());
                    break;
                default: {
                    const std::vector<uint8_t>& other = corpus[next() % corpus.size()];
                    input.insert(input.end(), other.begin(), other.end());
                    break;
                }
            }
        }
        LLVMFuzzerTestOneInput(input.data(), input.size());
        ++runs;
    }
    printf("{\"runs\":%lu}\n", runs);
    return 0;
}
#endif
