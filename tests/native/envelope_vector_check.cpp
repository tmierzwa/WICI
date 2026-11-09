// SPDX-License-Identifier: MIT
// Koperta stacji (firmware/src/envelope.cpp) dla wektorów z tests/vectors/envelope.json. Bajtów tu nie
// ma: tests/test_envelope_vectors.py podaje je z pliku na wejście, wiersz za wierszem:
//   derive <prywatny> <publiczny drugiej strony> <net_id> <nadawca> <odbiorca> <własny numer>
//       wypisuje "OK <klucz>" albo "REJECT"
//   seal <klucz> <nadawca> <odbiorca> <licznik> <max_payload> <rodzaj> <jawny tekst>
//       wypisuje "OK <koperta> [<koperta>]" albo "REJECT"
//   open <klucz> <koperta>
//       wypisuje "OK <nadawca> <odbiorca> <licznik> <część> <jawny tekst>" albo "REJECT"
// Pusty ciąg bajtów ma w wierszu postać "-".
#include "envelope.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hexstr.h"

namespace {

constexpr size_t MAX_INPUT = 512;  // Wektory dłuższe od największej koperty też muszą tu wejść.

const char* next() {
    const char* token = strtok(nullptr, " \n");
    if (!token) exit(2);
    return token;
}

size_t bytes(const char* token, uint8_t* out, size_t size) {
    if (!strcmp(token, "-")) return 0;
    const size_t length = strlen(token) / 2;
    if (length > size || !hexstr::decode(token, out, length)) exit(2);
    return length;
}

void fixed(uint8_t* out, size_t size) {
    if (bytes(next(), out, size) != size) exit(2);
}

void printHex(const uint8_t* data, size_t length) {
    if (!length) fputs("-", stdout);
    for (size_t i = 0; i < length; ++i) printf("%02x", data[i]);
}

uint16_t number() { return static_cast<uint16_t>(strtoul(next(), nullptr, 10)); }

void derive() {
    uint8_t privateKey[32], peerPublic[32], key[32];
    fixed(privateKey, sizeof(privateKey));
    fixed(peerPublic, sizeof(peerPublic));
    const uint16_t netId = number(), sender = number(), recipient = number(), own = number();
    if (!envelope::deriveKey(privateKey, peerPublic, netId, sender, recipient, own, key)) {
        puts("REJECT");
        return;
    }
    fputs("OK ", stdout);
    printHex(key, sizeof(key));
    putchar('\n');
}

void seal() {
    uint8_t key[32];
    fixed(key, sizeof(key));
    const uint16_t sender = number(), recipient = number();
    const uint32_t counter = static_cast<uint32_t>(strtoul(next(), nullptr, 10));
    const size_t maxPayload = strtoul(next(), nullptr, 10);
    const uint8_t type = static_cast<uint8_t>(atoi(next()));
    static uint8_t plaintext[MAX_INPUT];
    const size_t length = bytes(next(), plaintext, sizeof(plaintext));
    static envelope::Frame frames[2];
    const size_t count = envelope::seal(key, sender, recipient, counter, plaintext, length, maxPayload, frames, type);
    if (!count) {
        puts("REJECT");
        return;
    }
    fputs("OK", stdout);
    for (size_t i = 0; i < count; ++i) {
        putchar(' ');
        printHex(frames[i].bytes, frames[i].length);
    }
    putchar('\n');
}

void open() {
    uint8_t key[32];
    fixed(key, sizeof(key));
    static uint8_t frame[MAX_INPUT];
    const size_t length = bytes(next(), frame, sizeof(frame));
    static envelope::Part part;
    if (!envelope::openPart(key, frame, length, part)) {
        puts("REJECT");
        return;
    }
    printf("OK %u %u %lu %u ", part.sender, part.recipient, static_cast<unsigned long>(part.counter), part.number);
    printHex(part.plaintext, part.length);
    putchar('\n');
}

}  // namespace

int main() {
    static char line[4 * MAX_INPUT];
    while (fgets(line, sizeof(line), stdin)) {
        const char* command = strtok(line, " \n");
        if (!command) return 2;
        if (!strcmp(command, "derive")) derive();
        else if (!strcmp(command, "seal")) seal();
        else if (!strcmp(command, "open")) open();
        else return 2;
    }
    return 0;
}
