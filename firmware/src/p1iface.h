// SPDX-License-Identifier: MIT
// Interfejs P1 w stosie Reticulum (docs/spec/radio.md, "Interfejs P1 w stosie Reticulum" i
// "Dostęp do kanału"): część bez zależności od stosu i od Arduino, sprawdzana na komputerze.
//
// - Kolejka radiowa na 4 datagramy: pakiet od stosu jest przyjmowany tylko przy wolnym miejscu,
//   inaczej stos dostaje odmowę (zajętość), a odrzut trafia do liczników diagnostyki.
// - Kolejność: dowody i pakiety do celów PLAIN (zapytania o trasę) przed danymi, ogłoszenia na końcu.
// - Limit ogłoszeń przekazywanych (hops > 0): jak announce_cap w Reticulum, 2% przepływności
//   deklarowanej; ogłoszenie ponad limit czeka na liście 4 ogłoszeń (jedno na cel), potem odpada.
//   Ogłoszenia własne (hops = 0) i odpowiedzi na zapytania o trasę (kontekst PATH_RESPONSE)
//   nie podlegają limitowi, jak w implementacji referencyjnej (tam odpowiedź ma przypisany
//   interfejs, a limit dotyczy tylko ogłoszeń bez niego).
// - Rezerwa dla OSP (radio.md, punkt 6): dane przekazywane (hops > 0) do celu innego niż
//   przypięta OSP zajmują najwyżej 50% czasu kanału (TX i dług ciszy) w oknie 1 h i nie biorą
//   ostatniego wolnego miejsca w kolejce; ponad limit interfejs odmawia (stos odrzuca pakiet
//   przekazywany, nadawca ponawia). Ruch do OSP, dowody, zapytania o trasę i własne pakiety bez limitu.
//   W konfiguracji węzła OSP (setNodeReserve) stacja nie ma karty OSP: ruchem OSP są pakiety
//   z interfejsu USB i do celów osiągalnych przez niego, co wskazuje stos (argument osp w offer).
// - Deklarowana przepływność uwzględnia ramkowanie P1 i dług ciszy 12 x czas TX.
// - Kod dostępu IFAC 16 B: maskowanie i zdejmowanie maski jak Transport.handle_outgoing_ifac i
//   handle_ifac w Reticulum e40191b; podpis i HKDF liczy warstwa ze stosem (rns_node.cpp).
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "p1frame.h"

namespace p1iface {

constexpr size_t QUEUE = 4;                  // kolejka radiowa (specyfikacja)
constexpr size_t HW_MTU = 500;               // MTU Reticulum bez IFAC (radio.md, profil P1)
constexpr size_t IFAC_SIZE = 16;             // kod dostępu sieci w bajtach
constexpr size_t MAX_WIRE = HW_MTU + IFAC_SIZE;
constexpr size_t HELD_ANNOUNCES = 4;
constexpr uint32_t HELD_LIFE_MS = 3UL * 3600 * 1000;    // Reticulum.QUEUED_ANNOUNCE_LIFE (e40191b)
constexpr uint32_t ANNOUNCE_CAP_PERCENT = 2;
constexpr uint16_t SYMBOL_RATE = 4800;
constexpr uint8_t DEBT_FACTOR = 12;
constexpr uint32_t FRAME_OVERHEAD = 12;      // preambuła 8 B i słowo synchronizacji 4 B
constexpr uint32_t RAMP_MS = 3;              // narastanie i zaokrąglenie jak frameAirMs w measure.cpp
constexpr uint32_t RESERVE_WINDOW_MIN = 60;  // okno rezerwy dla OSP: 60 przedziałów po 1 min
constexpr uint32_t OTHER_SHARE_PERCENT = 50; // ruch przekazywany poza OSP: najwyżej 50% czasu kanału

// Czas nadawania datagramu P1 o długości length: ramki LEN|BODY|CRC z preambułą i słowem.
uint32_t airtimeMs(size_t length);
// Dług ciszy rezerwowany przez łącze za datagram (measure::Bench): 12 x czas TX ramki pełnej
// długości za każdy fragment.
uint32_t reservedDebtMs(size_t length);
// Przepływność deklarowana stosowi [bit/s]: datagram 600 B przez czas nadawania i długu ciszy.
uint32_t declaredBitrate();

enum class Kind : uint8_t { CONTROL, DATA, ANNOUNCE };
// Klasa pakietu z nagłówka Reticulum (bez IFAC): typ pakietu w bitach 0-1 bajtu 0, typ celu w 2-3.
Kind classify(const uint8_t* raw, size_t length);
// Skrót celu (16 B) z pakietu; nagłówek typu 2 ma przed nim identyfikator transportu.
const uint8_t* destination(const uint8_t* raw, size_t length);
// Ogłoszenie z kontekstem PATH_RESPONSE (bajt po skrócie celu).
bool pathResponse(const uint8_t* raw, size_t length);

enum class Admit : uint8_t { QUEUED, HELD, FULL, ANNOUNCE_LIMIT, TOO_LARGE, OSP_RESERVE };
const char* admitName(Admit admit);

struct Counters {
    uint32_t queued = 0;          // datagramy przyjęte do kolejki radiowej
    uint32_t full = 0;            // odmowy przy pełnej kolejce (zgłoszona zajętość)
    uint32_t tooLarge = 0;
    uint32_t announcesHeld = 0;
    uint32_t announcesDropped = 0; // ogłoszenia ponad limit przy pełnej liście oczekujących
    uint32_t announcesExpired = 0;
    uint32_t sent = 0;
    uint32_t sendFailed = 0;      // łącze odrzuciło datagram (cisza, odroczenia, dziennik)
    uint32_t received = 0;
    uint32_t ifacMissing = 0;     // pakiet bez flagi IFAC albo za krótki
    uint32_t ifacInvalid = 0;     // zły kod IFAC
    uint32_t offline = 0;         // pakiety odrzucone bez skonfigurowanego IFAC
    uint32_t reserved = 0;        // dane przekazywane poza OSP odrzucone przez rezerwę dla OSP
};

class Queue {
public:
    // Przyjęcie pakietu od stosu: wire to bajty po IFAC, kind i hops z pakietu przed IFAC
    // (hops = 0 także dla odpowiedzi na zapytanie o trasę: bez limitu ogłoszeń), dest to skrót
    // celu (deduplikacja ogłoszeń oczekujących).
    // osp: pakiet ruchu OSP wskazany przez stos (węzeł OSP), zwolniony z rezerwy.
    Admit offer(Kind kind, uint8_t hops, const uint8_t dest[16], const uint8_t* wire, size_t length, uint32_t nowMs,
                bool osp = false);
    // Ogłoszenia oczekujące przechodzą do kolejki, gdy limit pozwala i jest miejsce.
    void poll(uint32_t nowMs);
    // Skrót celu przypiętej (aktywnej) OSP; same zera albo nullptr = brak rezerwy.
    void setOsp(const uint8_t dest[16]);
    // Węzeł OSP: rezerwa bez przypiętego celu; ruch OSP wskazuje argument osp w offer().
    void setNodeReserve(bool on) { nodeReserve_ = on; }
    uint32_t otherUsedMs(uint32_t nowMs);   // czas kanału ruchu poza OSP w bieżącym oknie
    // Następny datagram do nadania (najwyższa klasa, najstarszy); false, gdy kolejka pusta albo
    // trwa nadawanie. Wybrany datagram zostaje w kolejce do finish(): pakiet przyjęty w trakcie
    // nadawania nie może go wyprzedzić ani zastąpić.
    bool start(const uint8_t*& data, size_t& length);
    void finish(bool sent);
    bool transmitting() const { return current_ >= 0; }
    size_t queued() const { return count_; }
    size_t held() const;
    bool full() const { return count_ >= QUEUE; }
    // Przewidywany czas do opuszczenia kolejki przez nowy datagram: dług ciszy oraz czas nadawania
    // i rezerwacja długu (reservedDebtMs) datagramów w kolejce.
    uint32_t waitMs(uint32_t debtMs) const;
    uint32_t announceAllowedInMs(uint32_t nowMs) const;
    const Counters& counters() const { return counters_; }
    Counters& counters() { return counters_; }

private:
    struct Slot {
        bool used = false;
        Kind kind = Kind::DATA;
        uint32_t order = 0;
        uint16_t length = 0;
        uint8_t data[MAX_WIRE] = {};
    };
    struct Held {
        bool used = false;
        uint8_t hops = 0;
        uint8_t dest[16] = {};
        uint32_t sinceMs = 0;
        uint32_t costMs = 0;
        uint16_t length = 0;
        uint8_t data[MAX_WIRE] = {};
    };
    bool push(Kind kind, const uint8_t* wire, size_t length);
    int head() const;
    uint32_t costMs(size_t length) const;   // czas TX przy przepływności deklarowanej

    Slot slots_[QUEUE];
    Held held_[HELD_ANNOUNCES];
    size_t count_ = 0;
    int current_ = -1;            // slot w nadawaniu
    uint32_t order_ = 0;
    uint32_t announceAllowedAt_ = 0;
    bool announceGate_ = false;   // announceAllowedAt_ ustawione
    // Limit ogłoszeń minął: zamyka porównanie, które po 2^31 ms bez ogłoszeń zmieniłoby znak.
    bool announceOpen(uint32_t nowMs);
    void advanceWindow(uint32_t nowMs);
    uint8_t osp_[16] = {};
    bool ospSet_ = false;
    bool nodeReserve_ = false;
    uint32_t window_[RESERVE_WINDOW_MIN] = {};   // czas kanału ruchu poza OSP na minutę
    uint32_t windowMinute_ = 0;
    Counters counters_;
};

// IFAC: wire = [b0 | 0x80, b1] + tag + raw[2:], wszystko poza tagiem XOR z maską (length + tagLength B).
void ifacMask(const uint8_t* raw, size_t length, const uint8_t* tag, size_t tagLength, const uint8_t* mask, uint8_t* wire);
// Flaga IFAC i długość pozwalają zdjąć kod o rozmiarze tagLength.
bool ifacPresent(const uint8_t* wire, size_t length, size_t tagLength);
// Zdejmuje maskę (length B maski) i tag: raw ma length - tagLength B, flaga IFAC skasowana.
void ifacUnmask(const uint8_t* wire, size_t length, size_t tagLength, const uint8_t* mask, uint8_t* raw);

}  // namespace p1iface
