// SPDX-License-Identifier: LicenseRef-Reticulum
// SPDX-FileCopyrightText: 2016-2026 Mark Qvist
// SPDX-FileCopyrightText: 2026 Tomek Mierzwa
// Wiadomość LXMF SA1 w jednym pakiecie okazjonalnym (OPPORTUNISTIC) do celu SINGLE "lxmf.delivery".
// Utwór zależny od LXMF c3ff2d6 (1.2.0, ta sama licencja Reticulum, © 2020-2025 Mark Qvist).
// Dane pakietu przed szyfrowaniem: skrót celu nadawcy 16 B, podpis Ed25519 64 B, payload MessagePack
// [czas, tytuł, treść, pola]; skrót celu odbiorcy jest w nagłówku pakietu. Skrót wiadomości to
// SHA-256 ze skrótu odbiorcy, skrótu nadawcy i payloadu; podpis obejmuje te same bajty i skrót.
// Stacja wysyła i przyjmuje tylko wiadomości SA1 (docs/spec/oprogramowanie.md, „Wiadomości SA1”):
// tytuł "SA1", treść UTF-8 JSON do 256 B, pola puste. Treść sprawdza warstwa SA1 stacji; szyfrowanie
// (token.h) i dowód po COMMIT robi wywołujący. Inne wiadomości LXMF, propagacja, DIRECT, łącza,
// znaczki pracy i bilety są poza rdzeniem.
#pragma once

#include "rnscore.h"

namespace rnscore {

constexpr size_t SA1_CONTENT_MAX = 256;
// Najdłuższe dane przyjmowane: tekst jawny tokenu z pakietu HEADER_1 o długości MTU (481 B danych,
// szyfrogram 400 B, dopełnienie co najmniej 1 B).
constexpr size_t LXMF_MAX_RECEIVED = 399;
// Skrót celu nadawcy na początku danych: po nim wywołujący szuka klucza nadawcy (Identity.recall).
constexpr size_t LXMF_SOURCE_OFFSET = 0;
// Najdłuższe dane własnej wiadomości: payload 0x94, float64 9 B, bin "SA1" 5 B, bin treści 3 + 256 B, 0x80.
constexpr size_t LXMF_SA1_MAX_DATA = TRUNCATED_HASH_SIZE + SIGNATURE_SIZE + 1 + 9 + 5 + 3 + SA1_CONTENT_MAX + 1;

// LXMF/LXMessage.py: LXMessage.pack z tytułem "SA1", pustymi polami i desired_method OPPORTUNISTIC,
// bez znaczka; dane pakietu to packed bez skrótu celu (LXMessage.__as_packet). privateKey i publicKey
// to tożsamość nadawcy, sourceHash jej cel "lxmf.delivery". Zwraca długość danych w out i skrót wiadomości
// w hash albo 0, gdy treść ma 0 albo ponad SA1_CONTENT_MAX B lub brak miejsca w out.
size_t lxmfPackSa1(const uint8_t privateKey[KEY_SIZE], const uint8_t publicKey[KEY_SIZE],
                   const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t sourceHash[TRUNCATED_HASH_SIZE],
                   double timestamp, const uint8_t* content, size_t contentLength, uint8_t* out, size_t capacity,
                   uint8_t hash[HASH_SIZE]);

// Przyjęta wiadomość SA1; wskaźniki do danych, które muszą żyć dłużej.
struct LxmfSa1 {
    const uint8_t* sourceHash;
    double timestamp;   // s od 1970-01-01 UTC według nadawcy
    const uint8_t* content;
    size_t contentLength;
    uint8_t hash[HASH_SIZE];   // message_id
};

// Powód odrzucenia wiadomości (diagnostyka stacji, bez odpowiednika w Pythonie): kształt (nie SA1 albo
// długość), znaczek pracy (payload 0x95, LXMessage z stamp), klucz nie należy do skrótu nadawcy, podpis.
enum class LxmfReject : uint8_t { NONE, SHAPE, STAMP, SOURCE, SIGNATURE };

// LXMF/LXMessage.py: LXMessage.unpack_from_bytes dla danych pakietu okazjonalnego (LXMRouter.delivery_packet
// dokleja skrót celu z pakietu), razem z weryfikacją podpisu, której wynik Python zapisuje w
// signature_validated. Prawda tylko dla wiadomości SA1 podpisanej kluczem senderPublicKey, którego cel
// "lxmf.delivery" jest skrótem nadawcy w danych; kształt jest sprawdzany przed kryptografią. Python
// przyjmuje więcej (tabela różnic w firmware/reticulum-core.md); niczego, co odrzuca Python, rdzeń nie przyjmuje.
// reason (opcjonalny): powód odrzucenia albo NONE.
bool lxmfReceiveSa1(const uint8_t destinationHash[TRUNCATED_HASH_SIZE], const uint8_t* data, size_t length,
                    const uint8_t senderPublicKey[KEY_SIZE], LxmfSa1& out, LxmfReject* reason = nullptr);

}  // namespace rnscore
