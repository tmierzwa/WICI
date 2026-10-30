// SPDX-License-Identifier: MIT
// Węzeł Reticulum stacji na rdzeniu (firmware/reticulum-core.md): ten sam interfejs rns_node.h co
// port, w obrazach stacji z rdzeniem i w programie na komputerze (env:host). Działa:
// - tożsamość: ten sam rekord klucza w FRAM co w porcie (framfs::loadKey, 64 B w kolejności Reticulum),
//   więc stacja zachowuje tożsamość i adres przy przejściu z portu na rdzeń (decyzja z 2026-10-22);
// - interfejs P1 (etap R1): kod dostępu IFAC 16 B z rdzenia (rnscore::ifacApply, ifacCheck) z frazą
//   jak w porcie (32 cyfry szesnastkowe klucza z konfiguracji), kolejka radiowa, klasy ruchu i limit
//   ogłoszeń z p1iface, cisza radiowa jak w porcie, liczniki interfejsu w tym samym JSON;
// - transport (rnscore::Transport): ogłoszenie własne celu "lxmf.delivery" (od R3) bez ratchetu
//   (własne ratchety stacji są poza rdzeniem), ogłoszenia innych celów z polem ratchetu w tablicy
//   znanych celów i tras (256 wpisów, odbiorca z karty chroniony), pakiety do stacji z dowodem po
//   decyzji warstwy aplikacji, pakiet okazjonalny z szyfrowaniem do ratchetu i potwierdzeniem;
// - tablica znanych celów i tras w FRAM (rnscore::Table, etap R2): 257 gniazd po 568 B od adresu
//   systemu plików portu (framfs::FS_BASE; rdzeń i port nie dzielą tego obszaru, ten sam rekord
//   tożsamości), w RAM indeks 257 × 24 B; zapis gniazda przy każdej zmianie wpisu, bez zapisu przy
//   powtórzonym ogłoszeniu;
// - LXMF (etap R3): cel stacji "lxmf.delivery" zamiast "wici.sa1" z portu, ogłoszenie z danymi
//   aplikacji jak LXMRouter (nazwa WICI-xxxxxx), wiadomość SA1 w jednym pakiecie okazjonalnym
//   (rnscore::lxmfPackSa1, lxmfReceiveSa1). Warstwa aplikacji (station.h) jest wspólna z portem
//   i nadal podaje zastępczą kopertę ["WICI",1,od,do,<SA1>] i cele "wici.sa1" odbiorcy z karty:
//   send() wyjmuje SA1 z koperty i wysyła je w LXMF do celu "lxmf.delivery" tego samego klucza,
//   a wiadomość odbiorcy z karty z poprawnym podpisem idzie do warstwy aplikacji w takiej kopercie
//   (od = cel tego odbiorcy z setReceivers). Dowód po decyzji warstwy aplikacji (COMMIT albo trwałe
//   odrzucenie); inne dane (nadawca spoza karty, nie SA1, znaczek pracy, zły podpis) to trwałe
//   odrzucenie z dowodem i licznikiem powodu (oprogramowanie.md, „Dowód dostarczenia po COMMIT”).
//   Znacznik czasu własnej wiadomości to licznik pracy w s (oprogramowanie.md, „Czas”): zwykły
//   klient LXMF pokaże datę z 1970 roku;
// - praca na pakiet ograniczona dla płytek (audyt rdzenia, U2): received() tylko odkłada datagram do
//   kolejki odbioru, a jeden obieg rnsnode::loop() wykonuje najwyżej jeden krok odbioru: sprawdzenie
//   IFAC (podpis) albo przetworzenie pakietu w transporcie; weryfikacja podpisów ogłoszeń z limitem na
//   sekundę. Wyjątek: pakiet do stacji z dowodem to w jednym obiegu ECDH, weryfikacja podpisu LXMF,
//   podpis dowodu i IFAC dowodu. Poza loop() kryptografię robią wywołania warstwy aplikacji: announce()
//   (podpis ogłoszenia i IFAC) i send() (podpis LXMF, ECDH i IFAC);
// - czas: licznik pracy (clockMs z begin() i zegar ms stosu); losowość z HMAC-DRBG stacji z ziarnem
//   z begin().
// - zapytania o trasę (etap R2): odpowiedzi dla celu stacji i celów z trasą (tablica retransmisji
//   ogłoszeń 16 wpisów), własne zapytania z requestPath(), sendReady() i send() przy nieznanym celu
//   (najwyżej jedno na cel na 20 s), w kolejce P1 jako ruch własny (Hint::OWN); kolejne zapytanie o cel
//   bez odpowiedzi czeka na jego ogłoszenie jak w Pythonie (inflight_path_requests);
// - przekazywanie (etap R2): pakiety HEADER_2 ze stacją jako następnym skokiem według tablicy tras,
//   dowody według tablicy odwrotnej (32 wpisy), retransmisja przyjętych ogłoszeń; klasę w kolejce P1
//   (K1, K2, ogłoszenia) ustala p1iface z nagłówka, jak dla portu.
// - interfejs USB węzła stanowiska (etap R4b, radio.md, „Interfejs Reticulum przez USB”): interfejs 1
//   transportu, tylko w konfiguracji węzła (setNode), ramki KISS z kontrolą przepływu (kiss::Port, bufor
//   około 5 KB przydzielany w begin(), bez sterty później), bez IFAC. Pakiet od komputera wchodzi do
//   transportu krokiem odbioru na zmianę z P1 (jeden krok na obieg loop()), gdy kolejka P1 ma miejsce.
//   Weryfikacja podpisów ogłoszeń z USB ma osobne wiadro żetonów (seria USB_PINNED). Do USB_PINNED celów
//   z trasą przez USB (cele komputera) jest chronionych w pełnej tablicy i w klasie K1 kolejki P1; po
//   restarcie wracają z indeksu tablicy (trasy przez interfejs 1, rnscore::Transport::routes).
#include <stdio.h>
#include <string.h>

#include <new>

#ifdef ARDUINO
#include <Arduino.h>
#else
#include <chrono>
#endif

#include <Crypto.h>

#include "announce.h"
#include "destination.h"
#include "drbg.h"
#include "framfs.h"
#include "identity.h"
#include "ifac.h"
#include "lxmf.h"
#include "p1frame.h"
#include "p1iface.h"
#include "packet.h"
#include "rns_node.h"
#include "rns_usb.h"
#include "transport.h"

namespace rnsnode {

namespace {

#ifndef ARDUINO
uint64_t (*hostClock)() = nullptr;   // zegar symulowany prób na komputerze (debugClock)
#endif

// Zegar ms stosu, ten sam co w porcie (rns_node.cpp).
uint32_t nowMs() {
#ifdef ARDUINO
    return millis();
#else
    if (hostClock) return static_cast<uint32_t>(hostClock());
    using namespace std::chrono;
    return static_cast<uint32_t>(duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count());
#endif
}

bool started = false;
bool halted = false;   // po halt() begin() odmawia do restartu (audyt rdzenia, U10)
bool identityNew = false;
bool identityLost = false;
bool nodeMode = false;
Hooks hooks;
Radio* radio = nullptr;
uint8_t privateKey[rnscore::KEY_SIZE];
uint8_t publicKeyBytes[rnscore::KEY_SIZE];
uint8_t identityBytes[HASH];
uint8_t addressBytes[HASH];
uint8_t nameHashBytes[rnscore::NAME_HASH_SIZE];
drbg::Drbg generator;   // skróty losowe ogłoszeń, klucze efemeryczne i IV tokenów

// Licznik pracy w ms: clockMs z begin() (czas pracy z dziennika FRAM) i przyrosty zegara stosu.
uint64_t clockMs = 0;
uint32_t clockLastMs = 0;

uint64_t uptimeMs() {
    const uint32_t now = nowMs();
    clockMs += static_cast<uint32_t>(now - clockLastMs);
    clockLastMs = now;
    return clockMs;
}

// Interfejs P1.
p1iface::Queue queue;
rnscore::Ifac ifac;
bool ifacOnline = false;
uint8_t pinned[2][HASH] = {};   // cele "lxmf.delivery" odbiorcy z karty (główny, zapasowy)
uint8_t receiverKeys[2][rnscore::KEY_SIZE] = {};
uint8_t receiverApp[2][HASH] = {};   // cele odbiorcy w warstwie aplikacji (setReceivers: "wici.sa1")
uint8_t receiverActive = 0;
// Cisza radiowa i znacznik ruchu dopuszczonego wyjątkiem (pakiet z send(), dowód pakietu zgłoszenia).
Silence silence = Silence::OFF;
bool exceptionOut = false;
bool ownRequest = false;   // zapytanie o trasę na polecenie stacji (Hint::OWN)
uint32_t malformed = 0;   // pakiety z poprawnym IFAC, które odrzuca rnscore::unpack
rnscore::Transport transport;
// Budżet RAM obiektu transportu (reticulum-core.md, „Budżet RAM”: 56 KiB z LXMF); na płytce sprawdza go
// też tools/core_boards.py kompilatorem obrazu.
static_assert(sizeof(rnscore::Transport) <= 56 * 1024, "rnscore::Transport ponad budżet RAM");
uint32_t nextHandle = 0;

// Kolejka odbioru: datagramy z eteru czekają na loop(). Na nRF52840 sprawdzenie IFAC (podpis Ed25519)
// trwa około 0,26 s, a weryfikacja podpisu ogłoszenia około 0,4 s (szacunek z audytu rdzenia), więc
// jeden obieg pętli stacji robi najwyżej jedną z tych operacji. Pełna kolejka: nowy datagram odpada.
constexpr size_t RX_SLOTS = 4;   // do pomiaru na płytce
struct RxSlot {
    uint16_t length;
    bool checked;                         // IFAC sprawdzony, w bytes pakiet bez IFAC
    uint8_t bytes[p1iface::MAX_WIRE];
};
RxSlot rx[RX_SLOTS];
size_t rxHead = 0, rxCount = 0;
uint32_t rxDropped = 0;   // datagramy odrzucone przy pełnej kolejce odbioru

// Wiadro żetonów: żeton co period ms, najwyżej burst naraz.
struct TokenBucket {
    uint32_t period;
    uint32_t burst;
    uint32_t tokens;
    uint64_t refillMs;
    void reset(uint64_t now) {
        tokens = burst;
        refillMs = now;
    }
    bool take(uint64_t now) {
        const uint64_t periods = (now - refillMs) / period;
        if (periods) {
            refillMs += periods * period;
            tokens = periods >= burst - tokens ? burst : tokens + static_cast<uint32_t>(periods);
        }
        if (!tokens) return false;
        --tokens;
        return true;
    }
};

// Limit weryfikacji podpisów ogłoszeń: wiadro żetonów na interfejs, żeton co sekundę,
// najwyżej burst naraz. Ogłoszenie bez żetonu odpada przed kryptografią (bez skrótu na liście, więc
// powtórka przejdzie). Python ogranicza napływ ogłoszeń inaczej (RNS/Interfaces/Interface.py:
// should_ingress_limit i hold_announce: tylko nieznane cele, po weryfikacji podpisu, ogłoszenia
// wstrzymane i wypuszczane później); tabela różnic w firmware/reticulum-core.md. USB ma osobne wiadro:
// zalew z dołączonego laptopa (także zawirusowanego) nie zajmuje weryfikacją wszystkich kroków USB,
// a ogłoszenia z P1 nie czekają na żetony USB.
// USB: seria pokrywa ogłoszenia komputera przy jego starcie (lxmf.delivery i kilka innych celów), więc
// żaden nie czeka na następne ogłoszenie; liczba niezależna od USB_PINNED. Do pomiaru na płytce.
constexpr uint32_t USB_VERIFY_BURST = 8;
TokenBucket verifyBuckets[rnscore::INTERFACES_MAX] = {
    {1000, 3, 0, 0},                  // P1, do pomiaru na płytce
    {1000, USB_VERIFY_BURST, 0, 0},   // USB
};
uint32_t announcesLimited[rnscore::INTERFACES_MAX] = {};   // ogłoszenia odrzucone bez żetonu, P1 i USB

// Limit pracy nad pakietami do celu stacji: żeton co sekundę, najwyżej 4 naraz; jeden żeton na pakiet
// (odszyfrowanie z ECDH, weryfikacja podpisu LXMF w packetHook, podpis dowodu i IFAC dowodu). Pakiet bez
// żetonu odpada przed odszyfrowaniem i bez dowodu, jak utracony; Python odszyfrowuje każdy (tabela różnic).
// Osobno od wiadra ogłoszeń: zalew ogłoszeń nie zabiera żetonów pakietom do stacji.
TokenBucket receiveBucket = {1000, 4, 0, 0};   // do pomiaru na płytce

// Węzeł stanowiska: interfejs USB (interfejs 1 transportu). Bufor KISS tylko w tej konfiguracji (stacja
// w schronieniu nie płaci za niego pamięcią), przydzielany raz w begin().
constexpr uint8_t IFACE_P1 = 0, IFACE_USB = 1;
kiss::Port* usbPort = nullptr;
usb::Destinations usbDests;   // cele komputera (trasa przez USB)
bool fromUsb = false;         // transport przetwarza pakiet z USB (pakiety na P1 w klasie K1)
bool usbNext = false;         // przeplot kroków odbioru: następny krok najpierw z USB
// Praca asymetryczna w obiegu loop() zgłaszana przez haki (żeton weryfikacji ogłoszenia albo pakietu do
// stacji, podpis IFAC pakietu na P1): po kroku USB poll() nadaje tylko w obiegu bez niej, więc tanie
// pakiety z USB (nieznany cel, duplikat, ogłoszenie albo pakiet bez żetonu) nie wstrzymują retransmisji.
bool asymmetricWork = false;
// Pakiety z USB odrzucone przed transportem albo przez niego (osobno od P1).
struct UsbRejects {
    uint32_t ifacFlag = 0;    // flaga IFAC na interfejsie bez IFAC (Python: Transport.inbound odrzuca)
    uint32_t malformed = 0;   // rnscore::unpack odrzuca
    uint32_t invalid = 0;     // transport: ogłoszenie odrzucone, pakiet nie do odszyfrowania itp.
};
UsbRejects usbRejects;
uint32_t usbK1 = 0;           // pakiety na P1 w klasie K1 z reguły węzła stanowiska (od komputera albo do niego)

// Cel komputera: na liście i z trasą nadal przez USB (trasa przeniesiona na P1 zdejmuje ochronę i K1).
bool computerDestination(const uint8_t* dest) {
    return dest && usbDests.known(dest) && transport.pathInterface(dest) == IFACE_USB;
}

void rxDrop() {
    rxHead = (rxHead + 1) % RX_SLOTS;
    --rxCount;
}

// Obszar tablicy znanych celów w FRAM: miejsce systemu plików portu (framfs.h). Stacja ma albo port,
// albo rdzeń; przy zmianie stosu drugi widzi obszar jako nowy (port formatuje system plików, rdzeń
// pomija gniazda bez znacznika i CRC), a tożsamość w osobnym rekordzie zostaje.
constexpr uint32_t TABLE_BASE = framfs::FS_BASE;
static_assert(rnscore::TABLE_AREA <= framfs::FS_SIZE, "tablica znanych celów w obszarze stosu");

struct FramTable : rnscore::TableStorage {
    journal::Storage* fram = nullptr;
    bool read(uint32_t offset, uint8_t* data, size_t count) override {
        return fram && offset + count <= rnscore::TABLE_AREA && fram->read(TABLE_BASE + offset, data, count);
    }
    bool write(uint32_t offset, const uint8_t* data, size_t count) override {
        return fram && offset + count <= rnscore::TABLE_AREA && fram->write(TABLE_BASE + offset, data, count);
    }
};
FramTable framTable;

void log(const char* text) {
    if (hooks.log) hooks.log(text, hooks.context);
}

// Cel stacji (etap R3, docs/spec/oprogramowanie.md): "lxmf.delivery" jak LXMRouter.register_delivery_identity.
constexpr const char* LXMF_DELIVERY = "lxmf.delivery";

// Zastępcza koperta warstwy aplikacji (station.cpp, Station::transmit): ["WICI",1,"<od>","<do>",<SA1>],
// od i do po 32 cyfry szesnastkowe, więc SA1 zaczyna się zawsze od tego samego miejsca.
constexpr char ENVELOPE_HEAD[] = "[\"WICI\",1,\"";
constexpr size_t ENVELOPE_FROM = sizeof(ENVELOPE_HEAD) - 1;
constexpr size_t ENVELOPE_TO = ENVELOPE_FROM + 2 * HASH + 3;   // po "," między adresami
constexpr size_t ENVELOPE_SA1 = ENVELOPE_TO + 2 * HASH + 2;    // po ", przed SA1
uint8_t lxmfOut[rnscore::LXMF_SA1_MAX_DATA];                       // dane pakietu wiadomości z send()
char envelope[ENVELOPE_SA1 + rnscore::SA1_CONTENT_MAX + 2];       // koperta wiadomości przyjętej
// Pakiety do stacji odrzucone przed warstwą aplikacji, według powodu: nadawca spoza karty (albo bez
// klucza w tablicy), kształt (nie SA1), znaczek pracy, podpis (także klucz nie do skrótu nadawcy).
struct LxmfRejects {
    uint32_t sender = 0, shape = 0, stamp = 0, signature = 0;
    uint32_t total() const { return sender + shape + stamp + signature; }
};
LxmfRejects lxmfRejects;
// Wpis w dzienniku (FRAM) o odrzuceniu, które wskazuje błąd konfiguracji albo podrobienie odbiorcy:
// najwyżej raz na godzinę dla powodu, żeby wrogi nadajnik nie zapełnił dziennika.
constexpr uint64_t LXMF_LOG_PERIOD_MS = 3600 * 1000;
uint64_t lxmfLoggedMs[2] = {};   // 0: zły podpis odbiorcy z karty, 1: znaczek pracy
bool lxmfLogged[2] = {};

void logLimited(size_t which, const char* text) {
    const uint64_t now = uptimeMs();
    if (lxmfLogged[which] && now - lxmfLoggedMs[which] < LXMF_LOG_PERIOD_MS) return;
    lxmfLogged[which] = true;
    lxmfLoggedMs[which] = now;
    log(text);
}

// SA1 z koperty; fałsz, gdy dane nie mają jej kształtu.
bool envelopeContent(const uint8_t* data, size_t length, const uint8_t*& content, size_t& contentLength) {
    if (length < ENVELOPE_SA1 + 2 || memcmp(data, ENVELOPE_HEAD, ENVELOPE_FROM) != 0 ||
        memcmp(data + ENVELOPE_TO - 3, "\",\"", 3) != 0 || memcmp(data + ENVELOPE_SA1 - 2, "\",", 2) != 0 ||
        data[length - 1] != ']') {
        return false;
    }
    content = data + ENVELOPE_SA1;
    contentLength = length - ENVELOPE_SA1 - 1;
    return true;
}

void hexTo(const uint8_t* bytes, size_t count, char* out) {
    static const char digits[] = "0123456789abcdef";
    for (size_t i = 0; i < count; ++i) {
        out[2 * i] = digits[bytes[i] >> 4];
        out[2 * i + 1] = digits[bytes[i] & 15];
    }
}

// Cel LXMF dla celu z warstwy aplikacji: odbiorca z karty po celu z setReceivers, inny cel bez zmian.
const uint8_t* lxmfTarget(const uint8_t dest[HASH]) {
    static const uint8_t zero[HASH] = {};
    for (size_t i = 0; i < 2; ++i) {
        if (memcmp(receiverApp[i], zero, HASH) != 0 && memcmp(receiverApp[i], dest, HASH) == 0) return pinned[i];
    }
    return dest;
}

// I odwrotnie: nadawca wiadomości w kopercie dla warstwy aplikacji.
const uint8_t* appSource(const uint8_t source[HASH]) {
    static const uint8_t zero[HASH] = {};
    for (size_t i = 0; i < 2; ++i) {
        if (memcmp(pinned[i], zero, HASH) != 0 && memcmp(pinned[i], source, HASH) == 0) return receiverApp[i];
    }
    return source;
}

// Pakiet do nadania (RNS/Transport.py: Transport.transmit przez interfejs z IFAC), warunki jak
// P1Interface::send_outgoing w porcie: interfejs z kodem, długość, cisza, miejsce w kolejce.
bool transmit(const uint8_t* raw, size_t length, p1iface::Hint hint) {
    p1iface::Counters& c = queue.counters();
    if (!ifacOnline) { ++c.offline; return false; }
    if (length < 2 || length > radio->timing().maxRaw) { ++c.tooLarge; return false; }
    if (silence == Silence::FULL || (silence == Silence::EXCEPTION && !exceptionOut)) { ++c.silenced; return false; }
    // Pełna kolejka: odmowa przed podpisem IFAC (ogłoszenia mogą jeszcze czekać na liście).
    if (p1iface::classify(raw, length) != p1iface::Kind::ANNOUNCE && queue.full()) { ++c.full; return false; }
    // Ogłoszenie bez miejsca w kolejce i na liście oczekujących: odmowa także przed podpisem IFAC.
    if (p1iface::classify(raw, length) == p1iface::Kind::ANNOUNCE && !queue.announceAdmits(raw, length, nowMs())) {
        ++c.announcesDropped;
        return false;
    }
    uint8_t wire[p1iface::MAX_WIRE];
    asymmetricWork = true;   // podpis IFAC
    const size_t wireLength = rnscore::ifacApply(ifac, raw, length, wire, sizeof(wire));
    if (!wireLength) { ++c.tooLarge; return false; }
    const p1iface::Admit admit = queue.offer(raw, length, wire, wireLength, nowMs(), hint);
    return admit == p1iface::Admit::QUEUED || admit == p1iface::Admit::HELD;
}

// Wywołania z transportu rdzenia: P1 (0) i USB węzła stanowiska (1, ramka KISS bez IFAC; zamknięty port
// albo pełny bufor: pakiet przepada i jest liczony, jak interfejs offline w Pythonie).
bool transmitHook(const uint8_t* raw, size_t length, uint8_t iface, void*) {
    if (iface == IFACE_USB) return usbPort && usbPort->send(raw, length);
    if (iface != IFACE_P1) return false;
    const p1iface::Hint hint = usb::hint(ownRequest, nodeMode, fromUsb, raw, length, computerDestination);
    const bool sent = transmit(raw, length, hint);
    if (sent && hint == p1iface::Hint::RECEIVER) ++usbK1;
    return sent;
}

bool randomHook(uint8_t* out, size_t length, void*) { return generator.generate(out, length); }

void announceHook(const uint8_t destination[HASH], const uint8_t* appData, size_t length, void*) {
    if (hooks.announce) hooks.announce(destination, appData, length, hooks.context);
}

// Nadawca to cel "lxmf.delivery" odbiorcy z karty (główny albo zapasowy).
bool cardReceiver(const uint8_t source[HASH]) {
    static const uint8_t zero[HASH] = {};
    for (const auto& dest : pinned) {
        if (memcmp(dest, zero, HASH) != 0 && memcmp(dest, source, HASH) == 0) return true;
    }
    return false;
}

// Klucz odbiorcy z karty, którego cel to source: z karty (konfiguracja w RAM), nie z tablicy znanych celów,
// więc uszkodzone gniazdo w FRAM nie odrzuca wiadomości odbiorcy z dowodem bez COMMIT (oprogramowanie.md,
// „Dowód dostarczenia po COMMIT”). Bez klucza w karcie (tylko próby na komputerze: polecenie receiver bez
// klucza) klucz z tablicy (Identity.recall). Fałsz: nadawca spoza karty albo bez klucza.
bool receiverKey(const uint8_t source[HASH], uint8_t out[rnscore::KEY_SIZE]) {
    static const uint8_t zero[rnscore::KEY_SIZE] = {};
    if (!cardReceiver(source)) return false;
    for (size_t i = 0; i < 2; ++i) {
        if (memcmp(pinned[i], source, HASH) != 0 || !memcmp(receiverKeys[i], zero, rnscore::KEY_SIZE)) continue;
        memcpy(out, receiverKeys[i], rnscore::KEY_SIZE);
        return true;
    }
    rnscore::KnownDestination sender;   // odczyt z FRAM (Transport::lookup)
    if (!transport.lookup(source, sender, uptimeMs())) return false;
    memcpy(out, sender.publicKey, rnscore::KEY_SIZE);
    return true;
}

// Wiadomość SA1 z danych pakietu do stacji (LXMRouter.delivery_packet i lxmf_delivery dla wiadomości
// z poprawnym podpisem) w kopercie dla warstwy aplikacji; 0: trwałe odrzucenie z powodem w lxmfRejects.
// Przed kryptografią: nadawca z karty (stacja przyjmuje wiadomości tylko od odbiorcy, oprogramowanie.md,
// „Model zaufania i kluczy”) i jego klucz (receiverKey); kształt sprawdza lxmfReceiveSa1 przed weryfikacją
// podpisu.
size_t lxmfToEnvelope(const uint8_t* data, size_t length) {
    const uint8_t* source = data + rnscore::LXMF_SOURCE_OFFSET;
    uint8_t senderKey[rnscore::KEY_SIZE];
    if (length < rnscore::LXMF_SOURCE_OFFSET + HASH || !receiverKey(source, senderKey)) {
        ++lxmfRejects.sender;
        return 0;
    }
    rnscore::LxmfSa1 m;
    rnscore::LxmfReject reason;
    if (!rnscore::lxmfReceiveSa1(addressBytes, data, length, senderKey, m, &reason)) {
        switch (reason) {
            case rnscore::LxmfReject::STAMP:
                ++lxmfRejects.stamp;
                logLimited(1, "rns: LXMF message with a stamp rejected (stamp cost set on the sender?)");
                break;
            case rnscore::LxmfReject::SOURCE:
            case rnscore::LxmfReject::SIGNATURE:
                ++lxmfRejects.signature;
                logLimited(0, "rns: LXMF signature of the receiver invalid");
                break;
            default:
                ++lxmfRejects.shape;
        }
        return 0;
    }
    memcpy(envelope, ENVELOPE_HEAD, ENVELOPE_FROM);
    hexTo(appSource(m.sourceHash), HASH, envelope + ENVELOPE_FROM);
    memcpy(envelope + ENVELOPE_TO - 3, "\",\"", 3);
    hexTo(addressBytes, HASH, envelope + ENVELOPE_TO);
    memcpy(envelope + ENVELOPE_SA1 - 2, "\",", 2);
    memcpy(envelope + ENVELOPE_SA1, m.content, m.contentLength);
    envelope[ENVELOPE_SA1 + m.contentLength] = ']';
    return ENVELOPE_SA1 + m.contentLength + 1;
}

// Decyzja warstwy aplikacji (PROVE_APP); dowód pakietu zgłoszenia z wyjątkiem ciszy wychodzi także
// w ciszy (znacznik kasuje received() po przetworzeniu pakietu), jak w porcie. Pakiet, który nie jest
// wiadomością SA1 odbiorcy z karty z poprawnym podpisem, to trwałe odrzucenie: z dowodem, bez warstwy
// aplikacji.
bool packetHook(const uint8_t* raw, size_t rawLength, void*) {
    const size_t length = lxmfToEnvelope(raw, rawLength);
    if (!length) return true;
    const uint8_t* data = reinterpret_cast<const uint8_t*>(envelope);
    bool exception = false;
    const bool accepted = hooks.packet && hooks.packet(data, length, exception, hooks.context);
    exceptionOut = accepted && exception;
    return accepted;
}

void receiptHook(uint32_t handle, bool delivered, void*) {
    if (hooks.receipt) hooks.receipt(handle, delivered, hooks.context);
}

// Żeton z wiadra tuż przed weryfikacją podpisu ogłoszenia, po tanich odrzuceniach w transporcie:
// powtórzone nagranie poprawnego ogłoszenia (IFAC przechodzi bez klucza sieci, bo kod jest
// deterministyczny) i ogłoszenie z kolizją klucza odpadają bez żetonu i nie wyczerpują wiadra.
// Interfejs przyjmie teraz pakiet stosu (jak transmit() przed podpisem IFAC, bez wyjątku ciszy).
// Przed podpisem odpowiedzi na zapytanie o cel stacji i przed retransmisją ogłoszenia (oba są
// ogłoszeniami): kod IFAC, bez ciszy, miejsce w kolejce i miejsce dla ogłoszenia najmniejszego rozmiaru
// (limit ogłoszeń 2%, pula, lista oczekujących). Pełne sprawdzenie zostaje w transmit(). USB zawsze
// tak (kontrakt mayTransmit w transport.h: zamknięty port porzuca pakiet w transmit).
bool mayTransmitHook(uint8_t iface, void*) {
    if (iface == IFACE_USB) return usbPort != nullptr;
    return iface == IFACE_P1 && ifacOnline && silence == Silence::OFF && !queue.full() &&
           queue.announceRoom(rnscore::HEADER_1_SIZE + rnscore::ANNOUNCE_MIN_SIZE, nowMs());
}

bool mayVerifyHook(uint8_t iface, void*) {
    if (iface >= rnscore::INTERFACES_MAX) return false;
    if (!verifyBuckets[iface].take(uptimeMs())) {
        ++announcesLimited[iface];
        return false;
    }
    asymmetricWork = true;   // weryfikacja podpisu zaraz po żetonie
    return true;
}

// Żeton tuż przed odszyfrowaniem pakietu do celu stacji, po filtrze duplikatów: powtórzone nagranie
// pakietu odpada bez żetonu.
bool mayReceiveHook(void*) {
    if (!receiveBucket.take(uptimeMs())) return false;
    asymmetricWork = true;   // odszyfrowanie (ECDH) zaraz po żetonie
    return true;
}

// Chronione w pełnej tablicy: odbiorca z karty i cele komputera stanowiska.
bool pinnedHook(const uint8_t destination[HASH], void*) { return cardReceiver(destination) || computerDestination(destination); }

// Tożsamości odbiorcy z kluczy karty w tablicy znanych celów (jak po ogłoszeniu, bez trasy). Klucz,
// z którego nie wychodzi cel z karty, jest pomijany: szyfrowanie do niego nie dotarłoby do odbiorcy.
void rememberReceivers() {
    static const uint8_t zero[rnscore::KEY_SIZE] = {};
    for (size_t i = 0; i < 2; ++i) {
        if (!memcmp(receiverKeys[i], zero, rnscore::KEY_SIZE) || !memcmp(pinned[i], zero, HASH)) continue;
        uint8_t identity[HASH], destination[HASH];
        rnscore::identityHash(receiverKeys[i], identity);
        rnscore::destinationHashFrom(nameHashBytes, identity, destination);
        if (memcmp(destination, pinned[i], HASH) != 0) {
            log("rns: receiver key does not match its destination");
            continue;
        }
        if (!transport.remember(pinned[i], receiverKeys[i], uptimeMs())) log("rns: receiver not remembered");
    }
}

// Kod dostępu jak Reticulum z passphrase = 32 cyfry szesnastkowe klucza z konfiguracji (jak port).
void configureIfac(const uint8_t key[16]) {
    ifacOnline = false;
    bool any = false;
    for (int i = 0; i < 16; ++i) any |= key[i] != 0;
    if (!any) return;
    char passphrase[33];
    for (int i = 0; i < 16; ++i) snprintf(passphrase + 2 * i, 3, "%02x", key[i]);
    ifacOnline = rnscore::ifacSetup(nullptr, passphrase, p1iface::IFAC_SIZE, ifac);
}

}  // namespace

bool begin(journal::Storage& storage, Radio& r, const uint8_t ifacKey[16], uint64_t clockAtStartMs, bool identitySaved,
           const uint8_t seed[32], const Hooks& h) {
    if (started || identityLost || halted) return started;
    hooks = h;
    static_assert(framfs::KEY_BYTES == rnscore::KEY_SIZE, "rekord klucza w FRAM = klucz prywatny Reticulum");
    if (!framfs::loadKey(storage, privateKey)) {
        if (identitySaved) {
            // Tożsamość była zapisana: nowa zmieniłaby adres stacji bez wiedzy odbiorcy (blad_pamieci).
            identityLost = true;
            log("rns: saved identity missing in FRAM");
            return false;
        }
        // RNS/Identity.py: Identity.create_keys: klucz X25519 i ziarno Ed25519 z generatora losowego.
        // Tu z HMAC-DRBG stacji z ziarnem z begin() (32 B z generatora stacji, drbg.h).
        drbg::Drbg keyGenerator;
        static const char nonce[] = "WICI rnscore identity";
        keyGenerator.seed(seed, 32, reinterpret_cast<const uint8_t*>(nonce), sizeof(nonce) - 1);
        const bool generated = keyGenerator.generate(privateKey, sizeof(privateKey));
        clean(&keyGenerator, sizeof(keyGenerator));   // stan generatora po kluczu (odporny wstecz, ale nie zostaje)
        // Klucz X25519 zapisany już przycięty (RFC 7748). Dla Reticulum w Pythonie i rdzenia to ten sam
        // klucz, ale port używa zapisanego klucza bez przycięcia (własne klucze tworzy przycięte): bez
        // tego powrót z rdzenia na port zmieniłby tożsamość stacji (tests/test_rns_stack_choice.py).
        privateKey[0] &= 0xF8;
        privateKey[31] = (privateKey[31] & 0x7F) | 0x40;
        if (!generated || !framfs::saveKey(storage, privateKey)) {
            clean(privateKey, sizeof(privateKey));
            log("rns: identity not saved in FRAM");
            return false;
        }
        identityNew = true;
    }
    rnscore::publicKey(privateKey, publicKeyBytes);
    rnscore::identityHash(publicKeyBytes, identityBytes);
    rnscore::nameHash(LXMF_DELIVERY, nameHashBytes);   // cel SINGLE "lxmf.delivery" stacji
    // Węzeł stanowiska nie ma adresu (jak w porcie): bez celu LXMF, tożsamość tylko dla transportu.
    if (!nodeMode) rnscore::destinationHashFrom(nameHashBytes, identityBytes, addressBytes);

    // Drugi generator z tego samego ziarna z innym nonce: losowość pracy stosu (RNS: os.urandom).
    static const char runtimeNonce[] = "WICI rnscore runtime";
    generator.seed(seed, 32, reinterpret_cast<const uint8_t*>(runtimeNonce), sizeof(runtimeNonce) - 1);
    clockMs = clockAtStartMs;
    clockLastMs = nowMs();
    for (auto& bucket : verifyBuckets) bucket.reset(clockMs);
    receiveBucket.reset(clockMs);
    // Węzeł stanowiska: bufor KISS raz, przy pierwszym starcie (bez sterty później); bez pamięci węzeł
    // działa bez USB. new (std::nothrow): na nRF52840 (Adafruit, GCC 7, newlib) malloc i nullptr przy braku
    // pamięci; na ESP32-S3 (ESP-IDF z wyjątkami C++) operator new zgłasza bad_alloc, który libstdc++ łapie
    // i zwraca nullptr, a przy zupełnie pełnej stercie (bez miejsca na obiekt wyjątku, pula awaryjna 0)
    // program przerywa się; tu to start stacji, więc oba wyniki są do przyjęcia.
    if (nodeMode && !usbPort) {
        usbPort = new (std::nothrow) kiss::Port();
        if (!usbPort) log("rns: no memory for the USB interface");
    }
    radio = &r;
    configureIfac(ifacKey);
    queue.setReceiver(pinned[receiverActive]);
    rnscore::TransportHooks th;
    th.transmit = transmitHook;
    th.announce = announceHook;
    th.packet = packetHook;
    th.receipt = receiptHook;
    th.pinned = pinnedHook;
    th.mayVerify = mayVerifyHook;
    th.mayReceive = mayReceiveHook;
    th.random = randomHook;
    th.mayTransmit = mayTransmitHook;
    framTable.fram = &storage;
    transport.begin(privateKey, publicKeyBytes, identityBytes, nodeMode ? nullptr : addressBytes, nameHashBytes, th, framTable,
                    clockMs, usbPort ? 2 : 1);
    // Cele komputera z tras przez USB o 1 skoku zapisanych przed restartem (cele samego komputera, nie te,
    // które tylko przekazuje); najnowsze ostatnie, więc zostają najdłużej.
    if (usbPort) {
        uint8_t routes[USB_PINNED][HASH];
        for (size_t n = transport.routes(IFACE_USB, 1, routes, USB_PINNED); n > 0; --n) usbDests.remember(routes[n - 1]);
    }
    queue.setTiming(radio->timing());
    transport.setBitrate(radio->timing().declaredBitrate);   // Interface.bitrate interfejsu radiowego (odkrycie trasy)
    started = true;
    rememberReceivers();
    log(usbPort ? "rns: Reticulum core (R4): P1 and USB interfaces, announces, proofs, table in FRAM"
                : "rns: Reticulum core (R3): P1 interface, announces, LXMF SA1 messages, proofs, table in FRAM");
    return true;
}

void setIfac(const uint8_t key[16]) {
    if (radio) configureIfac(key);
}

// Cel "lxmf.delivery" odbiorcy z klucza karty (config.cpp sprawdza, że to adres LXMF z karty); bez
// klucza (tylko próby na komputerze: polecenie receiver bez klucza) cel z wywołania.
void setReceivers(const uint8_t keys[2][64], const uint8_t sa1[2][HASH], uint8_t active) {
    static const uint8_t zero[rnscore::KEY_SIZE] = {};
    memcpy(receiverKeys, keys, sizeof(receiverKeys));
    memcpy(receiverApp, sa1, sizeof(receiverApp));
    uint8_t lxmfName[rnscore::NAME_HASH_SIZE];
    rnscore::nameHash(LXMF_DELIVERY, lxmfName);
    for (size_t i = 0; i < 2; ++i) {
        if (!memcmp(receiverKeys[i], zero, rnscore::KEY_SIZE)) {
            memcpy(pinned[i], sa1[i], HASH);
            continue;
        }
        uint8_t identity[HASH];
        rnscore::identityHash(receiverKeys[i], identity);
        rnscore::destinationHashFrom(lxmfName, identity, pinned[i]);
    }
    receiverActive = active ? 1 : 0;
    queue.setReceiver(pinned[receiverActive]);
    if (started) rememberReceivers();
}

void setNode(bool on) {
    if (!started) nodeMode = on;   // jak w porcie: zmiana działa po restarcie
}
bool node() { return nodeMode; }

void setSilence(Silence mode) {
    if (mode == silence) return;
    silence = mode;
    if (mode != Silence::OFF) queue.drop();   // nic z kolejki sprzed ciszy nie wychodzi
}

void dropQueue() { queue.drop(); }

void usbOpen(bool open) {
    if (usbPort) usbPort->setOpen(open);
}
void usbFeed(const uint8_t* data, size_t length, uint32_t now) {
    if (usbPort) usbPort->feed(data, length, now);
}
const uint8_t* usbOutput(size_t& length) {
    length = 0;
    return usbPort ? usbPort->output(length) : nullptr;
}
void usbConsume(size_t length) {
    if (usbPort) usbPort->consume(length);
}
UsbStatus usbStatus() { return usb::status(usbPort, usbDests); }
bool usbPinned(const uint8_t dest[HASH]) { return computerDestination(dest); }
// Pola jak w porcie, ogłoszenia z USB odrzucone przez limit weryfikacji, pakiety z USB odrzucone (flaga IFAC,
// unpack, transport) i pakiety na P1 w klasie K1 z reguły węzła. Wynik jak snprintf w porcie: długość całego
// tekstu (także gdy nie mieści się w out).
size_t usbJson(char* out, size_t size) {
    const size_t n = usb::json(usbStatus(), nodeMode, out, size);
    const bool room = n < size;
    const int m = snprintf(room ? out + n : nullptr, room ? size - n : 0,
                           ",\"usb_ann_limited\":%lu,\"usb_rx_ifac\":%lu,\"usb_rx_malformed\":%lu,\"usb_rx_invalid\":%lu,\"usb_k1\":%lu",
                           (unsigned long)announcesLimited[IFACE_USB], (unsigned long)usbRejects.ifacFlag,
                           (unsigned long)usbRejects.malformed, (unsigned long)usbRejects.invalid, (unsigned long)usbK1);
    return n + (m > 0 ? static_cast<size_t>(m) : 0);
}

namespace {

// Sprawdzenie IFAC datagramu w kolejce; w miejscu zostaje pakiet bez IFAC. Osobna funkcja bez wstawiania:
// bufor raw nie leży w ramce stosu ścieżki pakietu w transporcie (najgłębszej w węźle).
__attribute__((noinline)) void ifacStep(RxSlot& slot) {
    p1iface::Counters& c = queue.counters();
    uint8_t raw[p1iface::MAX_WIRE];
    const size_t rawLength = rnscore::ifacCheck(ifac, slot.bytes, slot.length, raw, sizeof(raw));
    if (!rawLength) { ++c.ifacInvalid; rxDrop(); return; }
    ++c.received;
    memcpy(slot.bytes, raw, rawLength);
    slot.length = static_cast<uint16_t>(rawLength);
    slot.checked = true;
}

// Jeden krok odbioru na obieg loop(): sprawdzenie IFAC najstarszego datagramu albo, w następnym obiegu,
// pakiet w transporcie (RNS/Transport.py: inbound po odjęciu IFAC w Interface). Prawda: krok był (mógł
// zrobić operację asymetryczną).
bool receiveStep() {
    if (!rxCount) return false;
    RxSlot& slot = rx[rxHead];
    if (!ifacOnline) { ++queue.counters().offline; rxDrop(); return false; }
    if (!slot.checked) {
        ifacStep(slot);
        return true;
    }
    if (!transport.inbound(slot.bytes, slot.length, uptimeMs(), IFACE_P1)) ++malformed;
    exceptionOut = false;
    rxDrop();
    return true;
}

// Krok USB: najstarszy pakiet od komputera w transporcie, gdy kolejka P1 ma miejsce (inaczej czeka
// w buforze KISS, a komputer na gotowość; jak w porcie). Pakiet z flagą IFAC odpada jak w Pythonie na
// interfejsie bez IFAC (Transport.inbound: „IFAC flag set on packet for interface without IFAC enabled”).
// Ogłoszenie z 0 skokami (cel samego komputera), które dało trasę przez USB, to cel komputera. Prawda:
// krok był.
bool usbStep() {
    if (!usbPort || queue.full()) return false;
    const uint8_t* data;
    size_t length;
    if (!usbPort->peek(data, length)) return false;
    if (length > radio->timing().maxRaw) {   // ponad największy pakiet łącza: odpada przed stosem i podpisem IFAC
        ++queue.counters().tooLarge;
        usbPort->pop();
        return true;
    }
    if (length && (data[0] & 0x80)) {
        ++usbRejects.ifacFlag;
        usbPort->pop();
        return true;
    }
    const uint32_t invalid = transport.counters().invalid;
    fromUsb = true;
    if (!transport.inbound(data, length, uptimeMs(), IFACE_USB)) ++usbRejects.malformed;
    fromUsb = false;
    usbRejects.invalid += transport.counters().invalid - invalid;
    if (length > 1 && data[1] == 0 && p1iface::classify(data, length) == p1iface::Kind::ANNOUNCE) {
        const uint8_t* dest = p1iface::destination(data, length);
        if (dest && transport.pathInterface(dest) == IFACE_USB) usbDests.remember(dest);
    }
    usbPort->pop();
    return true;
}

// Jeden krok odbioru na obieg, na zmianę P1 i USB, gdy oba mają pracę: zalew z jednego interfejsu nie
// wstrzymuje drugiego.
enum class Step : uint8_t { NONE, P1, USB };
Step receiveOrUsbStep() {
    const bool usbFirst = usbNext;
    if (usbFirst ? usbStep() : receiveStep()) {
        usbNext = !usbFirst;
        return usbFirst ? Step::USB : Step::P1;
    }
    if (usbFirst ? receiveStep() : usbStep()) return usbFirst ? Step::P1 : Step::USB;
    return Step::NONE;
}

}  // namespace

void loop(uint32_t) {
    if (!started || !radio) return;
    asymmetricWork = false;
    const Step step = receiveOrUsbStep();
    // Potwierdzenia po limicie (licznik pracy nie gubi zawinięcia zegara ms); retransmisja z podpisem IFAC
    // tylko w obiegu bez kroku P1 i bez pracy asymetrycznej kroku USB (najwyżej jedna operacja asymetryczna
    // na obieg; licznik operacji jest tylko w budowach prób).
    transport.poll(uptimeMs(), step != Step::P1 && !asymmetricWork);
    const uint32_t now = nowMs();
    if (silence == Silence::OFF) queue.poll(now);   // ogłoszenia oczekujące nie wychodzą w ciszy
    else queue.tick(now);
    if (queue.transmitting() || !radio->ready()) return;
    const uint8_t* data;
    size_t length;
    if (!queue.start(data, length)) return;
    if (!radio->transmit(data, length)) queue.finish(false);
}

// Bez kryptografii: sprawdzenia długości i flagi IFAC, potem datagram czeka w kolejce odbioru na loop().
// Wołane z tego samego zadania co loop() (kolejka odbioru nie ma blokad).
void received(const uint8_t* wire, size_t length) {
    if (!started) return;
    p1iface::Counters& c = queue.counters();
    if (!ifacOnline) { ++c.offline; return; }
    if (!p1iface::ifacPresent(wire, length, p1iface::IFAC_SIZE)) { ++c.ifacMissing; return; }
    if (length > radio->timing().maxWire) { ++c.tooLarge; return; }
    if (rxCount == RX_SLOTS) { ++rxDropped; return; }
    RxSlot& slot = rx[(rxHead + rxCount) % RX_SLOTS];
    memcpy(slot.bytes, wire, length);
    slot.length = static_cast<uint16_t>(length);
    slot.checked = false;
    ++rxCount;
}

void txDone(bool ok) { queue.finish(ok); }

// Bez danych aplikacji: dane jak LXMRouter.get_announce_app_data, msgpack [nazwa, None, [SF_COMPRESSION]]
// z nazwą WICI-xxxxxx (oprogramowanie.md, „Ogłoszenia adresu”; 6 cyfr skrótu tożsamości jak w main.cpp),
// bez kosztu znaczka. Dane podane przez wywołującego (próby na komputerze) idą bez zmian.
bool announce(const uint8_t* appData, size_t length) {
    if (!started || nodeMode) return false;
    uint8_t peerData[17] = {0x93, 0xC4, 11, 'W', 'I', 'C', 'I', '-'};
    if (!appData) {
        char name[7];
        snprintf(name, sizeof(name), "%02X%02X%02X", identityBytes[0], identityBytes[1], identityBytes[2]);
        memcpy(peerData + 8, name, 6);
        peerData[14] = 0xC0;   // stamp_cost: None
        peerData[15] = 0x91;   // [SF_COMPRESSION]
        peerData[16] = 0x00;
        appData = peerData;
        length = sizeof(peerData);
    }
    uint8_t random[5];
    return generator.generate(random, sizeof(random)) && transport.announce(random, appData, length, uptimeMs());
}

namespace {

// Pakiet i zapytanie o trasę z sendReady() i send() to ruch własny stacji; w ciszy z wyjątkiem warstwa
// aplikacji wysyła tylko zgłoszenie objęte wyjątkiem (station::Station::silencedFor), jak w porcie.
struct OwnTraffic {
    OwnTraffic() { exceptionOut = silence == Silence::EXCEPTION; }
    ~OwnTraffic() { exceptionOut = false; }
};

bool interfaceAccepts() { return started && !nodeMode && ifacOnline && !queue.full(); }

// RNS/Transport.py: request_path ze znacznikiem losowym (Identity.get_random_hash).
void requestOwnPath(const uint8_t dest[HASH]) {
    uint8_t tag[HASH];
    if (!generator.generate(tag, sizeof(tag))) return;
    ownRequest = true;
    transport.requestPath(dest, tag, uptimeMs());
    ownRequest = false;
}

// Odbiorca z karty, którego wpis wypadł z tablicy (uszkodzone gniazdo w FRAM): wpis z kluczy karty od
// nowa (bez trasy i ratchetu, jak po starcie), żeby zgłoszenia nie stanęły do restartu.
bool knowsOrRemembers(const uint8_t dest[HASH]) {
    if (transport.knows(dest)) return true;
    if (memcmp(dest, pinned[0], HASH) != 0 && memcmp(dest, pinned[1], HASH) != 0) return false;
    rememberReceivers();
    return transport.knows(dest);
}

// Tożsamość celu znana (także odbiorca z karty odtworzony z jej kluczy); inaczej zapytanie o trasę (ruch
// własny, K0) i fałsz (jak recallOrRequest w porcie).
bool knownOrRequest(const uint8_t dest[HASH]) {
    if (knowsOrRemembers(dest)) return true;
    requestOwnPath(dest);
    return false;
}

}  // namespace

// Koperta warstwy aplikacji: SA1 jako wiadomość LXMF (LXMessage.pack, OPPORTUNISTIC) do celu
// "lxmf.delivery". Znacznik czasu LXMF to licznik pracy stacji w s (odbiorca go ignoruje, oprogramowanie.md,
// „Czas”). Dalej jak pakiet okazjonalny R1.
uint32_t send(const uint8_t appDest[HASH], const uint8_t* message, size_t messageLength, uint32_t timeoutS) {
    if (!interfaceAccepts()) return 0;
    const uint8_t* dest = lxmfTarget(appDest);
    const uint8_t* content;
    size_t contentLength;
    if (!envelopeContent(message, messageLength, content, contentLength)) return 0;
    OwnTraffic own;
    if (!knownOrRequest(dest)) return 0;
    uint8_t messageHash[rnscore::HASH_SIZE];
    const size_t length = rnscore::lxmfPackSa1(privateKey, publicKeyBytes, dest, addressBytes, static_cast<double>(uptimeMs() / 1000),
                                               content, contentLength, lxmfOut, sizeof(lxmfOut), messageHash);
    if (!length) return 0;
    const uint8_t* data = lxmfOut;
    // Limit od przekazania do stosu jak w porcie (radio.md, "Interfejs P1 w stosie Reticulum"):
    // max(60 s, timeoutS, 2 × skoki × 13 × czas TX największego datagramu + dług ciszy + kolejka P1);
    // trasa nieznana liczy się jako 1 skok.
    uint32_t hops = transport.hopsTo(dest, uptimeMs());
    if (hops == 0 || hops >= rnscore::PATHFINDER_M) hops = 1;
    const uint64_t waitMs = radio->timing().receiptWaitMs(hops) + queueWaitMs();
    uint64_t limit = (waitMs + 999) / 1000;
    if (limit < timeoutS) limit = timeoutS;
    if (limit < RECEIPT_MIN_S) limit = RECEIPT_MIN_S;
    // RNS: X25519PrivateKey.generate i os.urandom dla każdego tokenu.
    uint8_t random[32 + 16];
    if (!generator.generate(random, sizeof(random))) return 0;
    const uint32_t handle = ++nextHandle ? nextHandle : ++nextHandle;
    rnscore::SendResult result = transport.send(dest, data, length, random, random + 32, handle, limit * 1000, uptimeMs());
    // Wpis wypadł przy odczycie (błędne CRC; nic nie wyszło, więc te same bajty losowe): odbiorca z karty od nowa.
    if (result == rnscore::SendResult::UNKNOWN && knowsOrRemembers(dest)) {
        result = transport.send(dest, data, length, random, random + 32, handle, limit * 1000, uptimeMs());
    }
    clean(random, sizeof(random));
    return result == rnscore::SendResult::SENT ? handle : 0;
}

bool sendReady(const uint8_t dest[HASH]) {
    if (!interfaceAccepts()) return false;
    OwnTraffic own;
    return knownOrRequest(lxmfTarget(dest));
}
bool knows(const uint8_t dest[HASH]) { return started && transport.knows(lxmfTarget(dest)); }
bool hasPath(const uint8_t dest[HASH]) {
    rnscore::KnownDestination e;   // odczyt z FRAM: trasa po wygaśnięciu już nie jest trasą
    return started && transport.lookup(lxmfTarget(dest), e, uptimeMs()) && e.hasPath;
}
void requestPath(const uint8_t dest[HASH]) {
    if (started) requestOwnPath(lxmfTarget(dest));
}
bool queueFull() { return !radio || queue.full(); }
bool online() { return started && ifacOnline; }
uint32_t queueWaitMs() { return radio ? queue.waitMs(radio->debtMs()) : 0; }

const uint8_t* address() { return addressBytes; }
const uint8_t* identityHash() { return identityBytes; }
bool publicKey(uint8_t out[64]) {
    if (!started) return false;
    memcpy(out, publicKeyBytes, sizeof(publicKeyBytes));
    return true;
}

Status status() {
    Status s;
    s.started = started;
    s.identityNew = identityNew;
    s.identityLost = identityLost;
    s.bitrate = radio ? radio->timing().declaredBitrate : p1iface::p1Timing().declaredBitrate;
    if (!started) return s;
    s.online = ifacOnline;
    const rnscore::TransportCounters& t = transport.counters();
    s.paths = transport.paths();
    s.packetHashes = transport.hashes();
    s.receiptsPending = transport.receiptsPending();
    s.announceTable = transport.announceTable();
    s.fsFiles = transport.known();   // wpisy tablicy znanych celów w gniazdach FRAM
    s.fsUsedBytes = transport.known() * rnscore::TABLE_SLOT_SIZE;
    s.fsCapacityBytes = rnscore::TABLE_AREA;
    s.packetsSent = t.sent;
    s.packetsReceived = t.received;
    s.packetsUnproven = t.unproven;
    s.delivered = t.delivered;
    s.timedOut = t.timedOut;
    s.announcesSeen = t.announces;
    const p1iface::Counters& c = queue.counters();
    s.k2Dropped = c.k2Slot + c.k2Pool + c.k2Dest;
    s.queueWaitMs = queueWaitMs();
    s.announceWaitMs = queue.announceAllowedInMs(nowMs());
    return s;
}

size_t interfaceJson(char* out, size_t size) {
    if (!radio) return snprintf(out, size, "\"p1_iface\":false");
    // Pola jak w porcie (rns_node.cpp) i liczniki rdzenia: pakiety odrzucone przez rnscore::unpack,
    // duplikaty, pakiety poza podzbiorem R1 albo nie do stacji, odrzucone przy sprawdzaniu, datagramy
    // odrzucone przy pełnej kolejce odbioru, ogłoszenia odrzucone przez limit weryfikacji, gniazda tablicy
    // znanych celów z błędną treścią (zwolnione), pakiety do stacji, które nie są wiadomością SA1 odbiorcy
    // z karty (razem i według powodu), pakiety do stacji odrzucone przed odszyfrowaniem przez limit pracy.
    const p1iface::Counters& c = queue.counters();
    const rnscore::TransportCounters& t = transport.counters();
    const uint32_t invalid = t.invalid - usbRejects.invalid;   // rx_invalid: tylko P1 (USB w usbJson)
    const uint32_t now = nowMs();   // okna czasu kanału przesuwane przed printf (kolejność wywołań)
    const unsigned long poolMs = queue.poolUsedMs(now), prMs = queue.pathRequestUsedMs(now);
    const int n = snprintf(out, size,
                           "\"link\":\"%s\",\"q_len\":%u,\"q_held\":%u,\"q_queued\":%lu,\"q_full\":%lu,\"too_large\":%lu,\"ann_held\":%lu,"
                           "\"ann_drop\":%lu,\"ann_expired\":%lu,\"tx_sent\":%lu,\"tx_failed\":%lu,\"rx_ok\":%lu,"
                           "\"ifac_missing\":%lu,\"ifac_invalid\":%lu,\"offline\":%lu,\"silenced\":%lu,\"k2_slot\":%lu,\"k2_pool\":%lu,"
                           "\"k2_dest\":%lu,\"pr_limited\":%lu,\"pr_resp_limited\":%lu,\"pool_ms\":%lu,\"pr_ms\":%lu,\"rx_malformed\":%lu,\"rx_duplicate\":%lu,"
                           "\"rx_ignored\":%lu,\"rx_invalid\":%lu,\"rx_queue_full\":%lu,\"ann_limited\":%lu,\"table_corrupt\":%lu,"
                           "\"pr_in\":%lu,\"pr_answered\":%lu,\"pr_responses\":%lu,\"pr_sent\":%lu,\"ann_table_full\":%lu,"
                           "\"fwd\":%lu,\"fwd_no_path\":%lu,\"proof_fwd\":%lu,\"rev_full\":%lu,\"ann_rebroadcast\":%lu,\"pr_gated\":%lu,"
                           "\"lxmf_rejected\":%lu,\"lxmf_rej_sender\":%lu,\"lxmf_rej_shape\":%lu,\"lxmf_rej_stamp\":%lu,"
                           "\"lxmf_rej_signature\":%lu,\"rx_limited\":%lu",
                           radio->timing().framing == p1iface::LinkTiming::Framing::RNODE ? "lora" : "p1",
                           (unsigned)queue.queued(), (unsigned)queue.held(), (unsigned long)c.queued, (unsigned long)c.full,
                           (unsigned long)c.tooLarge, (unsigned long)c.announcesHeld, (unsigned long)c.announcesDropped,
                           (unsigned long)c.announcesExpired, (unsigned long)c.sent, (unsigned long)c.sendFailed,
                           (unsigned long)c.received, (unsigned long)c.ifacMissing, (unsigned long)c.ifacInvalid,
                           (unsigned long)c.offline, (unsigned long)c.silenced, (unsigned long)c.k2Slot, (unsigned long)c.k2Pool,
                           (unsigned long)c.k2Dest, (unsigned long)c.pathRequestLimited, (unsigned long)c.pathResponseLimited, poolMs, prMs, (unsigned long)malformed,
                           (unsigned long)t.duplicate, (unsigned long)t.ignored, (unsigned long)invalid,
                           (unsigned long)rxDropped, (unsigned long)announcesLimited[IFACE_P1], (unsigned long)transport.tableCorrupt(),
                           (unsigned long)t.pathRequests, (unsigned long)t.pathAnswered, (unsigned long)t.pathResponses,
                           (unsigned long)t.requestsSent, (unsigned long)t.announceTableFull, (unsigned long)t.forwarded,
                           (unsigned long)t.noPath, (unsigned long)t.proofsForwarded, (unsigned long)t.reverseFull,
                           (unsigned long)t.rebroadcasts, (unsigned long)t.pathGated,
                           (unsigned long)lxmfRejects.total(),
                           (unsigned long)lxmfRejects.sender, (unsigned long)lxmfRejects.shape, (unsigned long)lxmfRejects.stamp,
                           (unsigned long)lxmfRejects.signature, (unsigned long)t.receiveLimited);
    return n < 0 ? 0 : static_cast<size_t>(n);
}

void halt() {
    // Jak w porcie: stos staje, interfejs przestaje nadawać, adres i skrót nie wskazują kasowanej
    // tożsamości; klucze (tożsamość, IFAC) i stan generatora znikają też z RAM. Ponowny begin() dopiero
    // po restarcie: nie wczyta klucza z FRAM, nawet jeśli magazyn go jeszcze nie skasował.
    started = false;
    halted = true;
    identityNew = false;
    ifacOnline = false;
    queue.drop();
    memset(rx, 0, sizeof(rx));
    rxCount = 0;
    clean(lxmfOut, sizeof(lxmfOut));   // treść ostatnich wiadomości
    clean(envelope, sizeof(envelope));
    transport.clear();
    usbDests.clear();
    // Bufor zostaje (bez zwalniania pamięci) i port nic nie wysyła; pakiety, które były w nim od komputera,
    // też zostają, ale nic ich nie przetwarza (loop() po halt() nic nie robi).
    if (usbPort) usbPort->setOpen(false);
    framTable.fram = nullptr;   // bez zapisów w FRAM do restartu
    clean(privateKey, sizeof(privateKey));
    clean(&ifac, sizeof(ifac));
    clean(&generator, sizeof(generator));
    memset(publicKeyBytes, 0, sizeof(publicKeyBytes));
    memset(addressBytes, 0, sizeof(addressBytes));
    memset(identityBytes, 0, sizeof(identityBytes));
}

void persist() {}   // tablica znanych celów jest zapisywana przy każdej zmianie wpisu

#ifndef ARDUINO
void debugTableMax(uint16_t n) { transport.setLimit(n); }
uint32_t debugFillHashes(uint32_t) { return 0; }
void debugClock(uint64_t (*clock)()) { hostClock = clock; }

size_t debugIfacWrap(const uint8_t* raw, size_t length, uint8_t* wire) {
    if (!ifacOnline || length < 2 || length > radio->timing().maxRaw) return 0;
    return rnscore::ifacApply(ifac, raw, length, wire, p1iface::MAX_WIRE);
}

size_t debugIfacUnwrap(const uint8_t* wire, size_t length, uint8_t* raw) {
    if (!ifacOnline || length > radio->timing().maxWire) return 0;
    return rnscore::ifacCheck(ifac, wire, length, raw, p1iface::MAX_WIRE);
}
#endif

}  // namespace rnsnode
