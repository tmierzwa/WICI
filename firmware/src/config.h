// SPDX-License-Identifier: MIT
// Konfiguracja stacji z dokumentu `configure` (docs/spec/protokol-usb.md, "Transfery dzielone na
// części", tabela „Dokument configure”): rola (`stacja` albo `wezel`), lista adresów, karta odbiorcy
// z pełnymi kluczami publicznymi tożsamości głównej i zapasowej, liczba stacji, frazy, kod IFAC
// i profil radiowy. Dokument (do 7680 B) leży w kopii konfiguracji w FRAM (store.h) i jest czytany
// stamtąd kawałkami, więc nie potrzebuje bufora w RAM: najpierw wyznaczane są zakresy pól obiektu
// głównego, potem każde pole albo element listy (≤640 B) jest rozbierany osobno.
// Dokument kodowany jak wiersze protokołu (UTF-8, bez sekwencji ucieczki: teksty SA1 nie mają
// cudzysłowu ani ukośnika wstecznego), każdy tekst według reguł SA1 (sa1::checkText), pole nieznane
// albo złego typu, brak pola wymaganego i pole spoza roli dają odmowę z nazwą pola.
// Karta odbiorcy: adres LXMF musi być celem "lxmf.delivery" podanego klucza; stacja wysyła do celu
// "wici.sa1" tego klucza (zastępcza koperta do czasu LXMF, station.h).
// Bez zależności od Arduino; sprawdzany na komputerze.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace config {

constexpr size_t HASH = 16;
constexpr size_t KEY = 64;                 // klucz publiczny tożsamości Reticulum (X25519 + Ed25519)
constexpr size_t ADDRESSES = 8;
constexpr size_t ADDRESS_MAX = 64;
constexpr size_t PHRASES = 11;
constexpr size_t PHRASE_MAX = 96;
constexpr size_t LANGS = 3;                // PL (do SA1), UK, EN
constexpr size_t PROFILE_MAX = 15;
constexpr uint32_t DOC_MAX = 7680;
constexpr uint16_t STATIONS_MAX = 1000;
constexpr const char* LXMF_NAME = "lxmf.delivery";
constexpr const char* SA1_NAME = "wici.sa1";

enum class Role : uint8_t { STATION, NODE };
enum Identity : uint8_t { MAIN = 0, BACKUP = 1 };

struct Receiver {
    uint8_t lxmf[HASH] = {};
    uint8_t key[KEY] = {};
    uint8_t sa1[HASH] = {};                // cel "wici.sa1" z klucza
};

struct Config {
    uint32_t seq = 0;                      // config_seq; 0 = stacja bez konfiguracji
    Role role = Role::STATION;
    uint16_t stations = 0;
    uint8_t addressCount = 0;
    char addresses[ADDRESSES][ADDRESS_MAX + 1] = {};
    uint8_t phraseCount = 0;
    char phrases[PHRASES][LANGS][PHRASE_MAX + 1] = {};
    Receiver receivers[2];
    uint8_t ifac[HASH] = {};
    char profile[PROFILE_MAX + 1] = {};
};

// Dokument w FRAM (albo w RAM w próbach).
struct Source {
    virtual ~Source() = default;
    virtual bool read(uint32_t offset, char* out, size_t length) = 0;
};

// Kontrola i rozbiór dokumentu o długości size. Zwraca nullptr albo `detail` odmowy `invalid`
// (nazwa pola, "worst_request", "json", "memory" przy błędzie odczytu). profile: profil radiowy,
// który obsługuje układ radiowy stacji. worst: największe zgłoszenie z przycisków (B); seq w out
// zostaje 0 (ustawia go magazyn).
const char* parse(Source& source, uint32_t size, const char* profile, Config& out, size_t& worst);

}  // namespace config
