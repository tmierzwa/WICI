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

// Ponowne kodowanie wartości sprawdzonej przez validate, jak packb(unpackb(dane)) w Pythonie. Znacznika
// czasu (EXT -1) Python nie koduje z powrotem tymi samymi bajtami (datetime), więc tu odmowa.
bool repack(mp::Reader& reader, mp::Writer& writer) {
    mp::Item item;
    if (!reader.read(item)) return false;
    switch (item.type) {
        case mp::Type::NIL: writer.nil(); return true;
        case mp::Type::BOOL: writer.boolean(item.boolean); return true;
        case mp::Type::UINT: writer.uinteger(item.uinteger); return true;
        case mp::Type::INT: writer.integer(item.integer); return true;
        case mp::Type::FLOAT32:
        case mp::Type::FLOAT64: writer.float64(item.real); return true;
        case mp::Type::STR: writer.str(item.data, item.length); return true;
        case mp::Type::BIN: writer.bin(item.data, item.length); return true;
        case mp::Type::EXT:
            if (item.extType == -1) return false;
            writer.ext(item.extType, item.data, item.length);
            return true;
        case mp::Type::ARRAY:
        case mp::Type::MAP: {
            const uint64_t count = item.type == mp::Type::ARRAY ? item.length : uint64_t(item.length) * 2;
            if (item.type == mp::Type::ARRAY) writer.array(item.length); else writer.map(item.length);
            for (uint64_t i = 0; i < count; ++i) {
                if (!repack(reader, writer)) return false;
            }
            return true;
        }
    }
    return false;
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
        } else if (command == "mp_repack" && !data.empty()) {
            // głębokość 1 B, dane; pierwsza wartość zakodowana ponownie albo "none"
            std::vector<uint8_t> input(data.begin() + 1, data.end());
            std::vector<uint8_t> out(2 * input.size() + 16);   // float32 → float64 wydłuża o 4 B na wartość
            mp::Reader reader(input.data(), input.size());
            mp::Writer writer(out.data(), out.size());
            if (mp::validate(input.data(), input.size(), data[0], nullptr) && repack(reader, writer) && writer.ok()) {
                printHex(out.data(), writer.length());
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
