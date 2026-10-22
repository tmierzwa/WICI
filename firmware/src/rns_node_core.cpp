// SPDX-License-Identifier: MIT
// Węzeł Reticulum stacji na rdzeniu (firmware/reticulum-core.md): ten sam interfejs rns_node.h co
// port, w programie na komputerze (env:host-core). Działa:
// - tożsamość: ten sam rekord klucza w FRAM co w porcie (framfs::loadKey, 64 B w kolejności Reticulum),
//   więc stacja zachowuje tożsamość i adres przy przejściu z portu na rdzeń (decyzja z 2026-10-22);
// - interfejs P1 (etap R1): kod dostępu IFAC 16 B z rdzenia (rnscore::ifacApply, ifacCheck) z frazą
//   jak w porcie (32 cyfry szesnastkowe klucza z konfiguracji), kolejka radiowa, klasy ruchu i limit
//   ogłoszeń z p1iface, cisza radiowa jak w porcie, liczniki interfejsu w tym samym JSON;
// - ogłoszenie własne celu "wici.sa1" bez ratchetu (własne ratchety stacji są poza rdzeniem); czas
//   w skrócie losowym z licznika pracy (clockMs z begin() i zegar ms stosu), losowość z HMAC-DRBG
//   stacji z ziarnem z begin().
// Pakiet przyjęty z P1 jest na razie tylko rozbierany (rnscore::unpack); ogłoszenia innych celów,
// pakiety do stacji, dowody, wysyłanie i trasy przychodzą w następnych krokach R1 i w R2–R4:
// odpowiednie funkcje odpowiadają jak stos bez celu (fałsz, 0, brak trasy).
#include <stdio.h>
#include <string.h>

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
#include "p1iface.h"
#include "packet.h"
#include "rns_node.h"

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
drbg::Drbg generator;   // skróty losowe ogłoszeń (dalej klucze efemeryczne i IV)

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
uint8_t pinned[2][HASH] = {};   // cele "wici.sa1" odbiorcy z karty (główny, zapasowy)
uint8_t receiverActive = 0;
// Cisza radiowa i znacznik ruchu dopuszczonego wyjątkiem (pakiet z send(), dowód pakietu zgłoszenia).
Silence silence = Silence::OFF;
bool exceptionOut = false;
uint32_t malformed = 0;   // pakiety z poprawnym IFAC, które odrzuca rnscore::unpack

void log(const char* text) {
    if (hooks.log) hooks.log(text, hooks.context);
}

// Pakiet do nadania (RNS/Transport.py: Transport.transmit przez interfejs z IFAC), warunki jak
// P1Interface::send_outgoing w porcie: interfejs z kodem, długość, cisza, miejsce w kolejce.
bool transmit(const uint8_t* raw, size_t length, p1iface::Hint hint) {
    p1iface::Counters& c = queue.counters();
    if (!ifacOnline) { ++c.offline; return false; }
    if (length < 2 || length > p1iface::HW_MTU) { ++c.tooLarge; return false; }
    if (silence == Silence::FULL || (silence == Silence::EXCEPTION && !exceptionOut)) { ++c.silenced; return false; }
    // Pełna kolejka: odmowa przed podpisem IFAC (ogłoszenia mogą jeszcze czekać na liście).
    if (p1iface::classify(raw, length) != p1iface::Kind::ANNOUNCE && queue.full()) { ++c.full; return false; }
    uint8_t wire[p1iface::MAX_WIRE];
    const size_t wireLength = rnscore::ifacApply(ifac, raw, length, wire, sizeof(wire));
    if (!wireLength) { ++c.tooLarge; return false; }
    const p1iface::Admit admit = queue.offer(raw, length, wire, wireLength, nowMs(), hint);
    return admit == p1iface::Admit::QUEUED || admit == p1iface::Admit::HELD;
}

// Pakiet bez IFAC z interfejsu P1 (RNS/Transport.py: Transport.preprocess_inbound po kodzie dostępu).
void inbound(const uint8_t* raw, size_t length) {
    rnscore::Packet packet;
    if (!rnscore::unpack(raw, length, packet)) {
        ++malformed;
        return;
    }
    // Następne kroki R1: ogłoszenia celów "wici.sa1", pakiety do stacji z dowodem, dowody wysłanych.
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
    if (started || identityLost) return started;
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
    char name[32];
    snprintf(name, sizeof(name), "%s.%s", APP_NAME, ASPECT);   // cel SINGLE "wici.sa1" stacji
    rnscore::nameHash(name, nameHashBytes);
    // Węzeł stanowiska nie ma adresu (jak w porcie): bez celu "wici.sa1", tożsamość tylko dla transportu.
    if (!nodeMode) rnscore::destinationHashFrom(nameHashBytes, identityBytes, addressBytes);

    // Drugi generator z tego samego ziarna z innym nonce: losowość pracy stosu (RNS: os.urandom).
    static const char runtimeNonce[] = "WICI rnscore runtime";
    generator.seed(seed, 32, reinterpret_cast<const uint8_t*>(runtimeNonce), sizeof(runtimeNonce) - 1);
    clockMs = clockAtStartMs;
    clockLastMs = nowMs();
    radio = &r;
    configureIfac(ifacKey);
    queue.setReceiver(pinned[receiverActive]);
    started = true;
    log("rns: Reticulum core (R1): P1 interface and own announces");
    return true;
}

void setIfac(const uint8_t key[16]) {
    if (radio) configureIfac(key);
}

void setReceivers(const uint8_t[2][64], const uint8_t sa1[2][HASH], uint8_t active) {
    memcpy(pinned, sa1, sizeof(pinned));
    receiverActive = active ? 1 : 0;
    queue.setReceiver(pinned[receiverActive]);
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

void usbOpen(bool) {}
void usbFeed(const uint8_t*, size_t, uint32_t) {}
const uint8_t* usbOutput(size_t& length) {
    length = 0;
    return nullptr;
}
void usbConsume(size_t) {}
UsbStatus usbStatus() { return UsbStatus(); }
bool usbPinned(const uint8_t[HASH]) { return false; }
size_t usbJson(char* out, size_t size) {
    const int n = snprintf(out, size, "\"node\":%s,\"usb_iface\":false", nodeMode ? "true" : "false");
    return n > 0 ? static_cast<size_t>(n) : 0;
}

void loop(uint32_t) {
    if (!started || !radio) return;
    uptimeMs();   // licznik pracy nie gubi zawinięcia zegara ms
    const uint32_t now = nowMs();
    if (silence == Silence::OFF) queue.poll(now);   // ogłoszenia oczekujące nie wychodzą w ciszy
    else queue.tick(now);
    if (queue.transmitting() || !radio->ready()) return;
    const uint8_t* data;
    size_t length;
    if (!queue.start(data, length)) return;
    if (!radio->transmit(data, length)) queue.finish(false);
}

void received(const uint8_t* wire, size_t length) {
    if (!started) return;
    p1iface::Counters& c = queue.counters();
    if (!ifacOnline) { ++c.offline; return; }
    if (!p1iface::ifacPresent(wire, length, p1iface::IFAC_SIZE)) { ++c.ifacMissing; return; }
    if (length > p1iface::MAX_WIRE) { ++c.tooLarge; return; }
    uint8_t raw[p1iface::MAX_WIRE];
    const size_t rawLength = rnscore::ifacCheck(ifac, wire, length, raw, sizeof(raw));
    if (!rawLength) { ++c.ifacInvalid; return; }
    ++c.received;
    inbound(raw, rawLength);
    exceptionOut = false;
}

void txDone(bool ok) { queue.finish(ok); }

bool announce(const uint8_t* appData, size_t length) {
    if (!started || nodeMode) return false;
    // RNS/Destination.py: Destination.announce (bez ratchetu, kontekst NONE), wysłane jak Packet.send:
    // HEADER_1, BROADCAST, 0 skoków.
    uint8_t random[5];
    uint8_t randomHash[rnscore::RANDOM_HASH_SIZE];
    if (!generator.generate(random, sizeof(random))) return false;
    rnscore::announceRandomHash(random, uptimeMs() / 1000, randomHash);
    uint8_t data[rnscore::ANNOUNCE_FORWARDABLE_SIZE];
    rnscore::Packet packet = {};
    packet.headerType = rnscore::HEADER_1;
    packet.transportType = rnscore::BROADCAST;
    packet.destinationType = rnscore::SINGLE;
    packet.packetType = rnscore::ANNOUNCE;
    memcpy(packet.destinationHash, addressBytes, HASH);
    packet.dataLength = rnscore::buildAnnounce(privateKey, publicKeyBytes, addressBytes, nameHashBytes, randomHash, nullptr,
                                               appData, length, data, sizeof(data));
    packet.data = data;
    uint8_t raw[rnscore::MTU];
    const size_t rawLength = packet.dataLength ? rnscore::pack(packet, raw, sizeof(raw)) : 0;
    return rawLength && transmit(raw, rawLength, p1iface::Hint::NONE);
}

uint32_t send(const uint8_t[HASH], const uint8_t*, size_t, uint32_t) { return 0; }
bool sendReady(const uint8_t[HASH]) { return false; }
bool knows(const uint8_t[HASH]) { return false; }
bool hasPath(const uint8_t[HASH]) { return false; }
void requestPath(const uint8_t[HASH]) {}
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
    s.bitrate = p1iface::declaredBitrate();
    if (!started) return s;
    s.online = ifacOnline;
    const p1iface::Counters& c = queue.counters();
    s.k2Dropped = c.k2Slot + c.k2Pool + c.k2Dest;
    s.queueWaitMs = queueWaitMs();
    s.announceWaitMs = queue.announceAllowedInMs(nowMs());
    return s;
}

size_t interfaceJson(char* out, size_t size) {
    if (!radio) return snprintf(out, size, "\"p1_iface\":false");
    // Pola jak w porcie (rns_node.cpp) i licznik pakietów odrzuconych przez rnscore::unpack.
    const p1iface::Counters& c = queue.counters();
    const uint32_t now = nowMs();   // okna czasu kanału przesuwane przed printf (kolejność wywołań)
    const unsigned long poolMs = queue.poolUsedMs(now), prMs = queue.pathRequestUsedMs(now);
    const int n = snprintf(out, size,
                           "\"q_len\":%u,\"q_held\":%u,\"q_queued\":%lu,\"q_full\":%lu,\"too_large\":%lu,\"ann_held\":%lu,"
                           "\"ann_drop\":%lu,\"ann_expired\":%lu,\"tx_sent\":%lu,\"tx_failed\":%lu,\"rx_ok\":%lu,"
                           "\"ifac_missing\":%lu,\"ifac_invalid\":%lu,\"offline\":%lu,\"silenced\":%lu,\"k2_slot\":%lu,\"k2_pool\":%lu,"
                           "\"k2_dest\":%lu,\"pr_limited\":%lu,\"pool_ms\":%lu,\"pr_ms\":%lu,\"rx_malformed\":%lu",
                           (unsigned)queue.queued(), (unsigned)queue.held(), (unsigned long)c.queued, (unsigned long)c.full,
                           (unsigned long)c.tooLarge, (unsigned long)c.announcesHeld, (unsigned long)c.announcesDropped,
                           (unsigned long)c.announcesExpired, (unsigned long)c.sent, (unsigned long)c.sendFailed,
                           (unsigned long)c.received, (unsigned long)c.ifacMissing, (unsigned long)c.ifacInvalid,
                           (unsigned long)c.offline, (unsigned long)c.silenced, (unsigned long)c.k2Slot, (unsigned long)c.k2Pool,
                           (unsigned long)c.k2Dest, (unsigned long)c.pathRequestLimited, poolMs, prMs, (unsigned long)malformed);
    return n < 0 ? 0 : static_cast<size_t>(n);
}

void halt() {
    // Jak w porcie: stos staje, interfejs przestaje nadawać, adres i skrót nie wskazują kasowanej
    // tożsamości; klucze (tożsamość, IFAC) i stan generatora znikają też z RAM.
    started = false;
    identityNew = false;
    ifacOnline = false;
    queue.drop();
    clean(privateKey, sizeof(privateKey));
    clean(&ifac, sizeof(ifac));
    clean(&generator, sizeof(generator));
    memset(publicKeyBytes, 0, sizeof(publicKeyBytes));
    memset(addressBytes, 0, sizeof(addressBytes));
    memset(identityBytes, 0, sizeof(identityBytes));
}

void persist() {}

#ifndef ARDUINO
void debugTableMax(uint16_t) {}
uint32_t debugFillHashes(uint32_t) { return 0; }
void debugClock(uint64_t (*clock)()) { hostClock = clock; }

size_t debugIfacWrap(const uint8_t* raw, size_t length, uint8_t* wire) {
    if (!ifacOnline || length < 2 || length > p1iface::HW_MTU) return 0;
    return rnscore::ifacApply(ifac, raw, length, wire, p1iface::MAX_WIRE);
}

size_t debugIfacUnwrap(const uint8_t* wire, size_t length, uint8_t* raw) {
    if (!ifacOnline || length > p1iface::MAX_WIRE) return 0;
    return rnscore::ifacCheck(ifac, wire, length, raw, p1iface::MAX_WIRE);
}
#endif

}  // namespace rnsnode
