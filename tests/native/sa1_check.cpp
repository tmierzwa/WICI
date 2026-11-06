// SPDX-License-Identifier: MIT
// Kodek SA1 stacji (firmware/src/sa1.cpp) dla wektorów z tests/vectors/sa1.json. Bajtów tu nie ma:
// tests/test_sa1_vectors.py podaje je z pliku na wejście, wiersz za wierszem:
//   decode <hex>     wypisuje "OK <pola>" albo "REJECT <powód>"
//   encode <pola>    wypisuje "OK <hex>" albo "REJECT"
// Pola: typ id revision category people urgency event state hex(location) hex(text).
// Pusty ciąg bajtów ma w wierszu postać "-".
#include "sa1.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "hexstr.h"

namespace {

constexpr size_t MAX_INPUT = 1024;  // Wektory dłuższe od limitu 256 B też muszą tu wejść.

const char* hexOrDash(const char* bytes, size_t length, char* out) {
    if (!length) return "-";
    hexstr::encode(reinterpret_cast<const uint8_t*>(bytes), length, out);
    return out;
}

// Liczba bajtów albo -1. Puste pole ("-") ma zero bajtów.
long fromHex(const char* token, char* out, size_t size) {
    if (!strcmp(token, "-")) return 0;
    const size_t length = strlen(token) / 2;
    if (length > size || !hexstr::decode(token, reinterpret_cast<uint8_t*>(out), length)) return -1;
    return static_cast<long>(length);
}

void decodeLine(const char* token) {
    static char wire[MAX_INPUT];
    const long length = fromHex(token, wire, sizeof(wire));
    if (length < 0) exit(2);
    sa1::Message message;
    const char* why = sa1::decode(wire, static_cast<size_t>(length), message);
    if (why) {
        printf("REJECT %s\n", why);
        return;
    }
    static char location[2 * sa1::LOCATION_MAX + 1], text[2 * sa1::BULLETIN_MAX + 1];
    const char* locationHex = hexOrDash(message.location, strlen(message.location), location);
    const char* textHex = hexOrDash(message.text, strlen(message.text), text);
    printf("OK %u %s %u %u %u %u %lu %u %s %s\n", message.type, message.id, message.revision, message.category,
           message.people, message.urgency, static_cast<unsigned long>(message.event), message.state, locationHex, textHex);
}

const char* next() {
    const char* token = strtok(nullptr, " \n");
    if (!token) exit(2);
    return token;
}

void encodeLine() {
    sa1::Message message;
    message.type = static_cast<uint8_t>(atoi(next()));
    const char* id = next();
    if (strlen(id) != sa1::ID_HEX) exit(2);
    memcpy(message.id, id, sa1::ID_HEX);
    message.revision = static_cast<uint16_t>(atol(next()));
    message.category = static_cast<uint8_t>(atoi(next()));
    message.people = static_cast<uint16_t>(atol(next()));
    message.urgency = static_cast<uint8_t>(atoi(next()));
    message.event = static_cast<uint32_t>(strtoul(next(), nullptr, 10));
    message.state = static_cast<uint8_t>(atoi(next()));
    if (fromHex(next(), message.location, sa1::LOCATION_MAX) < 0 || fromHex(next(), message.text, sa1::BULLETIN_MAX) < 0) exit(2);
    static char wire[sa1::MAX_CONTENT + 1], out[2 * sa1::MAX_CONTENT + 1];
    const size_t length = sa1::encode(message, wire, sizeof(wire));
    if (!length) {
        puts("REJECT");
        return;
    }
    printf("OK %s\n", hexOrDash(wire, length, out));
}

}  // namespace

int main() {
    static char line[4 * MAX_INPUT];
    while (fgets(line, sizeof(line), stdin)) {
        const char* command = strtok(line, " \n");
        if (!command) return 2;
        if (!strcmp(command, "decode")) decodeLine(next());
        else if (!strcmp(command, "encode")) encodeLine();
        else return 2;
    }
    return 0;
}
