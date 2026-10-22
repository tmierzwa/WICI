// SPDX-License-Identifier: MIT
// Program prób msgpack i LXMF rdzenia Reticulum stacji na komputerze (tests/test_rnscore_lxmf.py), jak
// tests/native/rnscore_check.cpp: czyta ze standardowego wejścia wiersze "polecenie dane_hex" i dla
// każdego wypisuje jeden wiersz z wynikiem albo "error". Argumenty sklejone w jednym ciągu w kolejności
// z opisu przy poleceniu. Wartości oczekiwane (wektory z LXMF w Pythonie) porównuje test w Pythonie.
#include <stdio.h>
#include <string.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "msgpack.h"

namespace {

namespace mp = rnscore::msgpack;

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
        } else if (command == "mp_validate" && !data.empty()) {
            // głębokość 1 B, dane; długość pierwszej wartości (dziesiętnie) albo "none" tam, gdzie unpackb
            // zgłasza błąd. Wektor kopiowany, żeby ASan pilnował dokładnej długości.
            std::vector<uint8_t> input(data.begin() + 1, data.end());
            size_t consumed = 0;
            if (mp::validate(input.data(), input.size(), data[0], &consumed)) {
                printf("%zu\n", consumed);
            } else {
                printf("none\n");
            }
        } else if (command == "mp_write" && !data.empty()) {
            // jedna operacja pisarza: "a" albo "m" i liczba 4 B big-endian (nagłówek tablicy albo mapy),
            // "f" i 8 B float64 big-endian, "b" i bajty; zapis albo "none" (ok() fałsz)
            const uint8_t* arg = data.data() + 1;
            const size_t argLength = data.size() - 1;
            uint64_t value = 0;
            for (size_t i = 0; i < argLength && i < 8; ++i) value = (value << 8) | arg[i];
            std::vector<uint8_t> out(argLength + 16);
            mp::Writer writer(out.data(), out.size());
            bool known = true;
            if (data[0] == 'a' && argLength == 4) {
                writer.array(value);
            } else if (data[0] == 'm' && argLength == 4) {
                writer.map(value);
            } else if (data[0] == 'f' && argLength == 8) {
                double real;
                memcpy(&real, &value, sizeof(real));
                writer.float64(real);
            } else if (data[0] == 'b') {
                writer.bin(arg, argLength);
            } else {
                known = false;
            }
            if (!known) printf("error\n"); else if (writer.ok()) printHex(out.data(), writer.length()); else printf("none\n");
        } else {
            printf("error\n");
        }
        fflush(stdout);
    }
    return 0;
}
