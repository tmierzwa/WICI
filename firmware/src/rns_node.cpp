// SPDX-License-Identifier: MIT
#include "rns_node.h"

#include <microReticulum.h>
#include <microReticulum/Cryptography/HKDF.h>

#include <new>
#include <stdio.h>
#include <string.h>

#ifdef ARDUINO
#include <Arduino.h>
#else
#include <chrono>
#endif

#include "framfs.h"
#include "p1iface.h"
#include "rns_framfs.h"

namespace rnsnode {

namespace {

// IFAC_SALT z Reticulum.py (e40191b).
const uint8_t IFAC_SALT[32] = {0xad, 0xf5, 0x4d, 0x88, 0x2c, 0x9a, 0x9b, 0x80, 0x77, 0x1e, 0xb4, 0x99, 0x5d, 0x70, 0x2d, 0x4a,
                               0x3e, 0x73, 0x33, 0x91, 0xb2, 0xa0, 0xf5, 0x3f, 0x41, 0x6d, 0x9f, 0x90, 0x7e, 0x55, 0xcf, 0xf8};

uint32_t nowMs() {
#ifdef ARDUINO
    return millis();
#else
    using namespace std::chrono;
    return static_cast<uint32_t>(duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count());
#endif
}

Hooks hooks;
Radio* radio = nullptr;
journal::Storage* fram = nullptr;
alignas(framfs::Fs) uint8_t fsMemory[sizeof(framfs::Fs)];
framfs::Fs* fs = nullptr;
bool started = false;
bool identityNew = false;
uint8_t addressBytes[HASH] = {};
uint8_t identityBytes[HASH] = {};
uint32_t nextHandle = 0;
uint32_t pending = 0;
uint32_t packetsSent = 0;
uint32_t packetsReceived = 0;
uint32_t packetsUnproven = 0;   // odrzucone przez warstwę aplikacji, bez dowodu
uint32_t delivered = 0;
uint32_t timedOut = 0;
uint32_t announcesSeen = 0;
// Cele OSP z konfiguracji (główna, zapasowa): ich tras i tożsamości limit tablic nie usuwa
// (microStore::pinned_key niżej, łata microStore 0001).
uint8_t pinned[2][HASH] = {};
// Węzeł OSP: interfejs USB do komputera stanowiska. Bufor KISS (około 5 KB) powstaje w puli
// stosu tylko w tej konfiguracji, więc stacja w schronieniu nie płaci za niego pamięcią.
bool nodeMode = false;
kiss::Port* usbPort = nullptr;
bool fromUsb = false;              // stos przetwarza pakiet z USB (pakiety wychodzące to ruch OSP)
uint8_t usbDest[USB_PINNED][HASH] = {};   // cele ogłoszone przez komputer (najnowsze zastępują najstarsze)
size_t usbDestCount = 0;
size_t usbDestNext = 0;

bool usbKnown(const uint8_t* dest) {
    if (!dest) return false;
    for (size_t i = 0; i < usbDestCount; ++i) if (!memcmp(usbDest[i], dest, HASH)) return true;
    return false;
}

void usbRemember(const uint8_t* dest) {
    if (!dest || usbKnown(dest)) return;
    memcpy(usbDest[usbDestNext], dest, HASH);
    usbDestNext = (usbDestNext + 1) % USB_PINNED;
    if (usbDestCount < USB_PINNED) ++usbDestCount;
}

void log(const char* text) {
    if (hooks.log) hooks.log(text, hooks.context);
}

void logFailure(const char* what, const std::exception& e) {
    char text[96];
    snprintf(text, sizeof(text), "rns: %s failed: %s", what, e.what());
    log(text);
}

class P1Interface : public RNS::InterfaceImpl {
public:
    P1Interface() : RNS::InterfaceImpl("P1") {
        _IN = true;
        _OUT = true;
        _HW_MTU = p1iface::HW_MTU;
        _bitrate = p1iface::declaredBitrate();
        _mode = RNS::Type::Interface::MODE_FULL;
    }

    // Kod dostępu jak Reticulum._add_interface z passphrase = 32 cyfry szesnastkowe klucza z konfiguracji.
    void setIfac(const uint8_t key[16]) {
        bool any = false;
        for (int i = 0; i < 16; ++i) any |= key[i] != 0;
        online_ = false;
        if (!any) { _online = false; return; }
        char passphrase[33];
        for (int i = 0; i < 16; ++i) snprintf(passphrase + 2 * i, 3, "%02x", key[i]);
        const RNS::Bytes origin = RNS::Identity::full_hash(RNS::Bytes(reinterpret_cast<const uint8_t*>(passphrase), 32));
        const RNS::Bytes originHash = RNS::Identity::full_hash(origin);
        ifacKey_ = RNS::Cryptography::hkdf(64, originHash, RNS::Bytes(IFAC_SALT, sizeof(IFAC_SALT)));
        ifacIdentity_ = RNS::Identity(false);
        if (!ifacIdentity_.load_private_key(ifacKey_)) { _online = false; return; }
        online_ = true;
        _online = true;
    }

    void receive(const uint8_t* wire, size_t length) {
        p1iface::Counters& c = queue_.counters();
        if (!online_) { ++c.offline; return; }
        if (!p1iface::ifacPresent(wire, length, p1iface::IFAC_SIZE)) { ++c.ifacMissing; return; }
        if (length > p1iface::MAX_WIRE) { ++c.tooLarge; return; }
        const RNS::Bytes tag(wire + 2, p1iface::IFAC_SIZE);
        const RNS::Bytes mask = RNS::Cryptography::hkdf(length, tag, ifacKey_);
        uint8_t raw[p1iface::MAX_WIRE];
        p1iface::ifacUnmask(wire, length, p1iface::IFAC_SIZE, mask.data(), raw);
        const RNS::Bytes packet(raw, length - p1iface::IFAC_SIZE);
        const RNS::Bytes signature = ifacIdentity_.sign(packet);
        if (signature.size() < p1iface::IFAC_SIZE ||
            memcmp(signature.data() + signature.size() - p1iface::IFAC_SIZE, wire + 2, p1iface::IFAC_SIZE) != 0) {
            ++c.ifacInvalid;
            return;
        }
        ++c.received;
        std::shared_ptr<RNS::InterfaceImpl> self = shared_from_this();
        RNS::Interface(self).handle_incoming(packet);
    }

    void loop() override {
        if (!radio) return;
        const uint32_t now = nowMs();
        queue_.poll(now);
        if (queue_.transmitting() || !radio->ready()) return;
        const uint8_t* data;
        size_t length;
        if (!queue_.start(data, length)) return;
        if (!radio->transmit(data, length)) queue_.finish(false);
    }

    void txDone(bool ok) { queue_.finish(ok); }

    p1iface::Queue& queue() { return queue_; }
    bool ifacOnline() const { return online_; }

protected:
    bool send_outgoing(const RNS::Bytes& raw) override {
        p1iface::Counters& c = queue_.counters();
        if (!online_) { ++c.offline; return false; }
        if (raw.size() < 2 || raw.size() > p1iface::HW_MTU) { ++c.tooLarge; return false; }
        const p1iface::Kind kind = p1iface::classify(raw.data(), raw.size());
        // Pełna kolejka: odmowa przed podpisem IFAC (ogłoszenia przekazywane mogą jeszcze czekać na liście).
        if (kind != p1iface::Kind::ANNOUNCE && queue_.full()) { ++c.full; return false; }
        const RNS::Bytes signature = ifacIdentity_.sign(raw);
        const uint8_t* tag = signature.data() + signature.size() - p1iface::IFAC_SIZE;
        const RNS::Bytes mask = RNS::Cryptography::hkdf(raw.size() + p1iface::IFAC_SIZE, RNS::Bytes(tag, p1iface::IFAC_SIZE), ifacKey_);
        uint8_t wire[p1iface::MAX_WIRE];
        p1iface::ifacMask(raw.data(), raw.size(), tag, p1iface::IFAC_SIZE, mask.data(), wire);
        const uint8_t hops = p1iface::pathResponse(raw.data(), raw.size()) ? 0 : raw.data()[1];
        const uint8_t* dest = p1iface::destination(raw.data(), raw.size());
        // Węzeł OSP: pakiet od komputera (w trakcie przetwarzania pakietu z USB) albo do celu
        // ogłoszonego przez komputer to ruch OSP, zwolniony z rezerwy (radio.md, „Limity”).
        const bool osp = nodeMode && (fromUsb || usbKnown(dest));
        const p1iface::Admit admit = queue_.offer(kind, hops, dest, wire, raw.size() + p1iface::IFAC_SIZE, nowMs(), osp);
        if (admit != p1iface::Admit::QUEUED && admit != p1iface::Admit::HELD) return false;
        handle_outgoing(raw);
        return true;
    }

private:
    p1iface::Queue queue_;
    RNS::Bytes ifacKey_;
    RNS::Identity ifacIdentity_{RNS::Type::NONE};
    bool online_ = false;
};

P1Interface* p1 = nullptr;

// Interfejs Reticulum przez USB (węzeł OSP): pakiety od komputera z bufora KISS do stosu, gdy
// kolejka P1 ma miejsce (inaczej czekają w buforze, a komputer na gotowość); pakiety, które
// transport kieruje do komputera, w ramkach KISS. Bez IFAC: kod dostępu dotyczy tylko P1.
class UsbInterface : public RNS::InterfaceImpl {
public:
    UsbInterface() : RNS::InterfaceImpl("USB") {
        _IN = true;
        _OUT = true;
        _HW_MTU = kiss::MTU;
        _bitrate = USB_BITRATE;
        _mode = RNS::Type::Interface::MODE_FULL;
    }

    void loop() override {
        if (!usbPort || !p1 || p1->queue().full()) return;
        const uint8_t* data;
        size_t length;
        if (!usbPort->peek(data, length)) return;
        const RNS::Bytes packet(data, length);
        usbPort->pop();
        // Ogłoszenie od komputera: cel chroniony w pełnych tablicach i ruch OSP w rezerwie P1.
        if (p1iface::classify(packet.data(), packet.size()) == p1iface::Kind::ANNOUNCE) {
            usbRemember(p1iface::destination(packet.data(), packet.size()));
        }
        struct Flag {
            Flag() { fromUsb = true; }
            ~Flag() { fromUsb = false; }
        } flag;
        std::shared_ptr<RNS::InterfaceImpl> self = shared_from_this();
        RNS::Interface(self).handle_incoming(packet);
    }

protected:
    bool send_outgoing(const RNS::Bytes& raw) override {
        if (!usbPort || !usbPort->send(raw.data(), raw.size())) return false;
        handle_outgoing(raw);
        return true;
    }

private:
    // Przepływność deklarowana stosowi: USB nie ogranicza ruchu, a limit ogłoszeń do komputera
    // (2% przepływności) nie może wstrzymywać ogłoszeń stacji sieci.
    static constexpr uint32_t USB_BITRATE = 1000000;
};

RNS::Interface iface(RNS::Type::NONE);
RNS::Interface usbIface(RNS::Type::NONE);
RNS::Reticulum reticulum(RNS::Type::NONE);
RNS::Identity identity(RNS::Type::NONE);
RNS::Destination destination(RNS::Type::NONE);

// Dowód pakietu (PROVE_APP): Transport wywołuje onProofRequested zaraz po onPacket dla tego
// samego pakietu, więc wynik warstwy aplikacji przechodzi przez zmienną.
bool lastAccepted = false;

void onPacket(const RNS::Bytes& data, const RNS::Packet&) {
    ++packetsReceived;
    lastAccepted = hooks.packet && hooks.packet(data.data(), data.size(), hooks.context);
    if (!lastAccepted) ++packetsUnproven;
}

bool onProofRequested(const RNS::Packet&) {
    const bool prove = lastAccepted;
    lastAccepted = false;
    return prove;
}

void onLog(const char* msg, RNS::LogLevel) { log(msg); }

class AnnounceHandler final : public RNS::AnnounceHandler {
public:
    AnnounceHandler() : RNS::AnnounceHandler("wici.sa1") {}
    void received_announce(const RNS::Bytes& destinationHash, const RNS::Identity&, const RNS::Bytes& appData) override {
        if (destinationHash.size() != HASH || !memcmp(destinationHash.data(), addressBytes, HASH)) return;
        ++announcesSeen;
        if (hooks.announce) hooks.announce(destinationHash.data(), appData.data(), appData.size(), hooks.context);
    }
};

RNS::HAnnounceHandler announceHandler;

}  // namespace

bool begin(journal::Storage& storage, Radio& r, const uint8_t ifac[16], uint64_t clockMs, const Hooks& h) {
    if (started) return true;
    hooks = h;
    radio = &r;
    fram = &storage;
    RNS::set_log_callback(onLog);
    try {
        fs = new (fsMemory) framfs::Fs(storage);
        if (!fs->mount()) { log("rns: FRAM file system mount failed"); return false; }
        microStore::FileSystem filesystem{new rnsfs::FramFileSystem(*fs)};
        RNS::Utilities::OS::register_filesystem(filesystem);

        uint8_t key[framfs::KEY_BYTES];
        if (framfs::loadKey(storage, key)) {
            identity = RNS::Identity(false);
            if (!identity.load_private_key(RNS::Bytes(key, sizeof(key)))) identity = RNS::Identity(RNS::Type::NONE);
        }
        memset(key, 0, sizeof(key));
        if (!identity) {
            identity = RNS::Identity();
            const RNS::Bytes prv = identity.get_private_key();
            if (prv.size() != framfs::KEY_BYTES || !framfs::saveKey(storage, prv.data())) {
                log("rns: identity not saved in FRAM");
                return false;
            }
            identityNew = true;
        }
        memcpy(identityBytes, identity.hash().data(), HASH);

        p1 = new P1Interface();
        p1->setIfac(ifac);
        p1->queue().setNodeReserve(nodeMode);
        iface = p1;
        RNS::Transport::register_interface(iface);
        iface.start();
        if (nodeMode) {
            usbPort = new kiss::Port();
            usbIface = new UsbInterface();
            RNS::Transport::register_interface(usbIface);
            usbIface.start();
        }

        reticulum = RNS::Reticulum();
        reticulum.transport_enabled(true);
        RNS::Transport::identity(identity);
        // Port ustawia limit tras tylko dla dawnej tablicy w RAM (cull_path_table), a trasy są
        // w magazynie microStore bez limitu; limit znanych tożsamości ustawia dopiero po wczytaniu
        // magazynu. Oba limity przed startem: wczytanie z FRAM usuwa nadmiar (poza celami OSP
        // z setOsp), więc wpisy usunięte w pracy nie wracają po restarcie.
        RNS::Transport::path_table_maxsize(RNS_PATH_TABLE_MAX);
        RNS::Identity::known_destinations_maxsize(RNS_KNOWN_DESTINATIONS_MAX);
        reticulum.start();
#ifdef ARDUINO
        // Zegar stosu = czas pracy z dziennika FRAM (Reticulum::start wczytuje przesunięcie z pliku
        // time_offset, które port odrzuca powyżej 2^32 ms, czyli po ok. 49 dniach pracy).
        // Przy pierwszym starcie (dziennik bez czasu pracy) clockMs jest o ułamek sekundy mniejsze
        // niż millis(): przesunięcie 0 zamiast zawinięcia do 2^64.
        const uint64_t nowMs = millis();
        RNS::Utilities::OS::setTimeOffset(clockMs > nowMs ? clockMs - nowMs : 0);
        microStore::set_time_offset(RNS::Utilities::OS::getTimeOffset() / 1000);
#else
        (void)clockMs;   // na komputerze stos używa zegara systemowego
#endif

        // Węzeł OSP nie ma adresu: bez celu "wici.sa1" (tożsamość służy tylko transportowi).
        if (!nodeMode) {
            destination = RNS::Destination(identity, RNS::Type::Destination::IN, RNS::Type::Destination::SINGLE, APP_NAME, ASPECT);
            destination.set_packet_callback(onPacket);
            destination.set_proof_strategy(RNS::Type::Destination::PROVE_APP);
            destination.set_proof_requested_callback(onProofRequested);
            memcpy(addressBytes, destination.hash().data(), HASH);
        }

        announceHandler = RNS::HAnnounceHandler(new AnnounceHandler());
        RNS::Transport::register_announce_handler(announceHandler);
        started = true;
        return true;
    } catch (const std::exception& e) {
        logFailure("start", e);
        return false;
    }
}

void setIfac(const uint8_t ifac[16]) {
    if (!p1) return;
    try {
        p1->setIfac(ifac);
    } catch (const std::exception& e) {
        logFailure("ifac", e);
    }
}

void setOsp(const uint8_t osp[2][HASH], uint8_t active) {
    memcpy(pinned, osp, sizeof(pinned));
    if (p1) p1->queue().setOsp(osp[active ? 1 : 0]);
}

void setOspNode(bool on) {
    if (!started) nodeMode = on;
}

bool ospNode() { return nodeMode; }

void usbOpen(bool open) {
    if (usbPort) usbPort->setOpen(open);
}

void usbFeed(const uint8_t* data, size_t length, uint32_t now) {
    if (usbPort) usbPort->feed(data, length, now);
}

size_t usbTake(uint8_t* out, size_t max) { return usbPort ? usbPort->take(out, max) : 0; }

UsbStatus usbStatus() {
    UsbStatus s;
    s.enabled = usbPort != nullptr;
    if (!usbPort) return s;
    s.open = usbPort->open();
    s.flowControl = usbPort->flowControl();
    s.buffered = usbPort->buffered();
    s.pinned = usbDestCount;
    s.counters = usbPort->counters();
    return s;
}

bool usbPinned(const uint8_t dest[HASH]) { return usbKnown(dest); }

size_t usbJson(char* out, size_t size) {
    const UsbStatus u = usbStatus();
    const kiss::Counters& c = u.counters;
    const int n = snprintf(out, size,
                           "\"osp_node\":%s,\"usb_open\":%s,\"usb_flow\":%s,\"usb_buffered\":%u,\"usb_pinned\":%u,"
                           "\"usb_rns_in\":%lu,\"usb_rns_out\":%lu,\"usb_rx_drop\":%lu,\"usb_rx_large\":%lu,\"usb_tx_drop\":%lu,"
                           "\"usb_ready\":%lu,\"usb_cmds\":%lu",
                           nodeMode ? "true" : "false", u.open ? "true" : "false", u.flowControl ? "true" : "false",
                           (unsigned)u.buffered, (unsigned)u.pinned, (unsigned long)c.fromComputer, (unsigned long)c.toComputer,
                           (unsigned long)c.rxDropped, (unsigned long)c.rxTooLarge, (unsigned long)c.txDropped,
                           (unsigned long)c.ready, (unsigned long)c.commands);
    return n < 0 ? 0 : (size_t)n;
}

void loop(uint32_t) {
    if (!started) return;
    try {
        reticulum.loop();
    } catch (const std::exception& e) {
        logFailure("loop", e);
    }
}

void received(const uint8_t* wire, size_t length) {
    if (!started || !p1) return;
    try {
        p1->receive(wire, length);
    } catch (const std::exception& e) {
        logFailure("inbound", e);
    }
}

void txDone(bool ok) {
    if (p1) p1->txDone(ok);
}

bool announce(const uint8_t* appData, size_t length) {
    if (!started || nodeMode) return false;
    try {
        // Pakiet bez wysyłki, żeby wynik mówił, czy interfejs P1 przyjął ogłoszenie (announce()
        // z send = true nie zwraca wyniku).
        RNS::Packet packet = destination.announce(RNS::Bytes(appData, length), false, {RNS::Type::NONE}, {}, false);
        if (!packet) return false;
        packet.receipt_send();
        return packet.sent();
    } catch (const std::exception& e) {
        logFailure("announce", e);
        return false;
    }
}

bool knows(const uint8_t dest[HASH]) {
    if (!started) return false;
    try {
        return (bool)RNS::Identity::recall(RNS::Bytes(dest, HASH));
    } catch (const std::exception& e) {
        logFailure("recall", e);
        return false;
    }
}

bool hasPath(const uint8_t dest[HASH]) {
    if (!started) return false;
    try {
        return RNS::Transport::has_path(RNS::Bytes(dest, HASH));
    } catch (const std::exception& e) {
        logFailure("path lookup", e);
        return false;
    }
}

void requestPath(const uint8_t dest[HASH]) {
    if (!started) return;
    try {
        RNS::Transport::request_path(RNS::Bytes(dest, HASH));
    } catch (const std::exception& e) {
        logFailure("path request", e);
    }
}

uint32_t send(const uint8_t dest[HASH], const uint8_t* data, size_t length, uint32_t timeoutS) {
    if (!started || nodeMode || !p1 || !p1->ifacOnline() || p1->queue().full()) return 0;
    try {
        const RNS::Bytes hash(dest, HASH);
        const RNS::Identity remote = RNS::Identity::recall(hash);
        if (!remote) {
            RNS::Transport::request_path(hash);
            return 0;
        }
        RNS::Destination out(remote, RNS::Type::Destination::OUT, RNS::Type::Destination::SINGLE, APP_NAME, ASPECT);
        if (out.hash() != hash) return 0;
        RNS::Packet packet(out, RNS::Bytes(data, length));
        RNS::PacketReceipt receipt = packet.receipt_send();
        if (!receipt) return 0;
        const uint32_t handle = ++nextHandle ? nextHandle : ++nextHandle;
        ++packetsSent;
        ++pending;
        // Limit od przekazania do stosu (radio.md, "Interfejs P1 w stosie Reticulum"):
        // max(60 s, 2 × skoki × 13 × czas TX największego datagramu + dług ciszy + kolejka P1).
        // Trasa nieznana (pakiet rozgłaszany) liczy się jako 1 skok.
        uint32_t hops = RNS::Transport::hops_to(hash);
        if (hops == 0 || hops >= RNS::Type::Transport::PATHFINDER_M) hops = 1;
        const uint64_t waitMs = static_cast<uint64_t>(2) * hops * (1 + p1iface::DEBT_FACTOR) *
                                    p1iface::airtimeMs(p1frame::MAX_DATAGRAM) + queueWaitMs();
        uint64_t limit = (waitMs + 999) / 1000;
        if (limit < timeoutS) limit = timeoutS;
        if (limit < RECEIPT_MIN_S) limit = RECEIPT_MIN_S;
        if (limit > 32767) limit = 32767;
        receipt.set_timeout(static_cast<int16_t>(limit));
        receipt.set_delivery_handler([handle](const RNS::PacketReceipt&) {
            ++delivered;
            if (pending) --pending;
            if (hooks.receipt) hooks.receipt(handle, true, hooks.context);
        });
        receipt.set_timeout_handler([handle](const RNS::PacketReceipt&) {
            ++timedOut;
            if (pending) --pending;
            if (hooks.receipt) hooks.receipt(handle, false, hooks.context);
        });
        return handle;
    } catch (const std::exception& e) {
        logFailure("send", e);
        return 0;
    }
}

bool queueFull() { return !p1 || p1->queue().full(); }

bool online() { return started && p1 && p1->ifacOnline(); }

uint32_t queueWaitMs() { return p1 && radio ? p1->queue().waitMs(radio->debtMs()) : 0; }

const uint8_t* address() { return addressBytes; }
const uint8_t* identityHash() { return identityBytes; }

Status status() {
    Status s;
    s.started = started;
    s.identityNew = identityNew;
    s.bitrate = p1iface::declaredBitrate();
    if (!started) return s;
    s.online = p1 && p1->ifacOnline();
    s.paths = RNS::Transport::new_path_table().size();
    s.packetHashes = RNS::Transport::packet_hashlist().size();
    s.announceTable = RNS::Transport::announce_table().size();
    s.receiptsPending = pending;
    s.poolSize = RNS::Utilities::Memory::heap_pool_size();
    s.poolUsed = RNS::Utilities::Memory::heap_pool_used();
    s.poolPeak = RNS::Utilities::Memory::heap_pool_peak();
    if (fs) {
        s.fsFiles = fs->stats().files;
        s.fsCapacityBytes = fs->capacityBytes();
        s.fsUsedBytes = fs->capacityBytes() - fs->freeBytes();
    }
    s.packetsSent = packetsSent;
    s.packetsReceived = packetsReceived;
    s.packetsUnproven = packetsUnproven;
    s.delivered = delivered;
    s.timedOut = timedOut;
    s.announcesSeen = announcesSeen;
    s.queueWaitMs = queueWaitMs();
    s.announceWaitMs = p1 ? p1->queue().announceAllowedInMs(nowMs()) : 0;
    return s;
}

size_t interfaceJson(char* out, size_t size) {
    if (!p1) return snprintf(out, size, "\"p1_iface\":false");
    const p1iface::Counters& c = p1->queue().counters();
    const int n = snprintf(out, size,
                           "\"q_len\":%u,\"q_held\":%u,\"q_queued\":%lu,\"q_full\":%lu,\"too_large\":%lu,\"ann_held\":%lu,"
                           "\"ann_drop\":%lu,\"ann_expired\":%lu,\"tx_sent\":%lu,\"tx_failed\":%lu,\"rx_ok\":%lu,"
                           "\"ifac_missing\":%lu,\"ifac_invalid\":%lu,\"offline\":%lu,\"q_reserved\":%lu,\"other_ms\":%lu",
                           (unsigned)p1->queue().queued(), (unsigned)p1->queue().held(), (unsigned long)c.queued,
                           (unsigned long)c.full, (unsigned long)c.tooLarge, (unsigned long)c.announcesHeld,
                           (unsigned long)c.announcesDropped, (unsigned long)c.announcesExpired, (unsigned long)c.sent,
                           (unsigned long)c.sendFailed, (unsigned long)c.received, (unsigned long)c.ifacMissing,
                           (unsigned long)c.ifacInvalid, (unsigned long)c.offline, (unsigned long)c.reserved,
                           (unsigned long)p1->queue().otherUsedMs(nowMs()));
    return n < 0 ? 0 : (size_t)n;
}

bool wipe() {
    // Stos staje przed formatowaniem: okresowy zapis tablic nie odtworzy ich w FRAM, a interfejs
    // przestaje nadawać ze starą tożsamością. Nowa tożsamość powstaje przy następnym starcie.
    started = false;
    identityNew = false;
    memset(addressBytes, 0, sizeof(addressBytes));    // adres i nazwa nie wskazują skasowanej tożsamości
    memset(identityBytes, 0, sizeof(identityBytes));
    if (p1) {
        const uint8_t none[16] = {};
        p1->setIfac(none);
    }
    bool ok = fram && framfs::wipeKey(*fram);
    if (fs) ok = fs->format(true) && ok;   // także treść tras, tożsamości i ogłoszeń
    return ok;
}

void persist() {
    if (!started) return;
    try {
        RNS::Transport::persist_data();
    } catch (const std::exception& e) {
        logFailure("persist", e);
    }
}

#ifndef ARDUINO
void debugTableMax(uint16_t n) {
    RNS::Transport::path_table_maxsize(n);
    RNS::Identity::known_destinations_maxsize(n);
}

uint32_t debugFillHashes(uint32_t n) {
    if (!started) return 0;
    for (uint32_t i = 0; i < n; ++i) RNS::Transport::add_packet_hash(RNS::Identity::get_random_hash());
    return n;
}
#endif

}  // namespace rnsnode

namespace microStore {

bool pinned_key(const uint8_t* key, size_t length) {
    if (length != rnsnode::HASH) return false;
    static const uint8_t zero[rnsnode::HASH] = {};
    for (const auto& dest : rnsnode::pinned) {
        if (memcmp(dest, zero, rnsnode::HASH) && !memcmp(dest, key, rnsnode::HASH)) return true;
    }
    return rnsnode::usbKnown(key);   // węzeł OSP: cele ogłoszone przez komputer stanowiska
}

}  // namespace microStore
