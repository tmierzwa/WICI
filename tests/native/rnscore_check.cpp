// SPDX-License-Identifier: MIT
// Program prób rdzenia Reticulum stacji na komputerze (tests/test_rnscore.py): czyta ze standardowego
// wejścia wiersze "polecenie dane_hex" i dla każdego wypisuje jeden wiersz z wynikiem szesnastkowo
// albo "error". Polecenia z kilkoma argumentami biorą je sklejone w jednym ciągu, w kolejności z opisu
// przy poleceniu (klucze i podpisy mają stałą długość, reszta to wiadomość). Wartości oczekiwane (wektory z Reticulum w Pythonie) porównuje test w Pythonie.
#include <stdio.h>
#include <string.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "announce.h"
#include "destination.h"
#include "hash.h"
#include "identity.h"
#include "packet.h"
#include "token.h"

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
        } else if (command == "encrypt" && data.size() >= rnscore::KEY_SIZE + 32 + rnscore::TOKEN_IV_SIZE) {
            // klucz publiczny 64 B, klucz efemeryczny prywatny 32 B, IV 16 B, tekst jawny; "none" przy odmowie
            const uint8_t* plaintext = data.data() + rnscore::KEY_SIZE + 32 + rnscore::TOKEN_IV_SIZE;
            const size_t length = data.size() - (plaintext - data.data());
            std::vector<uint8_t> out(rnscore::tokenSize(length));
            if (rnscore::encrypt(data.data(), data.data() + rnscore::KEY_SIZE, data.data() + rnscore::KEY_SIZE + 32,
                                 plaintext, length, out.data())) {
                printHex(out.data(), out.size());
            } else {
                printf("none\n");
            }
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
            uint8_t out[rnscore::MTU];
            const size_t length = rnscore::pack(packet, out, sizeof(out));
            if (length) {
                printHex(out, length);
            } else {
                printf("none\n");
            }
        } else {
            printf("error\n");
        }
        fflush(stdout);
    }
    return 0;
}
