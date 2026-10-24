// SPDX-License-Identifier: MIT
// Program prób rdzenia Reticulum stacji na komputerze (tests/test_rnscore.py): czyta ze standardowego
// wejścia wiersze "polecenie dane_hex" i dla każdego wypisuje jeden wiersz z wynikiem szesnastkowo
// albo "error". Polecenia z kilkoma argumentami biorą je sklejone w jednym ciągu, w kolejności z opisu
// przy poleceniu (klucze i podpisy mają stałą długość, reszta to wiadomość). Wartości oczekiwane (wektory z Reticulum w Pythonie) porównuje test w Pythonie.
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "announce.h"
#include "core_selftest.h"
#include "destination.h"
#include "hash.h"
#include "hkdf.h"
#include "identity.h"
#include "ifac.h"
#include "packet.h"
#include "proof.h"
#include "token.h"
#include "transport.h"

namespace {

bool fromHex(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2) return false;
    out.clear();
    for (size_t i = 0; i < hex.size(); i += 2) {
        const std::string pair = hex.substr(i, 2);
        if (pair.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos) return false;
        out.push_back(static_cast<uint8_t>(std::stoul(pair, nullptr, 16)));
    }
    return true;
}

void printHex(const uint8_t* data, size_t length, const char* end = "\n") {
    for (size_t i = 0; i < length; ++i) printf("%02x", data[i]);
    printf("%s", end);
}

// Obszar tablicy znanych celów w RAM (jak FRAM: nowa pamięć to same 0xFF). cutAfter: numer zapisu,
// w którym znika zasilanie (dochodzi tylko początek danych, potem każdy zapis zawodzi); -1 bez zaniku.
// failReads: tyle następnych odczytów zawodzi (chwilowy błąd SPI, treść bez zmian); failAt: tylko odczyt o tym
// numerze (1: następny) zawodzi, reads liczy wszystkie odczyty.
struct MemoryTable : rnscore::TableStorage {
    std::vector<uint8_t> bytes = std::vector<uint8_t>(rnscore::TABLE_AREA, 0xFF);
    long writes = 0;
    long cutAfter = -1;
    long failReads = 0;
    long failAt = 0;
    long reads = 0;
    bool read(uint32_t offset, uint8_t* data, size_t count) override {
        if (offset + count > bytes.size()) return false;
        ++reads;
        if (failAt > 0 && --failAt == 0) return false;
        if (failReads > 0) {
            --failReads;
            return false;
        }
        memcpy(data, bytes.data() + offset, count);
        return true;
    }
    bool write(uint32_t offset, const uint8_t* data, size_t count) override {
        if (offset + count > bytes.size()) return false;
        if (cutAfter >= 0 && writes > cutAfter) return false;
        const size_t n = cutAfter >= 0 && writes == cutAfter ? count / 2 : count;
        ++writes;
        memcpy(bytes.data() + offset, data, n);
        return n == count;
    }
};

// Stan poleceń t_* (transport): jedna stacja z celem "wici.sa1", zapis wywołań z transportu.
struct TransportState {
    MemoryTable table;
    rnscore::Transport transport;
    uint8_t privateKey[rnscore::KEY_SIZE] = {};
    uint8_t publicKey[rnscore::KEY_SIZE] = {};
    uint8_t identity[rnscore::TRUNCATED_HASH_SIZE] = {};
    uint8_t address[rnscore::TRUNCATED_HASH_SIZE] = {};
    uint8_t nameHash[rnscore::NAME_HASH_SIZE] = {};
    std::vector<uint8_t> pinned;   // jeden cel chroniony albo pusty
    std::vector<uint8_t> emitted;  // ostatni pakiet do nadania
    std::vector<std::vector<uint8_t>> sent;   // wszystkie pakiety do nadania od ostatniego t_out
    std::vector<uint8_t> sentIface;           // ich interfejsy (t_outif)
    uint8_t interfaces = 1;                   // liczba interfejsów transportu (t_begin z 65 B)
    std::string events;            // wywołania announce, packet i receipt od ostatniego polecenia
    bool accept = true;
    uint8_t busy = 0;    // bit 1 << interfejs: interfejs nie przyjmie pakietu (mayTransmit)
    long dropTx = 0;        // następne tyle nadań transmit odmówi (t_drop_tx), mimo zgody mayTransmit
    unsigned txCalls[8] = {};   // wywołania transmit na interfejs, także odrzucone (t_calls)
    uint8_t declined = 0;   // bit 1 << interfejs: transmit odmawia ramki (t_emit, t_decline)
    bool refuse = false; // brak żetonu na pakiet do stacji (mayReceive)
    uint64_t nowMs = 1000;
};
TransportState* state = nullptr;

}  // namespace

namespace rnscore {
struct EmitCheck {
    static uint8_t emit(Transport& transport, const uint8_t* raw, size_t length, uint8_t ifaces) {
        return transport.emit(raw, length, true, ifaces);
    }
};
}  // namespace rnscore

namespace {

void printHexTo(std::string& out, const uint8_t* data, size_t length) {
    char b[3];
    for (size_t i = 0; i < length; ++i) {
        snprintf(b, sizeof(b), "%02x", data[i]);
        out += b;
    }
}

bool onMayTransmit(uint8_t iface, void*) { return !(state->busy & (1u << iface)); }
bool onMayReceive(void*) { return !state->refuse; }

bool onTransmit(const uint8_t* raw, size_t length, uint8_t iface, void*) {
    ++state->txCalls[iface & 7];
    if (state->dropTx > 0) {
        --state->dropTx;
        return false;
    }
    if (state->declined & (1u << iface)) return false;
    state->emitted.assign(raw, raw + length);
    state->sent.emplace_back(raw, raw + length);
    state->sentIface.push_back(iface);
    return true;
}
void onAnnounce(const uint8_t destination[16], const uint8_t* appData, size_t length, void*) {
    state->events += " announce:";
    printHexTo(state->events, destination, 16);
    state->events += ":";
    printHexTo(state->events, appData, length);
}
bool onPacket(const uint8_t* data, size_t length, void*) {
    state->events += " packet:";
    printHexTo(state->events, data, length);
    return state->accept;
}
void onReceipt(uint32_t handle, bool delivered, void*) {
    state->events += " receipt:" + std::to_string(handle) + (delivered ? ":1" : ":0");
}
bool onRandom(uint8_t* out, size_t length, void*) {
    memset(out, 0x5A, length);   // stałe bajty: wynik do porównania
    return true;
}
bool onPinned(const uint8_t destination[16], void*) {
    return state->pinned.size() == 16 && memcmp(state->pinned.data(), destination, 16) == 0;
}

// Wiersz po poleceniu t_*: wynik, liczniki (duplikaty, pominięte, odrzucone, ogłoszenia, odebrane,
// bez dowodu, wysłane, doręczone, po limicie), wywołania, pakiet do nadania albo "-".
void printTransport(const char* result) {
    const rnscore::TransportCounters& c = state->transport.counters();
    printf("%s %u %u %u %u %u %u %u %u %u%s ", result, c.duplicate, c.ignored, c.invalid, c.announces, c.received, c.unproven,
           c.sent, c.delivered, c.timedOut, state->events.c_str());
    if (state->emitted.empty()) printf("-\n"); else printHex(state->emitted.data(), state->emitted.size());
    state->events.clear();
    state->emitted.clear();
}

}  // namespace

int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream fields(line);
        std::string command, hex;
        std::vector<uint8_t> data;
        fields >> command >> hex;
        if (command.empty() || !fromHex(hex, data)) {
            printf("error\n");
        } else if (command == "full_hash") {
            uint8_t out[rnscore::HASH_SIZE];
            rnscore::fullHash(data.data(), data.size(), out);
            printHex(out, sizeof(out));
        } else if (command == "truncated_hash") {
            uint8_t out[rnscore::TRUNCATED_HASH_SIZE];
            rnscore::truncatedHash(data.data(), data.size(), out);
            printHex(out, sizeof(out));
        } else if (command == "destination_hash" && data.size() >= rnscore::TRUNCATED_HASH_SIZE) {
            // skrót tożsamości 16 B, pełna nazwa celu (UTF-8)
            const std::string name(data.begin() + rnscore::TRUNCATED_HASH_SIZE, data.end());
            uint8_t out[rnscore::TRUNCATED_HASH_SIZE];
            rnscore::destinationHash(name.c_str(), data.data(), out);
            printHex(out, sizeof(out));
        } else if (command == "validate_announce") {
            // pakiet; pola przyjętego ogłoszenia (klucz, skrót nazwy, skrót losowy, ratchet albo "-",
            // dane aplikacji albo "-") albo "none" tam, gdzie Identity.validate_announce zwraca False
            rnscore::Packet packet;
            rnscore::Announce a;
            if (rnscore::unpack(data.data(), data.size(), packet) && rnscore::validateAnnounce(packet, a)) {
                printHex(a.publicKey, rnscore::KEY_SIZE, " ");
                printHex(a.nameHash, rnscore::NAME_HASH_SIZE, " ");
                printHex(a.randomHash, rnscore::RANDOM_HASH_SIZE, " ");
                if (a.ratchet) printHex(a.ratchet, rnscore::RATCHET_SIZE, " "); else printf("- ");
                if (a.appDataLength) printHex(a.appData, a.appDataLength); else printf("-\n");
            } else {
                printf("none\n");
            }
        } else if (command == "build_announce" && data.size() >= rnscore::KEY_SIZE + rnscore::RANDOM_HASH_SIZE + 1) {
            // klucz prywatny 64 B, skrót losowy 10 B, 1 B (1: dalej ratchet 32 B), dane aplikacji;
            // pakiet ANNOUNCE celu "wici.sa1" (HEADER_1, bez skoków) albo "none"
            const uint8_t* p = data.data();
            const bool hasRatchet = p[rnscore::KEY_SIZE + rnscore::RANDOM_HASH_SIZE] == 1;
            const size_t fixed = rnscore::KEY_SIZE + rnscore::RANDOM_HASH_SIZE + 1 + (hasRatchet ? rnscore::RATCHET_SIZE : 0);
            if (data.size() < fixed) {
                printf("error\n");
            } else {
                uint8_t pub[rnscore::KEY_SIZE], identity[rnscore::TRUNCATED_HASH_SIZE], name[rnscore::NAME_HASH_SIZE];
                rnscore::publicKey(p, pub);
                rnscore::identityHash(pub, identity);
                rnscore::nameHash("wici.sa1", name);
                rnscore::Packet packet = {};
                packet.headerType = rnscore::HEADER_1;
                packet.contextFlag = hasRatchet ? 1 : 0;
                packet.transportType = rnscore::BROADCAST;
                packet.destinationType = rnscore::SINGLE;
                packet.packetType = rnscore::ANNOUNCE;
                rnscore::destinationHashFrom(name, identity, packet.destinationHash);
                uint8_t announce[rnscore::ANNOUNCE_MAX_SIZE];
                packet.dataLength = rnscore::buildAnnounce(
                    p, pub, packet.destinationHash, name, p + rnscore::KEY_SIZE,
                    hasRatchet ? p + rnscore::KEY_SIZE + rnscore::RANDOM_HASH_SIZE + 1 : nullptr, p + fixed,
                    data.size() - fixed, announce, sizeof(announce));
                packet.data = announce;
                uint8_t out[rnscore::MTU];
                const size_t length = packet.dataLength ? rnscore::pack(packet, out, sizeof(out)) : 0;
                if (length) printHex(out, length); else printf("none\n");
            }
        } else if (command == "random_hash" && data.size() == 5 + 8) {
            // 5 B losowych, czas w s (8 B big-endian)
            uint64_t t = 0;
            for (size_t i = 5; i < 13; ++i) t = (t << 8) | data[i];
            uint8_t out[rnscore::RANDOM_HASH_SIZE];
            rnscore::announceRandomHash(data.data(), t, out);
            printHex(out, sizeof(out));
        } else if (command == "public_key" && data.size() == rnscore::KEY_SIZE) {
            // klucz prywatny 64 B
            uint8_t out[rnscore::KEY_SIZE];
            rnscore::publicKey(data.data(), out);
            printHex(out, sizeof(out));
        } else if (command == "identity_hash" && data.size() == rnscore::KEY_SIZE) {
            // klucz publiczny 64 B
            uint8_t out[rnscore::TRUNCATED_HASH_SIZE];
            rnscore::identityHash(data.data(), out);
            printHex(out, sizeof(out));
        } else if (command == "sign" && data.size() >= rnscore::KEY_SIZE) {
            // klucz prywatny 64 B, wiadomość
            uint8_t pub[rnscore::KEY_SIZE], out[rnscore::SIGNATURE_SIZE];
            rnscore::publicKey(data.data(), pub);
            rnscore::sign(data.data(), pub, data.data() + rnscore::KEY_SIZE, data.size() - rnscore::KEY_SIZE, out);
            printHex(out, sizeof(out));
        } else if (command == "validate" && data.size() >= rnscore::KEY_SIZE + 2) {
            // klucz publiczny 64 B, długość podpisu (2 B, big-endian), podpis, wiadomość
            const uint8_t* p = data.data() + rnscore::KEY_SIZE;
            const size_t signatureLength = (size_t(p[0]) << 8) | p[1];
            if (data.size() < rnscore::KEY_SIZE + 2 + signatureLength) {
                printf("error\n");
            } else {
                const size_t offset = rnscore::KEY_SIZE + 2 + signatureLength;
                printf("%d\n", rnscore::validate(data.data(), p + 2, signatureLength, data.data() + offset,
                                                 data.size() - offset) ? 1 : 0);
            }
        } else if ((command == "encrypt" || command == "encrypt_short") &&
                   data.size() >= rnscore::KEY_SIZE + 32 + rnscore::TOKEN_IV_SIZE) {
            // klucz publiczny 64 B, klucz efemeryczny prywatny 32 B, IV 16 B, tekst jawny; "none" przy odmowie;
            // encrypt_short: bufor wyjścia o 1 B za mały
            const uint8_t* plaintext = data.data() + rnscore::KEY_SIZE + 32 + rnscore::TOKEN_IV_SIZE;
            const size_t length = data.size() - (plaintext - data.data());
            std::vector<uint8_t> out(rnscore::tokenSize(length) - (command == "encrypt_short" ? 1 : 0));
            if (rnscore::encrypt(data.data(), nullptr, data.data() + rnscore::KEY_SIZE, data.data() + rnscore::KEY_SIZE + 32,
                                 plaintext, length, out.data(), out.size())) {
                printHex(out.data(), out.size());
            } else {
                printf("none\n");
            }
        } else if (command == "encrypt_ratchet" &&
                   data.size() >= rnscore::KEY_SIZE + rnscore::RATCHET_SIZE + 32 + rnscore::TOKEN_IV_SIZE) {
            // klucz publiczny 64 B, klucz ratchetu 32 B, klucz efemeryczny prywatny 32 B, IV 16 B, tekst jawny
            const uint8_t* p = data.data();
            const uint8_t* plaintext = p + rnscore::KEY_SIZE + rnscore::RATCHET_SIZE + 32 + rnscore::TOKEN_IV_SIZE;
            const size_t length = data.size() - (plaintext - p);
            std::vector<uint8_t> out(rnscore::tokenSize(length));
            if (rnscore::encrypt(p, p + rnscore::KEY_SIZE, p + rnscore::KEY_SIZE + rnscore::RATCHET_SIZE,
                                 p + rnscore::KEY_SIZE + rnscore::RATCHET_SIZE + 32, plaintext, length, out.data(),
                                 out.size())) {
                printHex(out.data(), out.size());
            } else {
                printf("none\n");
            }
        } else if (command == "prove" && data.size() == rnscore::KEY_SIZE + rnscore::HASH_SIZE + 1) {
            // klucz prywatny 64 B, skrót pakietu 32 B, 1 B (1: dowód niejawny)
            uint8_t pub[rnscore::KEY_SIZE], out[rnscore::PROOF_EXPLICIT_SIZE];
            rnscore::publicKey(data.data(), pub);
            const size_t length = rnscore::prove(data.data(), pub, data.data() + rnscore::KEY_SIZE,
                                                 data[rnscore::KEY_SIZE + rnscore::HASH_SIZE] == 1, out);
            printHex(out, length);
        } else if (command == "validate_proof" && data.size() >= rnscore::KEY_SIZE + rnscore::HASH_SIZE) {
            // klucz publiczny 64 B, skrót pakietu 32 B, dowód
            const size_t offset = rnscore::KEY_SIZE + rnscore::HASH_SIZE;
            printf("%d\n", rnscore::validateProof(data.data(), data.data() + rnscore::KEY_SIZE, data.data() + offset,
                                                   data.size() - offset) ? 1 : 0);
        } else if (command == "decrypt" && data.size() >= rnscore::KEY_SIZE) {
            // klucz prywatny 64 B, token; tekst jawny (może być pusty) albo "none" tam, gdzie Python zwraca None
            uint8_t pub[rnscore::KEY_SIZE];
            rnscore::publicKey(data.data(), pub);
            const size_t length = data.size() - rnscore::KEY_SIZE;
            std::vector<uint8_t> token(data.begin() + rnscore::KEY_SIZE, data.end());   // dokładnie length B dla ASan
            std::vector<uint8_t> out(length > rnscore::TOKEN_OVERHEAD ? length - rnscore::TOKEN_OVERHEAD : 0);
            size_t outLength = 0;
            if (rnscore::decrypt(data.data(), pub, token.data(), length, out.data(), out.size(), &outLength)) {
                printHex(out.data(), outLength);
            } else {
                printf("none\n");
            }
        } else if (command == "hkdf" && data.size() >= 3) {
            // długość wyniku (2 B, big-endian), długość soli (1 B), sól, materiał; wynik albo "none"
            const size_t length = (size_t(data[0]) << 8) | data[1];
            const size_t saltLength = data[2];
            if (data.size() < 3 + saltLength) {
                printf("error\n");
            } else {
                std::vector<uint8_t> out(length ? length : 1);
                const size_t offset = 3 + saltLength;
                if (rnscore::hkdf(data.data() + offset, data.size() - offset, data.data() + 3, saltLength, out.data(), length)) {
                    printHex(out.data(), length);
                } else {
                    printf("none\n");
                }
            }
        } else if ((command == "ifac_key" || command == "ifac_apply" || command == "ifac_check") && data.size() >= 1 &&
                   data.size() >= 1u + data[0]) {
            // długość frazy sieci (1 B), fraza (ASCII), potem pakiet (ifac_apply) albo datagram (ifac_check);
            // ifac_key: klucz IFAC 64 B; pozostałe: wynik albo "none" (kod IFAC 16 B)
            const std::string passphrase(data.begin() + 1, data.begin() + 1 + data[0]);
            const uint8_t* rest = data.data() + 1 + data[0];
            const size_t restLength = data.size() - 1 - data[0];
            rnscore::Ifac ifac;
            uint8_t out[rnscore::MTU + rnscore::IFAC_MAX_SIZE];
            size_t length = 0;
            std::vector<uint8_t> input(rest, rest + restLength);   // dokładnie restLength B dla ASan
            if (!rnscore::ifacSetup(nullptr, passphrase.c_str(), 16, ifac)) {
                printf("error\n");
            } else if (command == "ifac_key") {
                printHex(ifac.key, sizeof(ifac.key));
            } else {
                if (command == "ifac_apply") length = rnscore::ifacApply(ifac, input.data(), input.size(), out, sizeof(out));
                else length = rnscore::ifacCheck(ifac, input.data(), input.size(), out, sizeof(out));
                if (length) printHex(out, length); else printf("none\n");
            }
        } else if (command == "t_begin" && (data.size() == rnscore::KEY_SIZE || data.size() == rnscore::KEY_SIZE + 1)) {
            // klucz prywatny stacji 64 B, opcjonalnie liczba interfejsów (1 B): nowy transport z celem
            // "wici.sa1"; adres stacji
            delete state;
            state = new TransportState();
            if (data.size() > rnscore::KEY_SIZE) state->interfaces = data[rnscore::KEY_SIZE];
            memcpy(state->privateKey, data.data(), rnscore::KEY_SIZE);
            rnscore::publicKey(state->privateKey, state->publicKey);
            rnscore::identityHash(state->publicKey, state->identity);
            rnscore::nameHash("wici.sa1", state->nameHash);
            rnscore::destinationHashFrom(state->nameHash, state->identity, state->address);
            rnscore::TransportHooks hooks;
            hooks.transmit = onTransmit;
            hooks.announce = onAnnounce;
            hooks.packet = onPacket;
            hooks.receipt = onReceipt;
            hooks.pinned = onPinned;
            hooks.random = onRandom;
            hooks.mayTransmit = onMayTransmit;
            hooks.mayReceive = onMayReceive;
            state->transport.begin(state->privateKey, state->publicKey, state->identity, state->address, state->nameHash, hooks,
                                   state->table, state->nowMs, state->interfaces);
            printHex(state->address, sizeof(state->address));
        } else if (state && command == "t_restart" && (data.size() <= 2 || data.size() == 10)) {
            // restart stacji z tą samą pamięcią (zegar dalej); opcjonalnie 1 B: limit tablicy po starcie (0: bez
            // limitu), 1 B: nowa liczba interfejsów i 8 B: czas startu w ms (big-endian; zegar cofnięty, gdy
            // dziennik czasu pracy zawiódł). Wynik: liczba znanych celów i tras.
            if (data.size() >= 2) state->interfaces = data[1];
            if (data.size() == 10) {
                state->nowMs = 0;
                for (size_t i = 2; i < 10; ++i) state->nowMs = (state->nowMs << 8) | data[i];
            }
            rnscore::TransportHooks hooks;
            hooks.transmit = onTransmit;
            hooks.announce = onAnnounce;
            hooks.packet = onPacket;
            hooks.receipt = onReceipt;
            hooks.pinned = onPinned;
            hooks.random = onRandom;
            hooks.mayTransmit = onMayTransmit;
            hooks.mayReceive = onMayReceive;
            state->table.cutAfter = -1;
            state->transport.clear();
            state->transport.begin(state->privateKey, state->publicKey, state->identity, state->address, state->nameHash, hooks,
                                   state->table, state->nowMs, state->interfaces);
            if (!data.empty() && data[0]) state->transport.setLimit(data[0]);
            printf("%u %u\n", static_cast<unsigned>(state->transport.known()), static_cast<unsigned>(state->transport.paths()));
        } else if (state && command == "t_cut" && data.size() == 4) {
            // zanik zasilania w zapisie numer N (4 B, big-endian) licząc od teraz; wynik: zapisy do teraz
            const long n = static_cast<long>((uint32_t(data[0]) << 24) | (uint32_t(data[1]) << 16) | (uint32_t(data[2]) << 8) | data[3]);
            printf("%ld\n", state->table.writes);
            state->table.cutAfter = state->table.writes + n;
        } else if (state && command == "t_poke" && data.size() >= 4) {
            // bajty wprost do obszaru tablicy od adresu (4 B, big-endian), bez liczenia zapisów: uszkodzenia
            const uint32_t at = (uint32_t(data[0]) << 24) | (uint32_t(data[1]) << 16) | (uint32_t(data[2]) << 8) | data[3];
            const bool fits = at <= state->table.bytes.size() && data.size() - 4 <= state->table.bytes.size() - at;
            if (fits) memcpy(state->table.bytes.data() + at, data.data() + 4, data.size() - 4);
            printf(fits ? "ok\n" : "error\n");
        } else if (state && command == "t_request" && data.size() == 32) {
            // własne zapytanie o trasę: cel 16 B, znacznik 16 B
            printTransport(state->transport.requestPath(data.data(), data.data() + 16, state->nowMs) ? "ok" : "none");
        } else if (state && command == "t_paths") {
            // liczniki zapytań o trasę: przyjęte, z odpowiedzią, odpowiedzi wysłane, bez odpowiedzi z limitu,
            // własne, tablica ogłoszeń pełna, wpisy tablicy ogłoszeń
            const rnscore::TransportCounters& c = state->transport.counters();
            printf("%u %u %u %u %u %u %u\n", c.pathRequests, c.pathAnswered, c.pathResponses, c.pathLimited, c.requestsSent,
                   c.announceTableFull,
                   static_cast<unsigned>(state->transport.announceTable()));
        } else if (state && command == "t_out") {
            // wszystkie pakiety do nadania od poprzedniego t_out, rozdzielone spacjami, albo "-"
            std::string out;
            for (const std::vector<uint8_t>& raw : state->sent) {
                if (!out.empty()) out += " ";
                printHexTo(out, raw.data(), raw.size());
            }
            state->sent.clear();
            state->sentIface.clear();
            printf("%s\n", out.empty() ? "-" : out.c_str());
        } else if (state && command == "t_outif") {
            // jak t_out, każdy pakiet z numerem interfejsu: "<interfejs>:<pakiet>"
            std::string out;
            for (size_t i = 0; i < state->sent.size(); ++i) {
                if (!out.empty()) out += " ";
                out += std::to_string(state->sentIface[i]) + ":";
                printHexTo(out, state->sent[i].data(), state->sent[i].size());
            }
            state->sent.clear();
            state->sentIface.clear();
            printf("%s\n", out.empty() ? "-" : out.c_str());
        } else if (state && command == "t_route" && data.size() == 16) {
            // interfejs trasy do celu (IDX_PT_RVCD_IF) albo "none" bez trasy
            rnscore::KnownDestination e;
            if (state->transport.lookup(data.data(), e, state->nowMs) && e.hasPath) printf("%u\n", e.interface);
            else printf("none\n");
        } else if (state && command == "t_routes" && (data.size() == 2 || data.size() == 3)) {
            // cele z trasą przez interfejs data[0] (najwyżej data[1], najpierw ostatnio używane; opcjonalnie
            // data[2]: liczba skoków) z interfejsem trasy z indeksu (pathInterface) albo "-"
            uint8_t routes[8][rnscore::TRUNCATED_HASH_SIZE];
            const size_t n = state->transport.routes(data[0], data.size() == 3 ? data[2] : 0, routes, data[1] < 8 ? data[1] : 8);
            for (size_t i = 0; i < n; ++i) {
                if (i) printf(" ");
                printHex(routes[i], sizeof(routes[i]), "");
                printf(":%d", state->transport.pathInterface(routes[i]));
            }
            printf("%s\n", n ? "" : "-");
        } else if (state && command == "t_forward") {
            // transport: przekazane, bez trasy, dowody przekazane, tablica odwrotna pełna, retransmisje
            // ogłoszeń, wpisy tablicy odwrotnej, wpisy tablicy ogłoszeń
            const rnscore::TransportCounters& c = state->transport.counters();
            printf("%u %u %u %u %u %u %u\n", c.forwarded, c.noPath, c.proofsForwarded, c.reverseFull, c.rebroadcasts,
                   static_cast<unsigned>(state->transport.reverseEntries(state->nowMs)),
                   static_cast<unsigned>(state->transport.announceTable()));
        } else if (state && command == "t_writes") {
            printf("%ld\n", state->table.writes);
        } else if (state && command == "t_reads") {
            printf("%ld\n", state->table.reads);
        } else if (state && command == "t_failat" && data.size() == 2) {
            // zawodzi tylko n-ty następny odczyt tablicy (2 B, big-endian; 1: najbliższy)
            state->table.failAt = (data[0] << 8) | data[1];
            printf("ok\n");
        } else if (state && command == "t_readfail" && data.size() == 1) {
            // tyle następnych odczytów tablicy zawodzi (1 B); wynik: gniazda z błędną treścią od startu
            state->table.failReads = data[0];
            printf("%u\n", static_cast<unsigned>(state->transport.tableCorrupt()));
        } else if (!state && command.rfind("t_", 0) == 0) {
            printf("error\n");
        } else if (command == "t_clock" && data.size() == 8) {
            // czas w ms (8 B, big-endian); po nim poll() potwierdzeń
            state->nowMs = 0;
            for (uint8_t b : data) state->nowMs = (state->nowMs << 8) | b;
            state->transport.poll(state->nowMs);
            printTransport("ok");
        } else if (command == "t_held") {
            // wstrzymane retransmisje (held_announces)
            printf("%u\n", static_cast<unsigned>(state->transport.heldAnnounces()));
        } else if (state && command == "t_decline" && data.size() == 1) {
            // interfejsy z maski (bit 1 << numer) odmawiają każdego nadania transmit, choć mayTransmit zezwala
            state->declined = data[0];
            printTransport("ok");
        } else if (state && command == "t_calls") {
            // wywołania transmit od początku: interfejs 0, interfejs 1
            printf("%u %u\n", state->txCalls[0], state->txCalls[1]);
        } else if (state && command == "t_drop_tx" && data.size() == 1) {
            // następnych N (1 B) nadań transmit odmówi, choć mayTransmit zezwala
            state->dropTx = data[0];
            printTransport("ok");
        } else if (command == "t_busy" && data.size() == 1) {
            // interfejsy zajęte dla mayTransmit: bit 1 << numer (1: interfejs 0 zajęty, 0: wszystkie wolne)
            state->busy = data[0];
            printTransport("ok");
        } else if (state && command == "t_emit" && data.size() > 18) {
            // nadanie ramki (bajty od 3.) interfejsami z maski (2. B), gdy transmit odmawia interfejsom z maski
            // odmów (1. B); wynik: maska przyjętych i liczba skrótów na liście
            state->declined = data[0];
            const uint8_t mask = rnscore::EmitCheck::emit(state->transport, data.data() + 2, data.size() - 2, data[1]);
            state->declined = 0;
            printf("%u %u\n", static_cast<unsigned>(mask), static_cast<unsigned>(state->transport.hashes()));
        } else if (command == "t_refuse" && data.size() == 1) {
            // brak żetonu (1) albo żeton (0) dla mayReceive
            state->refuse = data[0] != 0;
            printTransport("ok");
        } else if (command == "t_limited") {
            // pakiety do stacji odrzucone przed odszyfrowaniem (receiveLimited)
            printf("%u\n", static_cast<unsigned>(state->transport.counters().receiveLimited));
        } else if (command == "t_poll" && data.size() == 8) {
            // czas w ms (8 B) i poll() bez nadawania (obieg z kryptografią odbioru)
            state->nowMs = 0;
            for (uint8_t b : data) state->nowMs = (state->nowMs << 8) | b;
            state->transport.poll(state->nowMs, false);
            printTransport("ok");
        } else if (command == "t_config" && (data.size() == 2 || data.size() == 18)) {
            // limit tablicy (1 B), przyjmowanie przez warstwę aplikacji (1 B: 0/1), opcjonalnie cel chroniony 16 B
            state->transport.setLimit(data[0]);
            state->accept = data[1] != 0;
            state->pinned.assign(data.begin() + 2, data.end());
            printTransport("ok");
        } else if (command == "t_in") {
            // pakiet bez IFAC
            printTransport(state->transport.inbound(data.data(), data.size(), state->nowMs) ? "ok" : "malformed");
        } else if (command == "t_inif" && !data.empty()) {
            // numer interfejsu odbioru (1 B), pakiet bez IFAC
            printTransport(state->transport.inbound(data.data() + 1, data.size() - 1, state->nowMs, data[0]) ? "ok" : "malformed");
        } else if (command == "t_announce") {
            // 5 B losowych, dane aplikacji
            printTransport(data.size() >= 5 && state->transport.announce(data.data(), data.data() + 5, data.size() - 5, state->nowMs)
                               ? "ok" : "none");
        } else if (command == "t_send" && data.size() >= 16 + 32 + 16 + 4 + 4) {
            // cel 16 B, klucz efemeryczny 32 B, IV 16 B, uchwyt 4 B, limit w ms 4 B, dane
            const uint8_t* p = data.data();
            const uint32_t handle = (uint32_t(p[64]) << 24) | (uint32_t(p[65]) << 16) | (uint32_t(p[66]) << 8) | p[67];
            const uint32_t timeout = (uint32_t(p[68]) << 24) | (uint32_t(p[69]) << 16) | (uint32_t(p[70]) << 8) | p[71];
            static const char* names[] = {"sent", "unknown", "too_large", "receipts_full", "refused"};
            const rnscore::SendResult r =
                state->transport.send(p, p + 72, data.size() - 72, p + 16, p + 48, handle, timeout, state->nowMs);
            printTransport(names[static_cast<int>(r)]);
        } else if (command == "t_known" && data.size() == 16) {
            // cel: "none" albo skoki, ratchet (0/1), trasa (0/1), następny skok, klucz ratchetu ("-" bez niego),
            // klucz publiczny, ogłoszenie w pamięci podręcznej ("-" bez niego)
            rnscore::KnownDestination e;
            if (!state->transport.lookup(data.data(), e, state->nowMs)) {
                printf("none\n");
            } else {
                printf("%u %d %d ", e.hops, e.hasRatchet ? 1 : 0, e.hasPath ? 1 : 0);
                printHex(e.nextHop, sizeof(e.nextHop), " ");
                if (e.hasRatchet) printHex(e.ratchet, sizeof(e.ratchet), " "); else printf("- ");
                printHex(e.publicKey, sizeof(e.publicKey), " ");
                if (e.announceLength) printHex(state->transport.cachedAnnounce(), e.announceLength); else printf("-\n");
            }
        } else if (command == "unpack") {
            // pakiet; pola rozdzielone spacjami (identyfikator transportu "-" w HEADER_1) i skrót pakietu,
            // albo "none" tam, gdzie Python odrzuca pakiet
            rnscore::Packet packet;
            if (rnscore::unpack(data.data(), data.size(), packet)) {
                printf("%u %u %u %u %u %u ", packet.headerType, packet.contextFlag, packet.transportType,
                       packet.destinationType, packet.packetType, packet.hops);
                if (packet.headerType == rnscore::HEADER_2) {
                    printHex(packet.transportId, sizeof(packet.transportId), " ");
                } else {
                    printf("- ");
                }
                printHex(packet.destinationHash, sizeof(packet.destinationHash), " ");
                printf("%u ", packet.context);
                printHex(packet.data, packet.dataLength, " ");
                uint8_t hash[rnscore::HASH_SIZE];
                rnscore::packetHash(data.data(), data.size(), hash);
                printHex(hash, sizeof(hash));
            } else {
                printf("none\n");
            }
        } else if (command == "pack" && data.size() >= 6 + 2 * rnscore::TRUNCATED_HASH_SIZE + 1) {
            // typ nagłówka, flaga kontekstu, typ transportu, typ celu, typ pakietu, skoki (po 1 B),
            // identyfikator transportu 16 B, skrót celu 16 B, kontekst 1 B, dane; pakiet albo "none"
            const uint8_t* p = data.data();
            rnscore::Packet packet;
            packet.headerType = static_cast<rnscore::HeaderType>(p[0]);
            packet.contextFlag = p[1];
            packet.transportType = static_cast<rnscore::TransportType>(p[2]);
            packet.destinationType = static_cast<rnscore::DestinationType>(p[3]);
            packet.packetType = static_cast<rnscore::PacketType>(p[4]);
            packet.hops = p[5];
            memcpy(packet.transportId, p + 6, rnscore::TRUNCATED_HASH_SIZE);
            memcpy(packet.destinationHash, p + 6 + rnscore::TRUNCATED_HASH_SIZE, rnscore::TRUNCATED_HASH_SIZE);
            packet.context = p[6 + 2 * rnscore::TRUNCATED_HASH_SIZE];
            packet.data = p + 6 + 2 * rnscore::TRUNCATED_HASH_SIZE + 1;
            packet.dataLength = data.size() - (6 + 2 * rnscore::TRUNCATED_HASH_SIZE + 1);
            // Bufor większy od MTU: granicę pakietu pilnuje `pack`, nie rozmiar bufora.
            uint8_t out[2 * rnscore::MTU];
            const size_t length = rnscore::pack(packet, out, sizeof(out));
            if (length) {
                printHex(out, length);
            } else {
                printf("none\n");
            }
        } else if (command == "selftest" && data.size() == 1) {
            // 1 B: liczba prób (QUICK albo COUNT); "1" albo "0" i nazwa:wynik każdej próby
            coreselftest::Result results[coreselftest::COUNT];
            const size_t count = data[0] < coreselftest::COUNT ? data[0] : coreselftest::COUNT;
            const bool ok = coreselftest::run(results, count, [] { return uint32_t{0}; });
            printf("%d", ok ? 1 : 0);
            for (size_t i = 0; i < count; ++i) printf(" %s:%d", results[i].name, results[i].ok ? 1 : 0);
            printf("\n");
        } else if (command == "huge_lengths" && data.size() == rnscore::KEY_SIZE) {
            // klucz prywatny 64 B; pack i buildAnnounce z długością danych bliską SIZE_MAX (błąd wywołującego)
            // mają odmówić bez dostępu do danych: obie długości wyniku w jednym wierszu
            uint8_t pub[rnscore::KEY_SIZE], name[rnscore::NAME_HASH_SIZE] = {}, random[rnscore::RANDOM_HASH_SIZE] = {};
            uint8_t dest[rnscore::TRUNCATED_HASH_SIZE] = {}, small[1] = {}, out[rnscore::MTU];
            rnscore::publicKey(data.data(), pub);
            rnscore::Packet packet = {};
            packet.data = small;
            packet.dataLength = SIZE_MAX - 10;
            const size_t packed = rnscore::pack(packet, out, sizeof(out));
            const size_t built = rnscore::buildAnnounce(data.data(), pub, dest, name, random, nullptr, small, SIZE_MAX - 100,
                                                        out, sizeof(out));
            printf("%zu %zu\n", packed, built);
        } else {
            printf("error\n");
        }
        fflush(stdout);
    }
    delete state;
    return 0;
}
