// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Kod dostępu interfejsu (IFAC): klucz 64 B z HKDF skrótu frazy sieci, kod = ostatnie bajty podpisu
// Ed25519 pakietu kluczem IFAC, maska z HKDF kodu. Datagram: [b0 | 0x80, b1], kod, reszta pakietu;
// wszystko poza kodem XOR z maską, flaga 0x80 ustawiona po maskowaniu.
#pragma once

#include "packet.h"
#include "rnscore.h"

namespace rnscore {

constexpr size_t IFAC_MIN_SIZE = 1;   // RNS/Reticulum.py: IFAC_MIN_SIZE
constexpr size_t IFAC_MAX_SIZE = SIGNATURE_SIZE;

struct Ifac {
    uint8_t key[KEY_SIZE];         // ifac_key, zarazem klucz prywatny tożsamości IFAC (Identity.from_bytes)
    uint8_t publicKey[KEY_SIZE];
    size_t size;                   // ifac_size w bajtach
};

// RNS/Reticulum.py: konfiguracja interfejsu z networkname i passphrase: ifac_origin = full_hash(nazwa)
// + full_hash(fraza) (pominięte, gdy brak), ifac_key = hkdf(64, full_hash(ifac_origin), IFAC_SALT),
// ifac_identity = Identity.from_bytes(ifac_key). Fałsz bez nazwy i frazy albo dla size spoza
// IFAC_MIN_SIZE..IFAC_MAX_SIZE.
bool ifacSetup(const char* networkName, const char* passphrase, size_t size, Ifac& out);

// RNS/Transport.py: Transport.handle_outgoing_ifac. raw: pakiet bez IFAC, od 2 do MTU B; wire ma
// length + size B i nie może zachodzić na raw. Zwraca długość wire albo 0 dla raw krótszego niż 2 B,
// dłuższego niż MTU (takiego nie składa pack) lub capacity za małego.
size_t ifacApply(const Ifac& ifac, const uint8_t* raw, size_t length, uint8_t* wire, size_t capacity);

// RNS/Transport.py: Transport.handle_ifac z warunkami z Transport.preprocess_inbound (flaga 0x80 ustawiona,
// datagram dłuższy niż 2 + size). raw ma length - size B i nie może zachodzić na wire; zwraca długość
// raw (flaga 0x80 skasowana) albo 0, gdy brak flagi, datagram za krótki, kod niezgodny albo capacity za
// małe. Datagram dłuższy niż MTU + size też daje 0 (maska w buforze stałym): Python sprawdza długość
// względem MTU interfejsu dopiero po kodzie, a interfejs P1 odrzuca taki datagram wcześniej (p1iface).
// Kod porównywany w stałym czasie.
size_t ifacCheck(const Ifac& ifac, const uint8_t* wire, size_t length, uint8_t* raw, size_t capacity);

}  // namespace rnscore
