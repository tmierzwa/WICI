// SPDX-License-Identifier: MIT
// Wykonanie emulatora; założenia opisuje README.md, a wejście to scenarios.cpp.
#include "emulator.h"

namespace emu {
namespace {

// X25519 z surowego klucza prywatnego, jak w configdoc.py.
void x25519Public(const uint8_t secret[32], uint8_t out[32]) {
    uint8_t scalar[32];
    memcpy(scalar, secret, 32);
    scalar[0] &= 0xf8;
    scalar[31] = static_cast<uint8_t>((scalar[31] & 0x7f) | 0x40);
    Curve25519::eval(out, scalar, nullptr);
}
constexpr uint32_t HACK_DEADLINE_MS = 200;
constexpr uint32_t CCA_MS = 50;
constexpr uint32_t BACKOFF_MIN_MS = 100, BACKOFF_MAX_MS = 1000;
constexpr uint32_t MAX_DEFERRALS = 30;
constexpr uint32_t DEBT_FACTOR = 12;
constexpr uint32_t MAX_DEBT_MS = lora::SERIES_MAX_MS * DEBT_FACTOR;

wici_link::Type frameType(const uint8_t* wire) { return static_cast<wici_link::Type>((wire[0] >> 3) & 7); }

bool isAckRequested(const uint8_t* wire) {
    return (wire[0] >> 6) == wici_link::VERSION && frameType(wire) == wici_link::Type::DATA && (wire[0] & wici_link::ACKREQ);
}

// Jak Station::retryDelayS, bez przebiegu „po 6 h”, który obsługuje wiek.
uint32_t stationRetry(uint32_t attempts, uint32_t ageS, uint32_t random) {
    const uint32_t jitter = 80 + random % 41;
    if (ageS >= 6 * 3600) return 3600 * jitter / 100;
    static const uint32_t steps[] = {60, 120, 300, 900};
    const uint32_t index = attempts ? attempts - 1 : 0;
    return steps[index < 4 ? index : 3] * jitter / 100;
}

uint32_t randomContext(void* context) { return static_cast<Node*>(context)->rng.next(); }

const uint8_t* beaconKey(uint16_t sender, const void* context) {
    const Node& node = *static_cast<const Node*>(context);
    for (const config::PriorityKey& peer : node.peers)
        if (peer.station == sender) return peer.ed25519;
    return nullptr;
}

void onDelivery(uint32_t handle, bool acknowledged, void* context);

bool onAdmit(uint16_t, uint16_t, uint16_t, const uint8_t* content, size_t length, void* context) {
    Node& node = *static_cast<Node*>(context);
    node.lastReceiverMsgS = node.net->nowS();
    node.leaveTimerS = 0;  // odbiorca odpowiada; stoper rusza od nowa przy kolejnej otwartej wiadomości
    node.upWaitS = 0;
    if (length < 4) return true;
    const uint32_t id = get32(content);
    for (Report* report : node.reports)
        if (!node.net->variant().perMessage || report->id == id) report->hacked = 0;
    if (id & 0x80000000u) node.net->downArrivedMs.emplace(id, node.net->now());
    else node.net->reportClosed(id, node.net->now());
    return true;
}

void finishFlight(Node& node, Node::Flight& flight, bool delivered) {
    Report* report = flight.report;
    flight = Node::Flight();
    if (!report || report->closed) return;
    const uint32_t nowS = node.net->nowS();
    if (delivered) {
        const bool first = !report->delivered;
        ++report->hacked;
        const uint32_t random = node.rng.next();
        report->nextTryS = nowS + (first ? 600 : 1800 + random % 1801);
        if (first) {
            report->delivered = true;
            report->firstHackMs = node.net->now();
        }
    } else {
        const uint32_t random = node.rng.next();
        report->nextTryS = nowS + stationRetry(report->attempts, report->firstSentS ? nowS - report->firstSentS : 0, random);
    }
}

void onDelivery(uint32_t handle, bool acknowledged, void* context) {
    Node& node = *static_cast<Node*>(context);
    for (Node::Flight& flight : node.flights)
        if (flight.report && flight.handle == handle) { finishFlight(node, flight, acknowledged); return; }
}

}  // namespace

bool Node::Check::start(void (*run)(void*), void* context) {
    if (job) return false;
    job = run;
    argument = context;
    dueMs = net->now() + net->assumptions().beaconCheckMs;
    return true;
}

// --- Radio ---------------------------------------------------------------------------------------------

bool Radio::accepts(wici_link::TxClass traffic, size_t radioLength) {
    if (silent || state_ != State::IDLE) return false;
    if (traffic == wici_link::TxClass::OWN || net_.variant().noPool) return true;
    return budget_.allows(traffic == wici_link::TxClass::BEACON, lora::frameAirMs(radioLength), net_.nowS(),
                          traffic == wici_link::TxClass::CONTENDED_K2);
}

bool Radio::sendData(const uint8_t* wire, size_t length, wici_link::TxClass traffic) {
    Node& self = net_.node(index_);
    if (silent || state_ != State::IDLE || !wire || length < wici_link::HEADER + wici_link::TAG) return false;
    const bool beacon = traffic == wici_link::TxClass::BEACON;
    if (frameType(wire) != (beacon ? wici_link::Type::BEACON : wici_link::Type::DATA)) return false;
    uint8_t radio[wici_link::MAX_FRAME];
    const size_t radioLength = auth_.seal(wire, length, radio, sizeof(radio));
    if (!radioLength) return false;
    const bool flood = !beacon && traffic != wici_link::TxClass::OWN && get16(wire + 5) == wici_link::BROADCAST;
#ifdef WICI_EMU_VARIANT
    const bool overCap = net_.k1Stats && flood && self.shelter && self.shelter->routedK1Waiting(net_.nowS()) &&
                         !budget_.allows(false, lora::frameAirMs(radioLength), net_.nowS(), true);
#else
    const bool overCap = false;
#endif
    if (traffic != wici_link::TxClass::OWN && !net_.variant().noPool &&
        !budget_.reserve(beacon, lora::frameAirMs(radioLength), net_.nowS(), traffic == wici_link::TxClass::CONTENDED_K2)) {
        ++self.stats.refusedBudget;
        if (!beacon && !flood) ++self.stats.unicastRefused;
        const uint32_t mute = (net_.now() - self.lastTxMs) / 1000;
        if (mute > self.stats.longestMuteS) self.stats.longestMuteS = mute;
        if (net_.trace) fprintf(stderr, "%u R %d %d %u %u\n", net_.now(), index_, static_cast<int>(traffic), mute, get16(wire + 5));
        return false;
    }
    if (net_.k1Stats && !beacon && traffic != wici_link::TxClass::OWN) {
        std::array<uint8_t, 9> header;
        memcpy(header.data(), wire + wici_link::HEADER, header.size());
        net_.forwardedCopies.insert({self.id, header});
    }
    if (overCap) {
        ++self.stats.floodOverCap;
        self.stats.floodOverCapMs += lora::frameAirMs(radioLength);
    }
    if (flood) {
        const uint32_t window = net_.nowS() / 120;
        if (window != self.stats.floodWindow) self.stats.floodsInWindow = 0;
        self.stats.floodWindow = window;
        self.stats.maxFloods120S = std::max(self.stats.maxFloods120S, ++self.stats.floodsInWindow);
    }
    memcpy(frame_, radio, radioLength);
    length_ = radioLength;
    deferrals_ = 0;
    const uint32_t now = net_.now();
    if (debtLeft(now)) state_ = State::WAIT_DEBT;
    else startListen(now, true);
    return true;
}

bool Radio::sendHack(const uint8_t* wire, size_t length, uint32_t receivedMs) {
    Node& self = net_.node(index_);
    const uint32_t now = net_.now();
    uint8_t radio[wici_link::MAX_FRAME];
    const size_t radioLength = auth_.seal(wire, length, radio, sizeof(radio));
    if (!radioLength || silent) { ++self.stats.hackRefused; return false; }
    const uint32_t txMs = lora::frameAirMs(radioLength);
    if (now - receivedMs > HACK_DEADLINE_MS - txMs - 20) { ++self.stats.hackRefused; return false; }
    // W firmware pętla stoi w nadawaniu, więc HACK nie zaczyna się w trakcie nadawania DATA; tu wynik jest ten sam.
    if (state_ == State::SENDING || now < hackUntil_ || net_.rxPending(index_)) { ++self.stats.hackRefused; return false; }
    if (net_.hearsNow(index_) && !net_.rng().chance(net_.assumptions().senseMissPermille)) {
        ++self.stats.hackRefused;
        return false;
    }
    const uint32_t remaining = debtLeft(now);
    const uint32_t extra = txMs * (DEBT_FACTOR + 1);
    if (extra > MAX_DEBT_MS || remaining > MAX_DEBT_MS - extra) { ++self.stats.hackRefused; return false; }
    const uint32_t proc = self.isRoot ? net_.assumptions().rootHackProcMs : net_.assumptions().hackProcMs;
    net_.startAir(index_, radio, radioLength, true, now + proc);
    hackUntil_ = now + proc + txMs;
    debtUntil_ = hackUntil_ + remaining + txMs * DEBT_FACTOR;
    if (state_ != State::IDLE) state_ = State::WAIT_DEBT;
    return true;
}

void Radio::holdForHack(uint32_t now, uint32_t receivedMs) {
    const uint32_t until = receivedMs + HACK_DEADLINE_MS - lora::frameAirMs(wici_link::RADIO_HACK);
    if (until > now && until > hackHoldUntil_) hackHoldUntil_ = until;
}

void Radio::startListen(uint32_t now, bool) {
    state_ = State::LISTEN;
    listenStart_ = now;
}

void Radio::defer(uint32_t now) {
    Node& self = net_.node(index_);
    ++self.stats.deferrals;
    if (++deferrals_ > MAX_DEFERRALS) {
        ++self.stats.txDrops;
        state_ = State::IDLE;
        if (self.shelter) self.shelter->onTxDone(false, now, net_.nowS());
        else if (self.root) self.root->onTxDone(false, now);
        return;
    }
    backoffUntil_ = now + net_.node(index_).rng.range(BACKOFF_MIN_MS, BACKOFF_MAX_MS);
    state_ = State::BACKOFF;
}

bool Radio::channelBusy(uint32_t now) {
    if (now < hackHoldUntil_ || net_.rxPending(index_)) return true;
    const uint32_t last = net_.lastActivity(index_);
    if (last && now - last < CCA_MS) return true;
    return net_.hearsNow(index_) && !net_.rng().chance(net_.assumptions().senseMissPermille);
}

void Radio::beginTx(uint32_t now) {
    state_ = State::SENDING;
    net_.startAir(index_, frame_, length_, false, now);
}

void Radio::txEnded(uint32_t now) {
    Node& self = net_.node(index_);
    debtUntil_ = now + lora::frameAirMs(length_) * DEBT_FACTOR;
    lastTxEnd_ = now;
    state_ = State::IDLE;
    if (self.shelter) self.shelter->onTxDone(true, now, net_.nowS());
    else if (self.root) self.root->onTxDone(true, now);
}

void Radio::poll(uint32_t now) {
    switch (state_) {
        case State::WAIT_DEBT:
            if (!debtLeft(now) && now >= hackUntil_) startListen(now, true);
            return;
        case State::BACKOFF:
            if (now >= backoffUntil_) startListen(now, false);
            return;
        case State::LISTEN:
            if (now - lastTxEnd_ < CCA_MS || now < hackUntil_) return;
            if (channelBusy(now)) { defer(now); return; }
            state_ = State::CAD;
            cadEnd_ = now + net_.assumptions().cadMs;
            return;
        case State::CAD:
            if (now < cadEnd_) return;
            if (net_.rxPending(index_) || (net_.hearsNow(index_) && !net_.rng().chance(net_.assumptions().senseMissPermille))) {
                defer(now);
                return;
            }
            beginTx(now);
            return;
        case State::IDLE:
        case State::SENDING:
            return;
    }
}

// --- Sieć ----------------------------------------------------------------------------------------------

Net::Net(size_t count, uint64_t seed, Assumptions assumptions, Variant variant)
    : assumptions_(assumptions), variant_(variant), rng_(seed) {
    for (unsigned i = 0; i < 16; ++i) ifac_[i] = static_cast<uint8_t>(i + 1);
    assert(wici_link::deriveKey(ifac_, NETWORK, linkKey_));
    for (unsigned i = 0; i < 32; ++i) receiverSecret_[i] = static_cast<uint8_t>(i + 64);
    x25519Public(receiverSecret_, receiverPublic_);
    links_.assign(count, std::vector<LinkInfo>(count));
    rx_.assign(count, Rx());
    for (size_t index = 0; index < count; ++index) {
        auto node = std::make_unique<Node>();
        node->net = this;
        node->index = static_cast<int>(index);
        node->id = static_cast<uint16_t>(index + 1);
        node->isRoot = index == 0;
        node->rng = Rng(seed * 1000003u + index + 1);
        for (unsigned i = 0; i < 32; ++i) {
            node->secret[i] = static_cast<uint8_t>(i * 3 + index + 1);
            node->secret[i + 32] = static_cast<uint8_t>(i * 5 + index * 7 + 2);
        }
        x25519Public(node->secret, node->xPublic);
        Ed25519::derivePublicKey(node->edPublic, node->secret + 32);
        node->fram = std::make_unique<Fram>();
        node->budget = std::make_unique<wici_airtime::Budget>(*node->fram);
        node->radio = std::make_unique<Radio>(*this, node->index, *node->fram, node->auth, *node->budget);
        node->check.net = this;
        nodes_.push_back(std::move(node));
    }
}

Net::~Net() = default;

void Net::link(int a, int b, uint32_t permille) {
    links_[static_cast<size_t>(a)][static_cast<size_t>(b)] = {static_cast<uint16_t>(permille), true};
    links_[static_cast<size_t>(b)][static_cast<size_t>(a)] = {static_cast<uint16_t>(permille), true};
}

void Net::interfere(int a, int b) { link(a, b, 0); }

void Net::setLinkPermille(int a, int b, uint32_t permille) {
    links_[static_cast<size_t>(a)][static_cast<size_t>(b)].permille = static_cast<uint16_t>(permille);
    links_[static_cast<size_t>(b)][static_cast<size_t>(a)].permille = static_cast<uint16_t>(permille);
}

void Net::setAudible(int a, int b, bool audible) {
    links_[static_cast<size_t>(a)][static_cast<size_t>(b)].audible = audible;
    links_[static_cast<size_t>(b)][static_cast<size_t>(a)].audible = audible;
}

void Net::setParents(int station, int planned, int backup) {
    Node& s = node(station);
    s.planned = node(planned).id;
    s.backup = backup >= 0 ? node(backup).id : 0;
}

void Net::rootPlan(uint16_t station, uint16_t via) { node(0).behind.push_back({station, via}); }

namespace {
void addKey(Node& to, const Node& peer) {
    for (const config::PriorityKey& known : to.peers) if (known.station == peer.id) return;
    assert(to.peers.size() < config::PRIORITY_KEYS_MAX);
    config::PriorityKey key;
    key.station = peer.id;
    memcpy(key.ed25519, peer.edPublic, 32);
    memcpy(key.x25519, peer.xPublic, 32);
    to.peers.push_back(key);
}
}  // namespace

void Net::addPeer(int a, int b) {
    addKey(node(a), node(b));
    addKey(node(b), node(a));
}

void Net::start() {
    const uint16_t receivers[2] = {RECEIVER_MAIN, RECEIVER_BACKUP};
    uint8_t receiverPublic[2][32];
    memcpy(receiverPublic[0], receiverPublic_, 32);
    memcpy(receiverPublic[1], receiverPublic_, 32);
    // Klucze par: najpierw rodzice i root (dokument configure ich wymaga), potem sąsiedzi z łącza, do limitu 50.
    for (auto& holder : nodes_) {
        Node& n = *holder;
        if (n.isRoot) continue;
        addKey(n, node(0));  // każda stacja zna klucze roota; root tylko sąsiadów z planu, stąd bez wpisu w drugą stronę
        if (n.planned) addPeer(n.index, indexOf(n.planned));
        if (n.backup) addPeer(n.index, indexOf(n.backup));
    }
    for (size_t a = 0; a < nodes_.size(); ++a) {
        for (size_t b = a + 1; b < nodes_.size(); ++b) {
            if (!links_[a][b].permille || nodes_[a]->peers.size() >= config::PRIORITY_KEYS_MAX ||
                nodes_[b]->peers.size() >= config::PRIORITY_KEYS_MAX) continue;
            addPeer(static_cast<int>(a), static_cast<int>(b));
        }
    }
    for (auto& holder : nodes_) {
        Node& n = *holder;
        assert(n.budget->begin(NETWORK, n.id));
        assert(envelope::startCounters(*n.fram));
        n.check.net = this;
        assert(n.auth.begin(NETWORK, n.id, n.secret, n.peers.data(), static_cast<uint8_t>(n.peers.size())));
        if (n.isRoot) {
            n.port = std::make_unique<kiss::Port>();
            n.root = std::make_unique<wici_gateway::Root>(*n.fram, *n.port, *n.radio, NETWORK, n.id, ifac_, n.secret,
                                                         n.peers.data(), static_cast<uint8_t>(n.peers.size()),
                                                         n.behind.data(), static_cast<uint16_t>(n.behind.size()));
            assert(n.root->begin(static_cast<uint16_t>(epochSeed)));
        } else {
            if (n.dropper && !n.planned) continue;
            n.shelter = std::make_unique<wici_radio::Shelter>(
                *n.fram, wici_route::Config{NETWORK, n.id, ROOT_ID, n.planned, n.backup}, static_cast<uint8_t>(ttl), receivers,
                ifac_, n.secret, receiverPublic, onAdmit, &n, *n.radio, randomContext, &n, nullptr, static_cast<uint16_t>(0),
                node(0).edPublic, beaconKey, &n, n.peers.data(), static_cast<uint8_t>(n.peers.size()));
            n.shelter->onDelivery(onDelivery, &n);
            n.shelter->useBeaconCheck(&n.check, nullptr);
            assert(n.shelter->begin());
            n.lastParent = n.shelter->routes().parent();
        }
        n.nextBeaconMs = 1000 + n.rng.next() % 4000;
    }
    laptop_ = std::make_unique<Laptop>(*this, node(0));
    laptop_->setOpen(true);
}

void Net::restartRoot(uint16_t epoch) {
    Node& n = node(0);
    assert(n.root->begin(epoch));
    laptop_->setOpen(true);
    if (wici_beacon::burstAllowed(now_, n.lastBeaconMs, n.lastBeaconMs != 0)) {
        n.nextBeaconMs = now_ + 1000 + n.rng.next() % 4000;
        n.beacons = 0;
    }
}

void Net::leave(Node& n, uint32_t nowSeconds) {
#ifdef WICI_EMU_VARIANT
    n.shelter->routes().leaveParent(nowSeconds, variant_.holdS);
#endif
    ++n.stats.leaves;
    if (!n.stats.firstLeaveMs) n.stats.firstLeaveMs = now_;
    if (trace) fprintf(stderr, "%u LEAVE %d\n", now_, n.index);
    n.leaveTimerS = nowSeconds;
    for (Report* report : n.reports) report->hacked = 0;
}

bool Net::allClosed() const {
    for (const auto& report : reports_) if (!report->probe && !report->closed) return false;
    return true;
}

size_t Net::realReports() const {
    size_t count = 0;
    for (const auto& report : reports_) count += !report->probe;
    return count;
}

Report* Net::report(int station, size_t size) {
    auto report = std::make_unique<Report>();
    report->id = nextReportId_++;
    report->createdMs = now_;
    report->nextTryS = nowS();
    report->station = node(station).id;
    report->size = size;
    if (trace) fprintf(stderr, "%u NEW %u %d\n", now_, report->id, station);
    Report* raw = report.get();
    reports_.push_back(std::move(report));
    node(station).reports.push_back(raw);
    return raw;
}

void Net::reportArrived(uint32_t reportId, uint32_t now) {
    if (reportId && reportId <= reports_.size() && reports_[reportId - 1]->probe) return;
    if (arrivedMs.emplace(reportId, now).second) {
        ++arrivedCount;
        if (trace) fprintf(stderr, "%u ARR %u\n", now, reportId);
    }
}

void Net::reportClosed(uint32_t reportId, uint32_t now) {
    if (!reportId || reportId > reports_.size()) return;
    Report& report = *reports_[reportId - 1];
    if (report.closed) return;
    report.closed = true;
    report.closedMs = now;
    if (trace) fprintf(stderr, "%u CLS %u\n", now, reportId);
    const size_t bucket = now / 600000;
    if (closedPerBucket.size() <= bucket) closedPerBucket.resize(bucket + 1);
    ++closedPerBucket[bucket];
}

void Net::startAir(int from, const uint8_t* bytes, size_t length, bool isHack, uint32_t startMs) {
    Air air;
    air.from = from;
    air.startMs = startMs;
    air.endMs = startMs + lora::frameAirMs(length);
    air.bytes.assign(bytes, bytes + length);
    air.isHack = isHack;
    air.id = nextAirId_++;
    pendingStart_.push_back(std::move(air));
}

void Net::stepAir() {
    // Starty: najpierw blokada nadajnika, potem co słyszą inni.
    for (size_t i = 0; i < pendingStart_.size();) {
        if (pendingStart_[i].startMs > now_) { ++i; continue; }
        Air air = std::move(pendingStart_[i]);
        pendingStart_.erase(pendingStart_.begin() + static_cast<long>(i));
        Node& sender = node(air.from);
        const uint32_t airMs = air.endMs - air.startMs;
        sender.stats.airMs += airMs;
        sender.lastTxMs = now_;
        if (air.isHack) {
            ++sender.stats.txHack;
            ++hacksOnAir;
            if (trackStall && lastHackMs && now_ - lastHackMs > longestStallMs) longestStallMs = now_ - lastHackMs;
            lastHackMs = now_;
            const size_t bucket = now_ / 600000;
            if (hacksPerBucket.size() <= bucket) hacksPerBucket.resize(bucket + 1);
            ++hacksPerBucket[bucket];
        } else if (frameType(air.bytes.data()) == wici_link::Type::BEACON) {
            ++sender.stats.txBeacon;
        } else if (get16(air.bytes.data() + 5) == wici_link::BROADCAST) {
            ++sender.stats.txFlood;
        } else {
            ++sender.stats.txUnicast;
        }
        Rx& own = rx_[static_cast<size_t>(air.from)];
        own.transmitting = true;
        own.locked = 0;  // odbiór w toku przepada
        for (size_t r = 0; r < nodes_.size(); ++r) {
            if (static_cast<int>(r) == air.from || !links_[static_cast<size_t>(air.from)][r].audible || nodes_[r]->dead) continue;
            Rx& rx = rx_[r];
            if (rx.transmitting) { ++rx.audible; continue; }  // półdupleks: nie odbierze, ale potem to słyszy
            if (rx.locked) {
                rx.corrupted = true;
            } else if (rx.audible) {
                // Inna ramka już w eterze, a tej odbiornik nie zaczął: obie stracone.
                ++nodes_[r]->stats.rxCollision;
            } else {
                rx.locked = air.id;
                rx.corrupted = false;
            }
            ++rx.audible;
            rx.lastActivityMs = now_;
        }
        if (trace) traceAir(air, 'T', -1);
        onAir_.push_back(std::move(air));
    }
    // Końce.
    for (size_t i = 0; i < onAir_.size();) {
        if (onAir_[i].endMs > now_) { ++i; continue; }
        Air air = std::move(onAir_[i]);
        onAir_.erase(onAir_.begin() + static_cast<long>(i));
        endAir(air);
    }
    if (!onAir_.empty()) ++channelBusyMs;
}

void Net::endAir(Air& air) {
    Rx& own = rx_[static_cast<size_t>(air.from)];
    own.transmitting = false;
    Node& sender = node(air.from);
    if (!air.isHack) sender.radio->txEnded(now_);
    const std::vector<LinkInfo>& row = links_[static_cast<size_t>(air.from)];
    for (size_t r = 0; r < nodes_.size(); ++r) {
        if (static_cast<int>(r) == air.from || !row[r].audible || nodes_[r]->dead) continue;
        Rx& rx = rx_[r];
        if (rx.audible) --rx.audible;
        rx.lastActivityMs = now_;
        if (rx.locked != air.id) continue;
        rx.locked = 0;
        if (rx.corrupted) { ++nodes_[r]->stats.rxCollision; if (trace) traceAir(air, 'C', static_cast<int>(r)); continue; }
        if (!row[r].permille || !rng_.chance(row[r].permille)) { ++nodes_[r]->stats.rxLost; if (trace) traceAir(air, 'L', static_cast<int>(r)); continue; }
        ++nodes_[r]->stats.rxOk;
        if (trace) traceAir(air, 'O', static_cast<int>(r));
        deliver(*nodes_[r], air.bytes.data(), air.bytes.size(), now_);
    }
}

// Zapis przebiegu: jeden wiersz na zdarzenie, do rozbioru poza emulatorem. Pola: czas, zdarzenie (T nadanie, O odbiór,
// L strata, C kolizja), nadawca, odbiornik, rodzaj (D dane, H HACK, B BEACON), adresat łącza, kierunek (U, D),
// `src` i `dst` koperty, licznik koperty, liczba skoków.
void Net::traceAir(const Air& air, char event, int receiver) {
    const uint8_t* wire = air.bytes.data();
    const wici_link::Type type = frameType(wire);
    if (type == wici_link::Type::BEACON) {
        if (event == 'T') fprintf(stderr, "%u T %d - B\n", now_, air.from);
        return;
    }
    const uint16_t to = get16(wire + 5);
    // Odbiór ma znaczenie u adresata; rozsyłanie ma wielu adresatów, więc liczy się każdy.
    if (receiver >= 0 && to != wici_link::BROADCAST && to != node(receiver).id) return;
    if (type == wici_link::Type::HACK) {
        fprintf(stderr, "%u %c %d %d H %d\n", now_, event, air.from, receiver, indexOf(to));
        return;
    }
    fprintf(stderr, "%u %c %d %d D %d %c %u %u %u %u\n", now_, event, air.from, receiver,
            to == wici_link::BROADCAST ? -1 : indexOf(to), wire[0] & wici_link::DOWN ? 'D' : 'U',
            get16(wire + 12), get16(wire + 14), get32(wire + 16), wire[7] >> 4);
}

void Net::traceSnapshot() {
    const uint16_t station = traceStation ? traceStation : node(static_cast<int>(nodes_.size()) - 1).id;
    fprintf(stderr, "%u S parents", now_);
    for (size_t i = 1; i < nodes_.size(); ++i) {
        const Node& n = *nodes_[i];
        fprintf(stderr, " %d", n.shelter ? indexOf(n.shelter->routes().parent()) : -1);
    }
    fprintf(stderr, " down");
    for (size_t i = 0; i < nodes_.size(); ++i) {
        const Node& n = *nodes_[i];
        const uint16_t via = n.root ? n.root->down(station) : n.shelter ? n.shelter->routes().down(station) : 0;
        fprintf(stderr, " %d", via == wici_link::BROADCAST ? -1 : indexOf(via));
    }
    fprintf(stderr, " pool");
    for (size_t i = 1; i < nodes_.size(); ++i) fprintf(stderr, " %u", nodes_[i]->budget->poolUsed() / 1000);
    fprintf(stderr, " refused");
    for (size_t i = 1; i < nodes_.size(); ++i) fprintf(stderr, " %u", nodes_[i]->stats.refusedBudget);
    fprintf(stderr, "\n");
}

void Net::deliver(Node& node, const uint8_t* bytes, size_t length, uint32_t now) {
    if (isAckRequested(bytes)) node.radio->holdForHack(now, now);
    uint8_t bare[wici_link::MAX_FRAME];
    size_t bareLength = 0;
    if (!node.auth.open(bytes, length, bare, sizeof(bare), bareLength)) return;
    if (variant_.probeS) noteTraffic(node, bare, bareLength);
    if (k1Stats) {
        wici_link::Frame heard;
        if (wici_link::decode(linkKey_, NETWORK, bare, bareLength, heard) && heard.type == wici_link::Type::DATA &&
            (heard.flags & wici_link::DOWN) && (heard.source == node.planned || heard.source == node.backup)) {
            std::array<uint8_t, 9> header;
            memcpy(header.data(), heard.payload, header.size());
            parentCopies.insert({node.id, header});
        }
    }
    if (node.selective) {
        wici_link::Frame frame;
        if (wici_link::decode(linkKey_, NETWORK, bare, bareLength, frame) && frame.type == wici_link::Type::DATA &&
            frame.destination == node.id && (frame.flags & wici_link::ACKREQ) && !(frame.flags & wici_link::DOWN) &&
            get16(frame.payload + 1) != frame.source) {
            uint8_t hack[wici_link::MAX_FRAME];
            const size_t n = wici_link::encodeHack(linkKey_, frame, wici_link::macEcho(bare, bareLength), hack, sizeof(hack));
            if (n) node.radio->sendHack(hack, n, now);
            return;
        }
    }
    if (node.dropper) {
        wici_link::Frame frame;
        if (!wici_link::decode(linkKey_, NETWORK, bare, bareLength, frame) || frame.type != wici_link::Type::DATA ||
            frame.destination != node.id || !(frame.flags & wici_link::ACKREQ)) return;
        uint8_t hack[wici_link::MAX_FRAME];
        const size_t n = wici_link::encodeHack(linkKey_, frame, wici_link::macEcho(bare, bareLength), hack, sizeof(hack));
        if (n) node.radio->sendHack(hack, n, now);
        return;
    }
    if (node.shelter) {
        const wici_radio::Event event = node.shelter->receive(bare, bareLength, now, nowS(), static_cast<int16_t>(0));
        if (event == wici_radio::Event::REJECTED) ++node.stats.rxRejected;
    } else if (node.root) {
        node.root->radio(bare, bareLength, now);
    }
}

void Net::forgeVictims(int attacker, std::vector<uint16_t> victims) {
    Node& n = node(attacker);
    n.forger = true;
    n.victims = std::move(victims);
    n.nextForgeMs = now_ + 30000;
}

void Net::pollHostile(Node& n) {
    if (pollLowRank(n)) return;
    if (!n.forger || now_ < n.nextForgeMs || !n.radio->idle() || n.victims.empty() || !n.radio->accepts(wici_link::TxClass::OWN, 100))
        return;
    forgeOne(n);
}

bool Net::pollLowRank(Node& n) {
    if (n.lowRank && now_ >= n.nextBeaconMs && n.radio->idle()) {
        // Podpisany BEACON z fałszywie niską rangą: klucz stacji jest prawdziwy, podpis epoki powtórzony po roocie.
        n.nextBeaconMs = now_ + 120000 + n.rng.below(4000);
        wici_route::Beacon value;
        value.root = ROOT_ID;
        value.rank = 1;
        value.epoch = static_cast<uint16_t>(epochSeed);
        value.parent = n.planned;
        Node& rootNode = node(0);
        wici_epoch::sign(rootNode.secret, rootNode.edPublic, NETWORK, ROOT_ID, value.epoch, value.epochSignature);
        uint8_t wire[wici_link::MAX_FRAME];
        const size_t length = wici_beacon::encode(linkKey_, n.secret, n.edPublic, NETWORK, n.id, n.forgeSeq++, value, wire, sizeof(wire));
        if (length) n.radio->sendData(wire, length, wici_link::TxClass::BEACON);
        return true;
    }
    return false;
}

void Net::forgeOne(Node& n) {
    n.nextForgeMs = now_ + 30000 + n.rng.below(30000);
    // Ramka w górę do rodzica przez prawdziwy kodek łącza, z cudzym `src` koperty. Tag pary jest prawdziwy,
    // bo przejęta stacja ma swoje klucze; MAC koperty nie, bo nie ma klucza ofiary.
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA;
    frame.flags = wici_link::ACKREQ;
    frame.network = NETWORK;
    frame.source = n.id;
    frame.destination = n.forgeRelays.empty() ? n.planned : n.forgeRelays[n.nextVictim % n.forgeRelays.size()];
    frame.ttl = static_cast<uint8_t>(ttl);
    frame.sequence = n.forgeSeq++;
    frame.length = 60;
    frame.payload[0] = 0x40;
    const uint16_t victim = n.victims[n.nextVictim++ % n.victims.size()];
    fram_record::put16(frame.payload + 1, victim);
    fram_record::put16(frame.payload + 3, RECEIVER_MAIN);
    put32(frame.payload + 5, n.forgeCounter++);
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_link::encode(linkKey_, frame, wire, sizeof(wire));
    if (length) n.radio->sendData(wire, length, wici_link::TxClass::OWN);
}

// Próbka przekaźnika: sygnał z ruchu, który przekaźnik i tak widzi. Stan żyje poza kodem stacji, jak stoper zmiany
// rodzica; w firmware wymagałby osobnego rekordu w Relay::receiveData.
void Net::noteTraffic(Node& n, const uint8_t* bare, size_t length) {
    wici_link::Frame frame;
    if (n.isRoot || !wici_link::decode(linkKey_, NETWORK, bare, length, frame) || frame.type != wici_link::Type::DATA ||
        (frame.destination != n.id && frame.destination != wici_link::BROADCAST)) return;
    if (frame.flags & wici_link::DOWN) {
        if (variant_.probeMode == 1) n.upWaitS = 0;
    } else if (get16(frame.payload + 3) != n.id && !n.upWaitS) {
        n.upWaitS = nowS();
    }
}

void Net::pollProbe(Node& n) {
    const uint32_t nowSeconds = nowS();
    if (!n.upWaitS || nowSeconds - n.upWaitS < variant_.probeS) return;
    if (n.lastProbeS && nowSeconds - n.lastProbeS < variant_.probeEveryS) return;
    for (const Report* report : n.reports) if (!report->closed) return;  // własna otwarta wiadomość już jest próbką
    n.lastProbeS = nowSeconds;
    ++n.stats.probes;
    report(n.index, 40)->probe = true;
    if (trace) fprintf(stderr, "%u PROBE %d\n", now_, n.index);
}

// Wrogi węzeł podsuwa dziecku ramkę w dół z ważnym tagiem pary. Dziecko nie sprawdzi koperty i uzna ją za powrót.
void Net::pollFakeDown(Node& n) {
    if (now_ < n.nextFakeMs || !n.radio->idle() || !n.radio->accepts(wici_link::TxClass::OWN, 100)) return;
    const bool rotate = !n.fakeTargets.empty();
    n.nextFakeMs = now_ + (rotate ? n.fakeEveryMs + n.rng.below(n.fakeEveryMs / 5 + 1)
                                  : n.fakeNoRoute ? 10000 + n.rng.below(2000) : 300000 + n.rng.below(30000));
    wici_link::Frame frame;
    frame.type = wici_link::Type::DATA;
    frame.flags = wici_link::ACKREQ | wici_link::DOWN;
    frame.network = NETWORK;
    frame.source = n.id;
    frame.destination = n.fakeBroadcast ? wici_link::BROADCAST : rotate ? n.fakeTargets[n.forgeCounter % n.fakeTargets.size()] : n.fakeDownTo;
    if (n.fakeBroadcast) frame.flags = wici_link::DOWN;
    frame.ttl = static_cast<uint8_t>(ttl);
    frame.sequence = n.forgeSeq++;
    frame.length = 60;
    frame.payload[0] = 0x40;
    fram_record::put16(frame.payload + 1, RECEIVER_MAIN);
    fram_record::put16(frame.payload + 3, rotate ? 900 + n.forgeCounter % 50 : n.fakeNoRoute ? 999 : node(static_cast<int>(nodes_.size()) - 1).id);
    put32(frame.payload + 5, n.forgeCounter++);
    uint8_t wire[wici_link::MAX_FRAME];
    const size_t length = wici_link::encode(linkKey_, frame, wire, sizeof(wire));
    if (length) n.radio->sendData(wire, length, wici_link::TxClass::OWN);
}

void Net::noteCopy(unsigned kind, uint16_t own, const uint8_t* header) {
    const uint16_t recipient = get16(header + 3);
    if (recipient >= 900 && recipient < 950) return;  // numery napastnika: tu odrzucenie jest celem reguły
    std::array<uint8_t, 9> key;
    memcpy(key.data(), header, key.size());
    (kind == 0 || kind == 3 ? refusedCopies : kind == 1 ? seenCopies : fullCopies).insert({own, key});
}

void Net::noteHop(unsigned kind, uint16_t own, uint16_t other, uint16_t recipient) {
    if (kind == 0) {
        // Odbiorca `own` odmówił bez HACK ramki od `other` do adresata `recipient`.
        if (recipient >= 900 && recipient < 950) { ++refusedUnicastAttack; return; }
        ++refusedUnicast;
        refusedUnicastMs[{other, own, recipient}] = now_;
        if (trace) fprintf(stderr, "%u RU %d %d %d\n", now_, indexOf(own), indexOf(other), indexOf(recipient));
        return;
    }
    ++failedRounds;
    const auto at = refusedUnicastMs.find({own, other, recipient});
    if (at == refusedUnicastMs.end() || now_ - at->second > 60000) return;
    // Nieudana runda nadawcy `own` do sąsiada, który przez regułę odmówił tej samej ramki.
    ++refusedRounds;
    if (recipient) ++refusedForgets;  // Relay::timeout zapomina drogę do adresata przez ten skok
    const int index = indexOf(own);
    if (index < 0) return;
    Node& n = node(index);
    if (n.shelter && n.shelter->routes().parent() == other) ++refusedRoundsOnParent;
    n.refusedRoundMs = now_;
    n.refusedRoundNext = other;
    if (trace) fprintf(stderr, "%u RR %d %d %d\n", now_, index, indexOf(other), indexOf(recipient));
}

void Net::pollBeacon(Node& n) {
    // Harmonogram BEACON-ów jak w main.cpp (pętla stacji, po wici_beacon).
    if (n.shelter) {
        const uint16_t parent = n.shelter->routes().parent(), rank = n.shelter->routes().rank(nowS());
        if (rank != 0xFFFF && (parent != n.advertisedParent || wici_beacon::rankMoved(rank, n.advertisedRank)) &&
            (parent != n.scheduledParent || wici_beacon::rankMoved(rank, n.scheduledRank))) {
            n.scheduledParent = parent;
            n.scheduledRank = rank;
            const uint32_t random = n.rng.next();
            const uint32_t earliest = wici_beacon::jittered(now_, n.lastBeaconMs, n.lastBeaconMs != 0, random);
            if (n.nextBeaconMs > earliest) n.nextBeaconMs = earliest;
        }
    }
    if (n.radio->silent || !n.radio->idle() || now_ < n.nextBeaconMs) return;
    const bool accepted = n.root ? n.root->beacon() : n.shelter && n.shelter->beacon(nowS());
    if (accepted) {
        n.lastBeaconMs = now_;
        if (n.shelter) {
            n.advertisedParent = n.scheduledParent = n.shelter->routes().parent();
            n.advertisedRank = n.scheduledRank = n.shelter->routes().rank(nowS());
        }
        ++n.beacons;
        const uint32_t jitter = n.rng.next();
        n.nextBeaconMs = now_ + (n.beacons < 3 ? 120000u + jitter % 4001u : 1440000u + jitter % 720001u);
    } else {
        const uint32_t random = n.rng.next();
        n.nextBeaconMs = wici_beacon::jittered(now_ + 5000u, n.lastBeaconMs, n.lastBeaconMs != 0, random);
    }
}

void Net::pollApp(Node& n) {
    const uint32_t nowSeconds = nowS();
    for (Node::Flight& flight : n.flights)
        if (flight.report && nowSeconds - flight.sentS >= 900) finishFlight(n, flight, false);
    // Stoper rozstrzygnięcia: otwarta wiadomość po HACK i brak uwierzytelnionej wiadomości od odbiorcy. Liczy też
    // na obecnym kodzie, żeby było widać, kiedy próg zadziałałby fałszywie. Działa tylko w wariancie.
    bool open = false;
    for (const Report* report : n.reports) open = open || (report->delivered && !report->closed);
    if (!open) {
        n.leaveTimerS = 0;
    } else if (!n.leaveTimerS) {
        n.leaveTimerS = nowSeconds;
    } else {
        const uint32_t silent = nowSeconds - n.leaveTimerS;
        if (silent > n.stats.maxSilentS) n.stats.maxSilentS = silent;
        if (variant_.leaveAfterS && silent >= variant_.leaveAfterS) leave(n, nowSeconds);
    }
    if (variant_.probeS) pollProbe(n);
    for (;;) {
        unsigned inFlight = 0;
        for (const Node::Flight& flight : n.flights) inFlight += flight.report != nullptr;
        if (inFlight >= 2 || n.shelter->ownBusy()) return;
        Report* best = nullptr;
        for (Report* report : n.reports) {
            if (report->closed || static_cast<int32_t>(nowSeconds - report->nextTryS) < 0) continue;
            bool flying = false;
            for (const Node::Flight& flight : n.flights) flying = flying || flight.report == report;
            if (flying) continue;
            if (!best || report->createdMs < best->createdMs) best = report;
        }
        if (!best) return;
        // Próg w próbach: to nadanie idzie już przez innego rodzica, bo poprzednie dostały HACK i nic nie wróciło.
        if (variant_.leaveCount && best->hacked >= variant_.leaveCount) leave(n, nowSeconds);
        ++best->attempts;
        if (!best->firstSentS) best->firstSentS = nowSeconds;
        best->nextTryS = nowSeconds + 60;
        uint8_t sa1[envelope::MAX_SA1];
        memset(sa1, 'Q', sizeof(sa1));
        put32(sa1, best->id);
        const uint32_t handle = ++n.lastHandle;
        Node::Flight* slot = nullptr;
        for (Node::Flight& flight : n.flights) if (!flight.report) { slot = &flight; break; }
        slot->report = best;
        slot->handle = handle;
        slot->sentS = nowSeconds;
        if (!n.shelter->queueOwn(RECEIVER_MAIN, sa1, best->size, handle)) {
            *slot = Node::Flight();
            const uint32_t random = n.rng.next();
            best->nextTryS = nowSeconds + stationRetry(best->attempts, nowSeconds - best->firstSentS, random);
            return;
        }
    }
}

void Net::pollNode(Node& n) {
    if (n.dead) return;
    n.check.poll(now_);
    if (n.radio->blocked(now_)) return;  // pętla stoi w nadawaniu
    if (n.fakeDownTo || !n.fakeTargets.empty()) pollFakeDown(n);
    if (n.dropper) { pollHostile(n); return; }
    // Uczciwy przekaźnik z fałszywie niską rangą: zamiast własnych BEACON-ów nadaje podrobione.
    const bool lowRank = n.lowRank;
    if (n.shelter) {
        n.shelter->poll(now_, nowS());
        const uint16_t parent = n.shelter->routes().parent();
        if (parent != n.lastParent) {
            ++n.stats.parentChanges;
            // Zmiana rodzica tuż po nieudanej rundzie do rodzica, który odmówił ramki przez regułę.
            if (n.refusedRoundMs && n.lastParent == n.refusedRoundNext && now_ - n.refusedRoundMs < 5000) ++refusedParentChanges;
            if (trace) fprintf(stderr, "%u P %d %d %d\n", now_, n.index, indexOf(n.lastParent), indexOf(parent));
            n.lastParent = parent;
        }
        if (now_ % 100 < assumptions_.pollMs) pollApp(n);
    }
    if (lowRank) pollLowRank(n);
    else pollBeacon(n);
}

void Net::step() {
    ++now_;
    stepAir();
    for (auto& holder : nodes_) {
        Node& n = *holder;
        if (!n.radio->idle() && !n.dead) n.radio->poll(now_);
        if ((now_ + static_cast<uint32_t>(n.index)) % assumptions_.pollMs == 0) pollNode(n);
    }
    if (now_ % 5 == 0) laptop_->tick(now_);
    if (trace && now_ % 30000 == 0) traceSnapshot();
    if (k1Stats && now_ % 10000 == 0) {
        for (auto& holder : nodes_) {
            Node& n = *holder;
            if (!n.budget->allows(false, 200, nowS(), true)) n.stats.over25S += 10;
            if (!n.budget->allows(false, 200, nowS(), false)) n.stats.full60S += 10;
        }
    }
}

void Net::run(uint32_t untilMs) {
    while (now_ < untilMs) step();
}

// --- Stanowisko ----------------------------------------------------------------------------------------

Laptop::Laptop(Net& net, Node& rootNode) : net_(net), node_(rootNode), rng_(net.rng().next()) {
    memcpy(key_, net.linkKey(), 32);
    for (size_t i = 1; i < net.size(); ++i) {
        const Node& station = net.node(static_cast<int>(i));
        std::array<uint8_t, 32> up, down;
        assert(envelope::deriveKey(net.receiverSecret(), station.xPublic, NETWORK, station.id, RECEIVER_MAIN, RECEIVER_MAIN, up.data()));
        assert(envelope::deriveKey(net.receiverSecret(), station.xPublic, NETWORK, RECEIVER_MAIN, station.id, RECEIVER_MAIN, down.data()));
        keysUp_[station.id] = up;
        keysDown_[station.id] = down;
    }
}

void Laptop::setOpen(bool open) {
    open_ = open;
    node_.root->setUsbOpen(open);
    if (!open) {
        // Port zamknięty: wszystko w toku wraca do intencji jako porażka (WiciStos._disconnect).
        for (auto& item : flight_) { intents_[item->intent].flying = false; failed(intents_[item->intent], net_.nowS()); }
        for (auto& item : waiting_) { intents_[item->intent].flying = false; failed(intents_[item->intent], net_.nowS()); }
        flight_.clear();
        waiting_.clear();
        outstanding_ = nullptr;
        usb_.clear();
        admissions_.clear();
        stream_.clear();
        inFrame_ = false;
    } else if (wici_beacon::burstAllowed(net_.now(), node_.lastBeaconMs, node_.lastBeaconMs != 0)) {
        node_.nextBeaconMs = net_.now() + 1000 + node_.rng.next() % 4000;
        node_.beacons = 0;
    }
}

size_t Laptop::openIntents() const {
    size_t open = 0;
    for (const Intent& intent : intents_) open += !intent.done;
    return open;
}

void Laptop::enqueue(uint16_t dest, uint32_t reportId, size_t size) {
    Intent intent;
    intent.dest = dest;
    intent.reportId = reportId;
    intent.plain.assign(size, 'R');
    put32(intent.plain.data(), reportId);
    intent.nextTryS = net_.nowS();
    byReport_[{dest, reportId}] = intents_.size();
    intents_.push_back(std::move(intent));
}

void Laptop::readPort(uint32_t now) {
    size_t length = 0;
    while (const uint8_t* bytes = node_.port->output(length)) {
        if (!length) break;
        for (size_t i = 0; i < length; ++i) {
            const uint8_t b = bytes[i];
            if (b == kiss::FEND) {
                if (inFrame_ && !stream_.empty()) {
                    const uint8_t command = stream_[0];
                    usb_.push_back({now + net_.assumptions().usbMs, command, std::vector<uint8_t>(stream_.begin() + 1, stream_.end())});
                }
                stream_.clear();
                inFrame_ = true;
                escape_ = false;
            } else if (inFrame_) {
                if (escape_) {
                    stream_.push_back(b == kiss::TFEND ? kiss::FEND : kiss::FESC);
                    escape_ = false;
                } else if (b == kiss::FESC) {
                    escape_ = true;
                } else {
                    stream_.push_back(b);
                }
            }
        }
        node_.port->consume(length);
    }
}

bool Laptop::answers(const Delivery& item, const wici_link::Frame& hack) {
    if (item.onAir.empty() || (!item.hasSequence && outstanding_ == &item)) return false;
    wici_link::Frame sent;
    if (!wici_link::decode(key_, NETWORK, item.onAir.data(), item.onAir.size(), sent)) return false;
    return sent.destination == hack.source && sent.sequence == hack.sequence &&
           wici_link::macEcho(item.onAir.data(), item.onAir.size()) == wici_link::hackEcho(hack);
}

Laptop::Delivery* Laptop::sentItem(const uint8_t* payload, size_t length) {
    for (auto& item : flight_) {
        const std::vector<uint8_t>& part = item->frames[item->part];
        if (part.size() == length && !memcmp(part.data(), payload, length)) return item.get();
    }
    return nullptr;
}

void Laptop::handle(uint8_t command, const std::vector<uint8_t>& wire, uint32_t now) {
    wici_link::Frame frame;
    if (!wici_link::decode(key_, NETWORK, wire.data(), wire.size(), frame)) return;
    if (command == wici_gateway::CMD_REFUSED) {
        if (outstanding_ && frame.type == wici_link::Type::DATA) {
            const std::vector<uint8_t>& part = outstanding_->frames[outstanding_->part];
            if (part.size() == frame.length && !memcmp(part.data(), frame.payload, frame.length)) {
                outstanding_ = nullptr;
                ++refused;
            }
        }
        return;
    }
    if (frame.type == wici_link::Type::DATA && frame.source == ROOT_ID && (frame.flags & wici_link::DOWN)) {
        Delivery* item = sentItem(frame.payload, frame.length);
        if (item && frame.destination == wici_link::BROADCAST && frame.flags == wici_link::DOWN) {
            if (outstanding_ == item) outstanding_ = nullptr;
            item->flooded = true;
            item->lastOwn = false;
            ++floods;
            nextPart(*item);
            return;
        }
        if (item && frame.flags == (wici_link::ACKREQ | wici_link::DOWN) && !item->hasSequence) {
            item->hasSequence = true;
            item->sequence = frame.sequence;
            item->onAir = wire;
            if (outstanding_ == item) outstanding_ = nullptr;
            ++item->attempts;
            ++routed;
            item->sentMs = now;
            item->retryMs = now + wici_link::HACK_WAIT_MS;
            return;
        }
    }
    if (frame.type == wici_link::Type::HACK && frame.destination == ROOT_ID) {
        for (auto& holder : flight_) {
            Delivery* item = holder.get();
            if (!answers(*item, frame)) continue;
            item->lastOwn = frame.source == item->destination;
            item->relayed = item->relayed || !item->lastOwn;
            nextPart(*item);
            return;
        }
    }
    if (frame.type != wici_link::Type::DATA || frame.destination != ROOT_ID) return;
    admissions_.push_back({now + net_.assumptions().admissionMs, 0, wire});
}

Laptop::Outcome Laptop::admit(const wici_link::Frame& frame, uint32_t now) {
    if (frame.length < envelope::OVERHEAD) return SETTLED;
    const uint16_t sender = get16(frame.payload + 1), recipient = get16(frame.payload + 3);
    const auto found = keysUp_.find(sender);
    if (found == keysUp_.end() || recipient != RECEIVER_MAIN) return SETTLED;
    const uint8_t type = frame.payload[0] & 0x0F;
    const uint32_t counter = get32(frame.payload + 5);
    std::set<uint32_t>& replay = replay_[sender];
    if (type == envelope::TYPE_PROOF) {
        // Dowód: openPart przyjmuje tylko SA1, więc tu to samo AEAD co w envelope.cpp.
        uint8_t iv[12];
        memcpy(iv, frame.payload + 1, 4);
        iv[4] = frame.payload[0];
        memset(iv + 5, 0, 3);
        memcpy(iv + 8, frame.payload + 5, 4);
        const size_t body = frame.length - envelope::OVERHEAD;
        uint8_t plain[envelope::MAX_FRAME];
        ChaChaPoly cipher;
        if (!cipher.setKey(found->second.data(), 32) || !cipher.setIV(iv, sizeof(iv))) return SETTLED;
        cipher.addAuthData(frame.payload, envelope::HEADER);
        cipher.decrypt(plain, frame.payload + envelope::HEADER, body);
        const bool valid = cipher.checkTag(frame.payload + envelope::HEADER + body, envelope::TAG);
        cipher.clear();
        if (!valid) return SETTLED;
        if (!replay.insert(counter).second) return DUPLICATE;
        for (size_t i = 0; i + 4 <= body; i += 4) {
            const auto intent = sent_.find({sender, get32(plain + i)});
            if (intent != sent_.end() && !intents_[intent->second].done) {
                intents_[intent->second].done = true;
                ++deliveredIntents;
            }
        }
        return PROOF;
    }
    envelope::Part part;
    if (!envelope::openPart(found->second.data(), frame.payload, frame.length, part) || part.sender != sender) return SETTLED;
    if (replay.count(part.counter)) return DUPLICATE;
    std::vector<uint8_t> whole;
    if (part.number == 0) {
        whole.assign(part.plaintext, part.plaintext + part.length);
    } else {
        auto key = std::make_pair(sender, part.counter * 2 + (part.number - 1));
        partial_[key].assign(part.plaintext, part.plaintext + part.length);
        const auto other = partial_.find(std::make_pair(sender, part.counter * 2 + (2 - part.number)));
        if (other == partial_.end()) {
            for (Intent& intent : intents_) if (!intent.done && intent.dest == sender) intent.nextTryS = 0, intent.forwarded = 0;
            return PARTIAL;
        }
        const std::vector<uint8_t>& first = part.number == 1 ? partial_[key] : other->second;
        const std::vector<uint8_t>& second = part.number == 1 ? other->second : partial_[key];
        whole = first;
        whole.insert(whole.end(), second.begin(), second.end());
    }
    replay.insert(part.counter);
    // Świeża uwierzytelniona koperta: stacja jest osiągalna teraz (Wysylka.contact).
    for (Intent& intent : intents_) {
        if (!intent.done && intent.dest == sender) { intent.nextTryS = 0; intent.forwarded = 0; }
    }
    const uint32_t reportId = get32(whole.data());
    net_.reportArrived(reportId, now);
    // Wysylka.accepted: czekająca intencja RECEIVED idzie od razu, a domknięta albo pierwsza powstaje.
    const auto existing = byReport_.find({sender, reportId});
    if (existing == byReport_.end() || intents_[existing->second].done) enqueue(sender, reportId, 50);
    else intents_[existing->second].nextTryS = 0;
    return COMPLETE;
}

bool Laptop::hackAllowed(const std::vector<uint8_t>& wire, Outcome outcome, uint32_t now) {
    std::vector<uint8_t> mac(wire.end() - static_cast<long>(wici_link::TAG), wire.end());
    const auto seen = seen_.find(mac);
    if (seen == seen_.end()) {
        seen_[mac] = {now, outcome != DUPLICATE};
        if (outcome != DUPLICATE) return true;
    } else if (seen->second.second) {
        seen->second.second = false;
        return true;
    }
    if (repeatSent_ && now - repeatMs_ < 5000) return false;
    repeatSent_ = true;
    repeatMs_ = now;
    return true;
}

void Laptop::receive(const std::vector<uint8_t>& wire, uint32_t now) {
    wici_link::Frame frame;
    if (!wici_link::decode(key_, NETWORK, wire.data(), wire.size(), frame)) return;
    const Outcome outcome = admit(frame, now);
    if (outcome == DUPLICATE) ++duplicates;
    if (outcome == SETTLED) ++rejected;
    if (!(frame.flags & wici_link::ACKREQ) || !hackAllowed(wire, outcome, now)) return;
    uint8_t hack[wici_link::MAX_FRAME];
    const size_t length = wici_link::encodeHack(key_, frame, wici_link::macEcho(wire.data(), wire.size()), hack, sizeof(hack));
    // Tylko świeża część uwierzytelniona MAC-iem koperty pozwala rootowi nauczyć się drogi.
    const bool fresh = outcome == PARTIAL || outcome == COMPLETE || outcome == PROOF;
    if (length) node_.root->host(hack, length, now, net_.nowS(), fresh ? kiss::CMD_DATA : wici_gateway::CMD_HACK_ONLY);
}

void Laptop::nextPart(Delivery& item) {
    ++item.part;
    item.hasSequence = false;
    item.onAir.clear();
    item.submissions = item.attempts = 0;
    item.retryMs = 0;
    if (item.part == item.frames.size())
        finish(item, item.relayed && !item.lastOwn ? 2 : item.relayed || item.flooded ? 3 : 1);
}

void Laptop::finish(Delivery& item, int result) {
    item.result = result;
    Intent& intent = intents_[item.intent];
    intent.flying = false;
    const uint32_t nowS = net_.nowS();
    if (result == 1) {
        if (!intent.done) ++deliveredIntents;
        intent.done = true;
    } else if (result == 2 || result == 3) {
        forwardedIntent(intent, nowS, result == 2);
    } else {
        failed(intent, nowS);
    }
    if (outstanding_ == &item) outstanding_ = nullptr;
    for (size_t i = 0; i < flight_.size(); ++i) {
        if (flight_[i].get() == &item) { flight_.erase(flight_.begin() + static_cast<long>(i)); return; }
    }
}

uint32_t Laptop::retryDelay(uint32_t attempts, uint32_t ageS) {
    const uint32_t jitter = 80 + rng_.below(41);
    if (ageS >= 6 * 3600) return 3600 * jitter / 100;
    static const uint32_t steps[] = {60, 120, 300, 900};
    const uint32_t index = attempts ? attempts - 1 : 0;
    return steps[index < 4 ? index : 3] * jitter / 100;
}

void Laptop::failed(Intent& intent, uint32_t nowS) {
    ++intent.attempts;
    intent.nextTryS = nowS + retryDelay(intent.attempts, nowS - intent.firstTryS);
}

void Laptop::forwardedIntent(Intent& intent, uint32_t nowS, bool custody) {
    ++intent.attempts;
    uint32_t delay = retryDelay(intent.attempts, nowS - intent.firstTryS);
    if (custody) {
        ++intent.forwarded;
        const uint64_t scaled = static_cast<uint64_t>(35 * 60) << (intent.forwarded - 1 > 8 ? 8 : intent.forwarded - 1);
        const uint32_t held = scaled > 4 * 3600 ? 4 * 3600 : static_cast<uint32_t>(scaled);
        if (held > delay) delay = held;
    }
    intent.nextTryS = nowS + delay;
}

bool Laptop::wantsFlood(const Delivery& item) const {
    return net_.variant().alternate && (intents_[item.intent].attempts % 2) == 1;
}

void Laptop::submit(Delivery& item, uint32_t now) {
#ifdef WICI_EMU_VARIANT
    node_.root->setFloodNext(item.flood);
#endif
    wici_gateway::Event event;
    if (!item.onAir.empty()) {
        event = node_.root->host(item.onAir.data(), item.onAir.size(), now, net_.nowS());
    } else {
        const std::vector<uint8_t>& part = item.frames[item.part];
        wici_link::Frame frame;
        frame.type = wici_link::Type::DATA;
        frame.flags = wici_link::ACKREQ | wici_link::DOWN;
        frame.network = NETWORK;
        frame.source = get16(part.data() + 1);
        frame.destination = ROOT_ID;
        frame.ttl = static_cast<uint8_t>(net_.ttl);
        frame.length = part.size();
        memcpy(frame.payload, part.data(), part.size());
        uint8_t wire[wici_link::MAX_FRAME];
        const size_t length = wici_link::encode(key_, frame, wire, sizeof(wire));
        event = length ? node_.root->host(wire, length, now, net_.nowS()) : wici_gateway::Event::REJECTED;
    }
    (void)event;
    ++item.submissions;
    item.sentMs = now;
    const uint32_t power = item.submissions < 5 ? item.submissions : 5;
    const uint32_t backoffS = 1u << power;
    item.retryMs = now + (backoffS < 30 ? backoffS : 30) * 1000;
    outstanding_ = &item;
    turn_ = item.destination;
}

void Laptop::portTick(uint32_t now) {
    for (size_t i = 0; i < waiting_.size();) {
        bool busy = false;
        for (auto& item : flight_) busy = busy || item->destination == waiting_[i]->destination;
        if (busy) { ++i; continue; }
        flight_.push_back(std::move(waiting_[i]));
        waiting_.erase(waiting_.begin() + static_cast<long>(i));
    }
    for (size_t i = 0; i < flight_.size();) {
        Delivery& item = *flight_[i];
        if (item.hasSequence && now >= item.retryMs) {
            if (item.attempts >= 3) { finish(item, 0); continue; }
            item.hasSequence = false;
            item.retryMs = now + rng_.range(500, 2000);
        }
        ++i;
    }
    if (outstanding_ && now < outstanding_->retryMs) return;
    outstanding_ = nullptr;
    for (auto& item : flight_)
        if (item->hasSequence && now < item->retryMs) return;
    // Na zmianę po stacjach: najpierw następna po ostatniej obsłużonej.
    std::vector<Delivery*> order;
    for (auto& item : flight_) if (item->destination > turn_) order.push_back(item.get());
    for (auto& item : flight_) if (item->destination <= turn_) order.push_back(item.get());
    for (size_t a = 0; a < order.size(); ++a)
        for (size_t b = a + 1; b < order.size(); ++b)
            if ((order[a]->destination > turn_) == (order[b]->destination > turn_) && order[a]->destination > order[b]->destination)
                std::swap(order[a], order[b]);
    for (Delivery* item : order) {
        if (item->hasSequence || now < item->retryMs) continue;
        if (item->submissions >= 30) { finish(*item, 0); continue; }
        const uint32_t spacing = net_.variant().floodMsPerStation * static_cast<uint32_t>(net_.size() - 1);
        if (spacing && item->onAir.empty()) {
            // Budżet rozsyłania stanowiska: ponad niego droga, gdy jest, albo czekanie.
            const bool noRoute = node_.root->down(item->destination) == wici_link::BROADCAST;
            if ((item->flood || noRoute) && now < nextFloodMs_) {
                if (noRoute) { ++floodsDeferred; continue; }
                item->flood = false;
            } else if (item->flood || noRoute) {
                nextFloodMs_ = now + spacing;
            }
        }
        submit(*item, now);
        return;
    }
}

void Laptop::wysylkaTick(uint32_t now) {
    const uint32_t nowS = net_.nowS();
    size_t unfinished = flight_.size() + waiting_.size();
    for (size_t i = 0; i < intents_.size() && unfinished < 4; ++i) {
        Intent& intent = intents_[i];
        if (intent.done || intent.flying || static_cast<int32_t>(nowS - intent.nextTryS) < 0) continue;
        if (!intent.hasFirstTry) { intent.hasFirstTry = true; intent.firstTryS = nowS; }
        const uint32_t counter = ++counters_[intent.dest];
        envelope::Frame parts[2];
        const size_t count = envelope::seal(keysDown_[intent.dest].data(), RECEIVER_MAIN, intent.dest, counter,
                                            intent.plain.data(), intent.plain.size(), wici_link::MAX_PAYLOAD, parts);
        if (!count) continue;
        sent_[{intent.dest, counter}] = i;
        auto item = std::make_unique<Delivery>();
        item->intent = i;
        item->destination = intent.dest;
        for (size_t p = 0; p < count; ++p) item->frames.emplace_back(parts[p].bytes, parts[p].bytes + parts[p].length);
        item->flood = wantsFlood(*item);
        intent.flying = true;
        waiting_.push_back(std::move(item));
        ++unfinished;
    }
    (void)now;
}

void Laptop::tick(uint32_t now) {
    if (!open_) return;
    readPort(now);
    while (!usb_.empty() && usb_.front().dueMs <= now) {
        const Timed entry = usb_.front();
        usb_.pop_front();
        handle(entry.command, entry.wire, now);
    }
    while (!admissions_.empty() && admissions_.front().dueMs <= now) {
        const Timed entry = admissions_.front();
        admissions_.pop_front();
        receive(entry.wire, now);
    }
    portTick(now);
    if (now >= nextWysylkaMs_) {
        wysylkaTick(now);
        nextWysylkaMs_ = now + 1000;
    }
}

}  // namespace emu
