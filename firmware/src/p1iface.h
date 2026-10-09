// SPDX-License-Identifier: MIT
// Interfejs P1 w stosie Reticulum (docs/spec/radio.md, "Interfejs P1 w stosie Reticulum" i
// "Dostęp do kanału"): część bez zależności od stosu i od Arduino, sprawdzana na komputerze.
//
// - Kolejka radiowa na 4 datagramy: pakiet od stosu jest przyjmowany tylko przy wolnym miejscu,
//   inaczej stos dostaje odmowę (zajętość), a odrzut trafia do liczników diagnostyki.
// - Czas kanału (radio.md, "Dostęp do kanału", punkt 6): czas nadawania wraz z długiem ciszy,
//   13t na serię (t = zarezerwowany czas TX, dług 12t według punktu 2), liczony w przesuwnym oknie
//   3600 s z przedziałami po 1 min i naliczany przy przyjęciu do kolejki.
// - Klasy ruchu (punkt 6):
//   K0: własne pakiety stacji (hops = 0), dowody, zapytania o trasę i odpowiedzi na nie (ogłoszenie
//       z kontekstem PATH_RESPONSE); przekazywane zapytania o trasę: najwyżej 1 na cel na 60 s
//       i łącznie ≤5% czasu kanału, ponad limit odrzucane i liczone; zapytania wysłane na polecenie
//       stacji stos wskazuje (Hint::OWN), bo nagłówek ich nie odróżnia (Reticulum nadaje przekazywane
//       zapytanie od nowa z hops = 0).
//   K1: dane przekazywane (hops > 0) do aktywnej tożsamości odbiorcy z karty (setReceiver);
//       w konfiguracji węzła stanowiska pakiety z interfejsu USB i do celów osiągalnych przez niego,
//       co wskazuje stos (Hint::RECEIVER).
//   K2: pozostałe dane przekazywane. K2 razem z ogłoszeniami najwyżej 60% czasu kanału; K2 ponad
//       pulę odrzucany przed kolejką i liczony, bez ostatniego wolnego miejsca w kolejce. Jeden cel
//       w K2 najwyżej 25% czasu kanału, ale tylko gdy w kolejce czeka pakiet K0 lub K1.
// - Ogłoszenia (własne i przekazywane, poza odpowiedziami na zapytania o trasę): limit 2% czasu
//   zegarowego liczony z czasu nadawania (oprogramowanie.md, "Tryby kryzysowe", "Ogłoszenia
//   adresu"), czas kanału we wspólnej puli z K2. Ogłoszenie ponad limit albo ponad pulę czeka na
//   liście 4 ogłoszeń (nowsze ogłoszenie tego samego celu zastępuje starsze; przy pełnej liście
//   ogłoszenie z mniejszą liczbą skoków zastępuje to z największą), po 3 h odpada.
// - Kolejność nadawania: dowody, zapytania o trasę i odpowiedzi na nie, potem dane K0 i K1, potem
//   dane K2, na końcu ogłoszenia (oprogramowanie.md, "Wysyłanie"); w obrębie klasy od najstarszego.
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
constexpr uint16_t SYMBOL_RATE = 4800;
constexpr uint8_t DEBT_FACTOR = 12;          // dług ciszy = 12 x zarezerwowany czas TX (radio.md, punkt 2)
constexpr uint32_t FRAME_OVERHEAD = 12;      // preambuła 8 B i słowo synchronizacji 4 B
constexpr uint32_t RAMP_MS = 3;              // narastanie i zaokrąglenie jak frameAirMs w measure.cpp
constexpr uint32_t WINDOW_MIN = 60;          // okno czasu kanału: 60 przedziałów po 1 min
constexpr uint32_t WINDOW_MS = WINDOW_MIN * 60000;
constexpr uint32_t POOL_PERCENT = 60;        // K2 i ogłoszenia razem
constexpr uint32_t DEST_PERCENT = 25;        // jeden cel w K2 przy rywalizacji z K0 i K1
constexpr uint32_t PATH_REQUEST_PERCENT = 5; // przekazywane zapytania o trasę
constexpr uint32_t PATH_REQUEST_GAP_MS = 60000;   // przekazywane zapytanie o ten sam cel
constexpr uint32_t ANNOUNCE_CAP_PERCENT = 2; // ogłoszenia: czas TX wobec czasu zegarowego
constexpr size_t DEST_TRACK = 4;             // cele K2 z własnym oknem (najmniej używany wypada)
constexpr size_t PATH_REQUEST_TRACK = 8;     // cele ostatnich przekazywanych zapytań o trasę

// Czas nadawania datagramu P1 o długości length: ramki LEN|BODY|CRC z preambułą i słowem.
uint32_t airtimeMs(size_t length);
// Czas TX rezerwowany przez łącze (measure::Bench): ramka pełnej długości za każdy fragment.
uint32_t reservedTxMs(size_t length);
// Dług ciszy rezerwowany przez łącze za datagram: 12 x reservedTxMs.
uint32_t reservedDebtMs(size_t length);
// Czas kanału datagramu: 13t, t = reservedTxMs (radio.md, "Dostęp do kanału", punkt 6).
uint32_t channelMs(size_t length);
// Przepływność deklarowana stosowi [bit/s]: datagram 600 B przez czas nadawania i długu ciszy.
uint32_t declaredBitrate();

enum class Kind : uint8_t { CONTROL, DATA, ANNOUNCE };
// Rodzaj pakietu z nagłówka Reticulum (bez IFAC): typ pakietu w bitach 0-1 bajtu 0, typ celu w 2-3.
// CONTROL: dowód albo dane do celu PLAIN (zapytanie o trasę).
Kind classify(const uint8_t* raw, size_t length);
// Skrót celu (16 B) z pakietu; nagłówek typu 2 ma przed nim identyfikator transportu.
const uint8_t* destination(const uint8_t* raw, size_t length);
// Ogłoszenie z kontekstem PATH_RESPONSE (bajt po skrócie celu).
bool pathResponse(const uint8_t* raw, size_t length);
// Zapytanie o trasę (dane do celu PLAIN): skrót szukanego celu, pierwsze 16 B danych po kontekście.
const uint8_t* pathRequestTarget(const uint8_t* raw, size_t length);

// Wskazanie stosu dla pakietu, którego klasy nie da się ustalić z nagłówka.
enum class Hint : uint8_t {
    NONE,       // klasa z nagłówka i celu
    OWN,        // pakiet własny stacji, np. zapytanie o trasę na polecenie aplikacji (K0 bez limitu)
    RECEIVER,   // węzeł stanowiska: pakiet z interfejsu USB albo do celu osiągalnego przez USB (K1)
};
// Klasa pakietu w kolejce; kolejność nadawania: CONTROL, K0 i K1 razem, K2, ANNOUNCE.
// CONTROL to K0 poza danymi: dowody, zapytania o trasę, odpowiedzi na nie.
enum class Lane : uint8_t { CONTROL, K0, K1, K2, ANNOUNCE };
const char* laneName(Lane lane);

enum class Admit : uint8_t { QUEUED, HELD, FULL, ANNOUNCE_LIMIT, TOO_LARGE, K2_SLOT, K2_POOL, K2_DEST, PATH_REQUEST_LIMIT };
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
    uint32_t k2Slot = 0;          // K2 odrzucony: ostatnie wolne miejsce w kolejce
    uint32_t k2Pool = 0;          // K2 odrzucony: pula 60% (K2 i ogłoszenia) wyczerpana
    uint32_t k2Dest = 0;          // K2 odrzucony: 25% na cel przy czekającym K0 lub K1
    uint32_t pathRequestLimited = 0;   // przekazywane zapytania o trasę ponad 1/cel/60 s albo 5%
    uint32_t silenced = 0;        // pakiety wstrzymane ciszą radiową (odmowa stosowi albo usunięte z kolejki)
};

class Queue {
public:
    // Przyjęcie pakietu od stosu: raw to pakiet Reticulum bez IFAC (klasa, skoki, cel), wire to
    // bajty do nadania (z IFAC). hint: wskazanie stosu (Hint).
    Admit offer(const uint8_t* raw, size_t rawLength, const uint8_t* wire, size_t wireLength, uint32_t nowMs,
                Hint hint = Hint::NONE);
    // Klasa pakietu według reguł wyżej (bez stanu kolejki).
    Lane lane(const uint8_t* raw, size_t length, Hint hint = Hint::NONE) const;
    // Ogłoszenia oczekujące przechodzą do kolejki, gdy limit 2%, pula i miejsce pozwalają.
    void poll(uint32_t nowMs);
    // Bramka ogłoszeń gaśnie po swoim czasie także w ciszy (poll() wtedy nie działa): inaczej po
    // ciszy dłuższej niż 2^31 ms różnica czasu znowu wyszłaby dodatnia i trzymała ogłoszenia.
    void tick(uint32_t nowMs) { announceOpen(nowMs); }
    // Aktywna tożsamość odbiorcy z karty (cel K1); same zera albo nullptr = brak.
    void setReceiver(const uint8_t dest[16]);
    uint32_t poolUsedMs(uint32_t nowMs);          // czas kanału K2 i ogłoszeń w bieżącym oknie
    uint32_t pathRequestUsedMs(uint32_t nowMs);   // czas kanału przekazywanych zapytań o trasę
    uint32_t destUsedMs(const uint8_t dest[16], uint32_t nowMs);   // czas kanału jednego celu K2
    // Następny datagram do nadania (najwyższa klasa, najstarszy); false, gdy kolejka pusta albo
    // trwa nadawanie. Wybrany datagram zostaje w kolejce do finish(): pakiet przyjęty w trakcie
    // nadawania nie może go wyprzedzić ani zastąpić.
    bool start(const uint8_t*& data, size_t& length);
    void finish(bool sent);
    // Cisza radiowa: datagramy czekające w kolejce odpadają (liczone jako silenced); nadawany zostaje
    // do finish(), ogłoszenia oczekujące zostają na liście.
    void drop();
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
    // Czas kanału w przesuwnym oknie: przedziały po 1 min.
    struct Window {
        uint32_t ms[WINDOW_MIN] = {};
        uint32_t minute = 0;
        void advance(uint32_t nowMs);
        uint32_t used(uint32_t nowMs);
        void add(uint32_t nowMs, uint32_t cost);
    };
    struct DestWindow {
        bool used = false;
        uint8_t dest[16] = {};
        Window window;
    };
    struct PathRequest {
        bool used = false;
        uint8_t target[16] = {};
        uint32_t atMs = 0;
    };
    struct Slot {
        bool used = false;
        Lane lane = Lane::K0;
        uint32_t order = 0;
        uint16_t length = 0;
        uint8_t data[MAX_WIRE] = {};
    };
    struct Held {
        bool used = false;
        uint8_t hops = 0;
        uint8_t dest[16] = {};
        uint32_t sinceMs = 0;
        uint16_t length = 0;
        uint8_t data[MAX_WIRE] = {};
    };
    bool push(Lane lane, const uint8_t* wire, size_t length);
    int head() const;
    bool k0k1Waiting() const;
    bool poolAllows(uint32_t nowMs, size_t length);
    void releaseAnnounce(const uint8_t* wire, size_t length, uint32_t nowMs);
    Admit offerAnnounce(uint8_t hops, const uint8_t* dest, const uint8_t* wire, size_t length, uint32_t nowMs);
    Admit offerPathRequest(const uint8_t* target, const uint8_t* wire, size_t length, uint32_t nowMs);
    Admit offerK2(const uint8_t* dest, const uint8_t* wire, size_t length, uint32_t nowMs);
    DestWindow* findDest(const uint8_t* dest);
    // Limit ogłoszeń minął: zamyka porównanie, które po 2^31 ms bez ogłoszeń zmieniłoby znak.
    bool announceOpen(uint32_t nowMs);

    Slot slots_[QUEUE];
    Held held_[HELD_ANNOUNCES];
    size_t count_ = 0;
    int current_ = -1;            // slot w nadawaniu
    uint32_t order_ = 0;
    uint32_t announceAllowedAt_ = 0;
    bool announceGate_ = false;   // announceAllowedAt_ ustawione
    uint8_t receiver_[16] = {};
    bool receiverSet_ = false;
    Window pool_;                 // K2 i ogłoszenia
    Window pathRequests_;         // przekazywane zapytania o trasę
    DestWindow dests_[DEST_TRACK];
    PathRequest recentRequests_[PATH_REQUEST_TRACK];
    Counters counters_;
};

// IFAC: wire = [b0 | 0x80, b1] + tag + raw[2:], wszystko poza tagiem XOR z maską (length + tagLength B).
void ifacMask(const uint8_t* raw, size_t length, const uint8_t* tag, size_t tagLength, const uint8_t* mask, uint8_t* wire);
// Flaga IFAC i długość pozwalają zdjąć kod o rozmiarze tagLength.
bool ifacPresent(const uint8_t* wire, size_t length, size_t tagLength);
// Zdejmuje maskę (length B maski) i tag: raw ma length - tagLength B, flaga IFAC skasowana.
void ifacUnmask(const uint8_t* wire, size_t length, size_t tagLength, const uint8_t* mask, uint8_t* raw);

}  // namespace p1iface
