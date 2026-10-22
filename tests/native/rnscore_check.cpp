// SPDX-License-Identifier: MIT
// Program prób rdzenia Reticulum stacji na komputerze (tests/test_rnscore.py): czyta ze standardowego
// wejścia wiersze "polecenie dane_hex" i dla każdego wypisuje jeden wiersz z wynikiem szesnastkowo
// albo "error". Polecenia z kilkoma argumentami biorą je sklejone w jednym ciągu, w kolejności z opisu
// przy poleceniu (klucze i podpisy mają stałą długość, reszta to wiadomość). Wartości oczekiwane (wektory z Reticulum w Pythonie) porównuje test w Pythonie.
#include <stdio.h>

#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "hash.h"
#include "identity.h"
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
        } else {
            printf("error\n");
        }
        fflush(stdout);
    }
    return 0;
}
