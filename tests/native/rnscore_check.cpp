// SPDX-License-Identifier: MIT
// Program prób rdzenia Reticulum stacji na komputerze (tests/test_rnscore.py): czyta ze standardowego
// wejścia wiersze "polecenie dane_hex" i dla każdego wypisuje jeden wiersz z wynikiem szesnastkowo
// albo "error". Wartości oczekiwane (wektory z Reticulum w Pythonie) porównuje test w Pythonie.
#include <stdio.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "hash.h"

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

void printHex(const uint8_t* data, size_t length) {
    for (size_t i = 0; i < length; ++i) printf("%02x", data[i]);
    printf("\n");
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
        } else {
            printf("error\n");
        }
        fflush(stdout);
    }
    return 0;
}
