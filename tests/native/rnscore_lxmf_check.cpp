// SPDX-License-Identifier: MIT
// Program prób wiadomości LXMF SA1 rdzenia Reticulum stacji na komputerze (tests/test_rnscore_lxmf.py), jak
// tests/native/rnscore_check.cpp: czyta ze standardowego wejścia wiersze "polecenie dane_hex" i dla
// każdego wypisuje jeden wiersz z wynikiem albo "error". Argumenty sklejone w jednym ciągu w kolejności
// z opisu przy poleceniu. Wartości oczekiwane (wektory z LXMF w Pythonie) porównuje test w Pythonie.
#include <stdio.h>
#include <string.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "identity.h"
#include "lxmf.h"

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
        const size_t keyAndHashes = rnscore::KEY_SIZE + 2 * rnscore::TRUNCATED_HASH_SIZE;
        if (command.empty() || !fromHex(hex, data)) {
            printf("error\n");
        } else if (command == "lxmf_pack" && data.size() >= keyAndHashes + 8) {
            // klucz prywatny nadawcy 64 B, skrót celu 16 B, skrót nadawcy 16 B, czas (float64 big-endian
            // 8 B), treść; dane pakietu i skrót wiadomości albo "none"
            const uint8_t* p = data.data();
            uint64_t bits = 0;
            for (size_t i = 0; i < 8; ++i) bits = (bits << 8) | p[keyAndHashes + i];
            double timestamp;
            memcpy(&timestamp, &bits, sizeof(timestamp));
            std::vector<uint8_t> content(p + keyAndHashes + 8, p + data.size());   // dokładna długość dla ASan
            uint8_t pub[rnscore::KEY_SIZE], out[rnscore::LXMF_SA1_MAX_DATA], hash[rnscore::HASH_SIZE];
            rnscore::publicKey(p, pub);
            const size_t length = rnscore::lxmfPackSa1(p, pub, p + rnscore::KEY_SIZE, p + rnscore::KEY_SIZE + 16, timestamp,
                                                       content.data(), content.size(), out, sizeof(out), hash);
            if (length) {
                printHex(out, length, " ");
                printHex(hash, sizeof(hash));
            } else {
                printf("none\n");
            }
        } else if (command == "lxmf_receive" && data.size() >= rnscore::KEY_SIZE + rnscore::TRUNCATED_HASH_SIZE) {
            // klucz publiczny nadawcy 64 B, skrót celu 16 B, dane pakietu; skrót wiadomości, czas i treść albo
            // "none" (wiadomość odrzucona)
            const uint8_t* dest = data.data() + rnscore::KEY_SIZE;
            const uint8_t* end = data.data() + data.size();
            std::vector<uint8_t> packet(dest + rnscore::TRUNCATED_HASH_SIZE, end);
            rnscore::LxmfSa1 m;
            if (rnscore::lxmfReceiveSa1(dest, packet.data(), packet.size(), data.data(), m)) {
                printHex(m.hash, sizeof(m.hash), " ");
                printf("%.17g ", m.timestamp);
                printHex(m.content, m.contentLength);
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
