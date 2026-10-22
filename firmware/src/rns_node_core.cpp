// SPDX-License-Identifier: MIT
// Węzeł Reticulum stacji na rdzeniu (firmware/reticulum-core.md), wersja etapu R0: ten sam interfejs
// rns_node.h co port, w programie na komputerze (env:host-core). Działa tożsamość: ten sam rekord
// klucza w FRAM co w porcie (framfs::loadKey, 64 B w kolejności Reticulum), więc stacja zachowuje
// tożsamość i adres przy przejściu z portu na rdzeń (decyzja z 2026-10-22). Interfejsu P1, ogłoszeń,
// pakietów, tras i USB jeszcze nie ma (etapy R1–R4): funkcje odpowiadają jak stos bez interfejsu
// (fałsz, 0, brak trasy), status.online jest fałszywy.
#include <stdio.h>
#include <string.h>

#include <Crypto.h>

#include "destination.h"
#include "drbg.h"
#include "framfs.h"
#include "identity.h"
#include "p1iface.h"
#include "rns_node.h"

namespace rnsnode {

namespace {

bool started = false;
bool identityNew = false;
bool identityLost = false;
bool nodeMode = false;
Hooks hooks;
uint8_t privateKey[rnscore::KEY_SIZE];
uint8_t publicKeyBytes[rnscore::KEY_SIZE];
uint8_t identityBytes[HASH];
uint8_t addressBytes[HASH];

void log(const char* text) {
    if (hooks.log) hooks.log(text, hooks.context);
}

}  // namespace

bool begin(journal::Storage& storage, Radio&, const uint8_t[16], uint64_t, bool identitySaved, const uint8_t seed[32],
           const Hooks& h) {
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
        drbg::Drbg generator;
        static const char nonce[] = "WICI rnscore identity";
        generator.seed(seed, 32, reinterpret_cast<const uint8_t*>(nonce), sizeof(nonce) - 1);
        const bool generated = generator.generate(privateKey, sizeof(privateKey));
        clean(&generator, sizeof(generator));   // stan generatora po kluczu (odporny wstecz, ale nie zostaje)
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
    // Węzeł stanowiska nie ma adresu (jak w porcie): bez celu "wici.sa1", tożsamość tylko dla transportu.
    if (!nodeMode) {
        char name[32];
        snprintf(name, sizeof(name), "%s.%s", APP_NAME, ASPECT);   // cel SINGLE "wici.sa1" stacji
        rnscore::destinationHash(name, identityBytes, addressBytes);
    }
    started = true;
    log("rns: Reticulum core (R0): identity only, no interface yet");
    return true;
}

void setIfac(const uint8_t[16]) {}
void setReceivers(const uint8_t[2][64], const uint8_t[2][HASH], uint8_t) {}
void setNode(bool on) {
    if (!started) nodeMode = on;   // jak w porcie: zmiana działa po restarcie
}
bool node() { return nodeMode; }
void setSilence(Silence) {}
void dropQueue() {}

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
void loop(uint32_t) {}
void received(const uint8_t*, size_t) {}
void txDone(bool) {}

bool announce(const uint8_t*, size_t) { return false; }
uint32_t send(const uint8_t[HASH], const uint8_t*, size_t, uint32_t) { return 0; }
bool sendReady(const uint8_t[HASH]) { return false; }
bool knows(const uint8_t[HASH]) { return false; }
bool hasPath(const uint8_t[HASH]) { return false; }
void requestPath(const uint8_t[HASH]) {}
bool queueFull() { return false; }
bool online() { return false; }
uint32_t queueWaitMs() { return 0; }

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
    return s;
}

size_t interfaceJson(char* out, size_t size) {
    const int n = snprintf(out, size, "\"p1_iface\":false");
    return n > 0 ? static_cast<size_t>(n) : 0;
}

void halt() {
    // Jak w porcie: stos staje, adres i skrót nie wskazują kasowanej tożsamości; klucz znika też z RAM.
    started = false;
    identityNew = false;
    clean(privateKey, sizeof(privateKey));
    memset(publicKeyBytes, 0, sizeof(publicKeyBytes));
    memset(addressBytes, 0, sizeof(addressBytes));
    memset(identityBytes, 0, sizeof(identityBytes));
}

void persist() {}

#ifndef ARDUINO
void debugTableMax(uint16_t) {}
uint32_t debugFillHashes(uint32_t) { return 0; }
void debugClock(uint64_t (*)()) {}
size_t debugIfacWrap(const uint8_t*, size_t, uint8_t*) { return 0; }
size_t debugIfacUnwrap(const uint8_t*, size_t, uint8_t*) { return 0; }
#endif

}  // namespace rnsnode
