// SPDX-License-Identifier: MIT
// Węzeł Reticulum stacji (port microReticulum) z interfejsem P1 (docs/spec/radio.md, "Interfejs P1
// w stosie Reticulum"; oprogramowanie.md, "Podział oprogramowania" i "Pojemności stosu"):
// - transport włączony, jeden interfejs P1 nad łączem radiowym (Radio) z kolejką na 4 datagramy,
//   limitem ogłoszeń przekazywanych i kodem IFAC 16 B z konfiguracji (config.ifac);
// - jedna tożsamość stacji w rekordzie FRAM (framfs::loadKey), także jako tożsamość transportu;
//   znacznik w rekordzie formatu magazynu mówi, że tożsamość była zapisana: brak klucza przy znaczniku
//   to błąd pamięci, nie nowa tożsamość (Status::identityLost);
// - tożsamości odbiorcy (główna i zapasowa) z kluczy publicznych karty w konfiguracji (setReceivers):
//   wysyłka do celu "wici.sa1" odbiorcy nie czeka na jego ogłoszenie, a wpisy obu nie są usuwane
//   przy pełnych tablicach (łata microStore 0001);
// - tablica tras, znane tożsamości i buforowane ogłoszenia w systemie plików FRAM (framfs), po 256
//   wpisów; lista skrótów pakietów 4096 x 8 B w RAM (pkthash.h, łata 0002);
// - cel SINGLE "wici.sa1" stacji z dowodem pakietu po decyzji warstwy aplikacji (PROVE_APP):
//   pakiet okazjonalny do stacji wraca z potwierdzeniem transportowym; brak miejsca i błąd zapisu
//   nie dają dowodu. LXMF przyjdzie w następnym etapie (D14);
// - klasy ruchu K0–K2 kolejki P1 (p1iface.h): zapytania o trasę wysłane przez stację (Hint::OWN),
//   cel K1 = aktywna tożsamość odbiorcy;
// - cisza radiowa (setSilence): FULL odmawia stosowi każdego pakietu i opróżnia kolejkę; EXCEPTION
//   przepuszcza tylko wymianę jednego zgłoszenia (pakiet i zapytanie o trasę z send(), dowody pakietów
//   tego zgłoszenia), bez ogłoszeń i ruchu przekazywanego (oprogramowanie.md, "Tryby kryzysowe");
// - konfiguracja węzła stanowiska (stanowisko-osp.md, „Stacja stanowiska”): bez celu "wici.sa1"
//   i bez ogłoszeń własnych, z drugim interfejsem Reticulum przez USB do komputera stanowiska (ramki
//   KISS z kontrolą przepływu, kiss.h; radio.md, „Interfejs Reticulum przez USB”). Pakiet z USB
//   przechodzi do stosu, gdy kolejka P1 ma miejsce. Cele ogłoszone przez komputer są chronione
//   w pełnych tablicach, a pakiety z USB i do tych celów są w klasie K1 (Hint::RECEIVER).
// Nagłówek nie dołącza microReticulum (jego makra ERROR, INFO, DEBUG kolidują z kodem stacji).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "journal.h"
#include "kiss.h"

namespace rnsnode {

constexpr const char* APP_NAME = "wici";
constexpr const char* ASPECT = "sa1";
constexpr size_t HASH = 16;
constexpr uint32_t RECEIPT_MIN_S = 60;   // potwierdzenie transportowe: co najmniej 60 s (radio.md)

// Łącze P1 pod interfejsem: na stacji measure::Bench, na komputerze emulator.
struct Radio {
    virtual ~Radio() = default;
    virtual bool ready() = 0;                                      // odbiór P1 włączony, nic nie nadaje
    virtual bool transmit(const uint8_t* data, size_t length) = 0; // początek nadawania datagramu
    virtual uint32_t debtMs() = 0;                                  // pozostały dług ciszy
};

struct Hooks {
    // Pakiet do celu "wici.sa1" stacji (dane po odszyfrowaniu); true = rozstrzygnięty, stos wysyła
    // dowód. exception: pakiet dotyczy zgłoszenia z wyjątkiem ciszy (dowód wychodzi także w ciszy).
    bool (*packet)(const uint8_t* data, size_t length, bool& exception, void* context) = nullptr;
    // Wynik potwierdzenia transportowego pakietu wysłanego przez send().
    void (*receipt)(uint32_t handle, bool delivered, void* context) = nullptr;
    // Ogłoszenie celu "wici.sa1" innej stacji (cel, dane aplikacji).
    void (*announce)(const uint8_t destination[HASH], const uint8_t* appData, size_t length, void* context) = nullptr;
    void (*log)(const char* text, void* context) = nullptr;
    void* context = nullptr;
};

struct Status {
    bool started = false;
    bool online = false;            // IFAC skonfigurowany, interfejs przyjmuje pakiety
    bool identityNew = false;       // tożsamość utworzona przy tym starcie
    bool identityLost = false;      // znacznik zapisanej tożsamości bez klucza w FRAM: stos nie startuje
    size_t paths = 0;
    size_t packetHashes = 0;
    size_t announceTable = 0;
    size_t receiptsPending = 0;
    size_t poolSize = 0;            // pula TLSF stosu
    size_t poolUsed = 0;
    size_t poolPeak = 0;
    size_t fsFiles = 0;
    size_t fsUsedBytes = 0;
    size_t fsCapacityBytes = 0;
    uint32_t packetsSent = 0;
    uint32_t packetsReceived = 0;
    uint32_t packetsUnproven = 0;   // odrzucone przez warstwę aplikacji, bez dowodu
    uint32_t delivered = 0;
    uint32_t timedOut = 0;
    uint32_t announcesSeen = 0;
    uint32_t k2Dropped = 0;         // pakiety K2 odrzucone (ostatnie miejsce, pula 60%, 25% na cel)
    uint32_t queueWaitMs = 0;
    uint32_t announceWaitMs = 0;
    uint32_t bitrate = 0;
};

// Start stosu. ifac: 16 B z konfiguracji; same zera = interfejs bez kodu dostępu nie nadaje
// i odrzuca odbiór (stacja przed przygotowaniem). clockMs: czas pracy z dziennika FRAM, z którego
// stos liczy swój zegar monotoniczny także między restartami (oprogramowanie.md, "Czas").
// identitySaved: znacznik zapisanej tożsamości (store::Store::identitySaved); bez klucza w FRAM
// przy znaczniku stos nie startuje (identityLost), bez znacznika tworzy nową tożsamość (identityNew).
// seed: 32 B z generatora stacji (drbg.h) wmieszane w generator stosu przed utworzeniem tożsamości
// (bez tego klucz zależałby tylko od źródła sprzętowego, na ESP32-S3 słabego bez radia Wi-Fi).
bool begin(journal::Storage& fram, Radio& radio, const uint8_t ifac[16], uint64_t clockMs, bool identitySaved, const uint8_t seed[32],
           const Hooks& hooks);
void setIfac(const uint8_t ifac[16]);   // po configure
// Tożsamości odbiorcy z karty (klucze publiczne 64 B i cele "wici.sa1"; zera = brak), active 0 albo 1.
// Wywoływane przed begin() (porządkowanie tablic przy starcie nie usuwa ich wpisów) i po zmianie
// konfiguracji albo KLUCZ ZAPASOWY.
void setReceivers(const uint8_t keys[2][64], const uint8_t sa1[2][HASH], uint8_t active);
// Konfiguracja węzła stanowiska; wywoływane przed begin() (zmiana działa po restarcie stacji).
void setNode(bool on);
bool node();
enum class Silence : uint8_t { OFF, FULL, EXCEPTION };
void setSilence(Silence mode);
constexpr size_t USB_PINNED = 8;   // cele ogłoszone przez komputer stanowiska, chronione w tablicach

// Interfejs danych USB w konfiguracji węzła stanowiska (poza trybem przygotowania): port otwarty przez
// komputer, bajty od komputera i do niego (zapis tyle, ile przyjmie CDC: kiss::Port::output()).
void usbOpen(bool open);
void usbFeed(const uint8_t* data, size_t length, uint32_t nowMs);
const uint8_t* usbOutput(size_t& length);
void usbConsume(size_t length);
struct UsbStatus {
    bool enabled = false;          // węzeł stanowiska z interfejsem USB w stosie
    bool open = false;
    bool flowControl = false;
    size_t buffered = 0;           // pakiety od komputera czekające na stos
    size_t pinned = 0;             // chronione cele komputera
    kiss::Counters counters;
};
UsbStatus usbStatus();
bool usbPinned(const uint8_t destination[HASH]);
// Liczniki interfejsu USB jako pola JSON bez nawiasów (INFO, RNS).
size_t usbJson(char* out, size_t size);
void loop(uint32_t nowMs);
void received(const uint8_t* wire, size_t length);   // datagram złożony z ramek P1
void txDone(bool ok);                                // koniec nadawania datagramu z transmit()

// Ogłoszenie celu "wici.sa1"; true, gdy interfejs P1 przyjął pakiet (false: stos nie działa,
// brak IFAC albo pełna kolejka; ponowienie ustala rns_announce.h).
bool announce(const uint8_t* appData, size_t length);
// Pakiet okazjonalny do celu "wici.sa1" o skrócie destination z dowodem; zwraca uchwyt
// potwierdzenia albo 0, gdy cel nie jest znany (wysłane zapytanie o trasę) albo interfejs
// odmówił (pełna kolejka, brak IFAC). timeoutS: najkrótszy limit potwierdzenia; stos wydłuża go do
// max(RECEIPT_MIN_S, 2 x skoki x 13 x czas TX datagramu 600 B + dług ciszy + kolejka P1).
uint32_t send(const uint8_t destination[HASH], const uint8_t* data, size_t length, uint32_t timeoutS);
bool knows(const uint8_t destination[HASH]);   // tożsamość celu znana z ogłoszenia
bool hasPath(const uint8_t destination[HASH]);
void requestPath(const uint8_t destination[HASH]);
bool queueFull();
bool online();                                // stos działa i IFAC skonfigurowany (interfejs nadaje)
uint32_t queueWaitMs();                       // dług ciszy i kolejka radiowa (dla limitów czasu)

const uint8_t* address();                     // skrót celu "wici.sa1" stacji
const uint8_t* identityHash();
bool publicKey(uint8_t out[64]);              // klucz publiczny tożsamości stacji (karta `card`)
Status status();
// Liczniki interfejsu P1 jako pola JSON bez nawiasów (do wiersza diagnostyki).
size_t interfaceJson(char* out, size_t size);
// ZNISZCZ DANE: stos staje do restartu bez dalszych zapisów w FRAM (tożsamość i tablice kasuje
// store::Store::destroy); nowa tożsamość przy następnym starcie.
void halt();
// Zapis tablic w FRAM (przy restarcie programowym).
void persist();

#ifndef ARDUINO
// Próba ochrony wpisów odbiorcy: mniejszy limit tablicy tras i znanych tożsamości (domyślnie 256).
void debugTableMax(uint16_t n);
// Pomiar pamięci na komputerze: n losowych skrótów na liście skrótów pakietów (pełną tablicę
// tras wypełniają ogłoszenia z Reticulum w Pythonie, tools/rns_interop.py --fill).
uint32_t debugFillHashes(uint32_t n);
#endif

}  // namespace rnsnode
