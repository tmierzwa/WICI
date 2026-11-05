// SPDX-License-Identifier: MIT
// Scenariusze emulatora WICI-Link. Wynik: jeden wiersz JSON na przebieg; opis założeń w README.md.
// Użycie: wici_emulator <scenariusz> [seed=1] [p=900] [learn=0] [alternate=0] [leave=0] [hold=0]
//         [flood=0] [n=0] [reports=50] [hops=15] [hours=0]
#include <stdlib.h>

#include <algorithm>
#include <string>

#include "emulator.h"

using namespace emu;

namespace {

struct Params {
    std::string scenario;
    uint64_t seed = 1;
    uint32_t p = 900, hops = 15, reports = 50, n = 0, hours = 0, spreadS = 300;
    uint32_t sense = 1, miss = 20, skip = 0;
    Variant variant;
};

// Pełny raport przebiegu: tylko liczby całkowite, żeby wynik nie zależał od kompilatora.
void percentiles(std::vector<uint32_t>& values, uint32_t& p50, uint32_t& maximum) {
    std::sort(values.begin(), values.end());
    p50 = values.empty() ? 0 : values[values.size() / 2];
    maximum = values.empty() ? 0 : values.back();
}

void emit(const Params& params, const std::string& label, Net& net, const std::string& extra = "") {
    std::vector<uint32_t> arrive, close;
    uint32_t closed = 0;
    for (const auto& report : net.reports()) {
        const auto at = net.arrivedMs.find(report->id);
        if (at != net.arrivedMs.end()) arrive.push_back((at->second - report->createdMs) / 1000);
        if (report->closed) { ++closed; close.push_back((report->closedMs - report->createdMs) / 1000); }
    }
    uint32_t arriveP50, arriveMax, closeP50, closeMax;
    percentiles(arrive, arriveP50, arriveMax);
    percentiles(close, closeP50, closeMax);
    NodeStats total;
    uint64_t maxAir = 0;
    uint32_t maxSilent = 0, over30 = 0;
    for (size_t i = 0; i < net.size(); ++i) {
        const NodeStats& s = net.node(static_cast<int>(i)).stats;
        total.txUnicast += s.txUnicast; total.txFlood += s.txFlood; total.txHack += s.txHack; total.txBeacon += s.txBeacon;
        total.refusedBudget += s.refusedBudget; total.deferrals += s.deferrals; total.txDrops += s.txDrops;
        total.rxCollision += s.rxCollision; total.rxLost += s.rxLost; total.hackRefused += s.hackRefused;
        total.parentChanges += s.parentChanges; total.leaves += s.leaves; total.rxRejected += s.rxRejected;
        maxAir = std::max(maxAir, s.airMs);
        maxSilent = std::max(maxSilent, s.maxSilentS);
        over30 += s.maxSilentS >= 1800;
    }
    uint32_t offPlanned = 0;
    for (size_t i = 1; i < net.size(); ++i) {
        const Node& n = net.node(static_cast<int>(i));
        if (n.shelter && !n.dropper) offPlanned += n.shelter->routes().parent() != n.planned;
    }
    const uint32_t seconds = net.now() / 1000;
    Laptop& laptop = net.laptop();
    printf("{\"scenario\":\"%s\",\"label\":\"%s\",\"seed\":%llu,\"p\":%u,\"hops\":%u,\"nodes\":%zu,"
           "\"learn\":%d,\"alternate\":%d,\"leave_s\":%u,\"hold_s\":%u,\"flood_ms\":%u,\"t_s\":%u,"
           "\"reports\":%zu,\"arrived\":%u,\"closed\":%u,\"arrive_p50_s\":%u,\"arrive_max_s\":%u,"
           "\"close_p50_s\":%u,\"close_max_s\":%u,",
           params.scenario.c_str(), label.c_str(), static_cast<unsigned long long>(params.seed), params.p, params.hops,
           net.size(), net.variant().learnRoutes, net.variant().alternate, net.variant().leaveAfterS, net.variant().holdS,
           net.variant().floodMsPerStation, seconds, net.reports().size(), net.arrivedCount, closed,
           arriveP50, arriveMax, closeP50, closeMax);
    printf("\"unicast\":%u,\"flood\":%u,\"hack\":%u,\"beacon\":%u,\"busy_pm\":%u,\"max_air_pm\":%u,"
           "\"collisions\":%u,\"lost\":%u,\"hack_refused\":%u,\"budget_refused\":%u,\"tx_drops\":%u,\"deferrals\":%u,"
           "\"parent_changes\":%u,\"leaves\":%u,\"max_silent_s\":%u,\"stations_silent_30min\":%u,\"stall_s\":%u,",
           total.txUnicast, total.txFlood, total.txHack, total.txBeacon,
           static_cast<uint32_t>(static_cast<uint64_t>(net.channelBusyMs) * 1000 / std::max(net.now(), 1u)),
           static_cast<uint32_t>(maxAir * 1000 / std::max(net.now(), 1u)),
           total.rxCollision, total.rxLost, total.hackRefused, total.refusedBudget, total.txDrops, total.deferrals,
           total.parentChanges, total.leaves, maxSilent, over30, net.longestStallMs / 1000);
    printf("\"laptop_floods\":%u,\"laptop_routed\":%u,\"laptop_refused\":%u,\"intents_open\":%zu,\"intents_done\":%u,"
           "\"duplicates\":%u,\"settled\":%u,\"floods_deferred\":%u,\"off_planned\":%u%s}\n",
           laptop.floods, laptop.routed, laptop.refused, laptop.openIntents(), laptop.deliveredIntents,
           laptop.duplicates, laptop.rejected, laptop.floodsDeferred, offPlanned, extra.c_str());
    fflush(stdout);
}

// Łańcuch: root (0), stacje 1..hops; `skip` > 0 dodaje łącza co dwa skoki i rodzica zapasowego.
void chain(Net& net, const Params& params, uint32_t skip = 0, int count = -1) {
    const int last = count >= 0 ? count : static_cast<int>(params.hops);
    for (int i = 0; i < last; ++i) net.link(i, i + 1, params.p);
    for (int i = 0; i + 2 <= last; ++i) {
        if (skip) net.link(i, i + 2, skip);
        else if (params.sense >= 2) net.interfere(i, i + 2);
    }
    for (int i = 1; i <= last; ++i) net.setParents(i, i - 1, skip && i >= 2 ? i - 2 : -1);
    // Plan roota jak w dokumencie configure: każda stacja za pierwszą stacją łańcucha.
    if (!net.variant().learnRoutes)
        for (int i = 2; i <= last; ++i) net.rootPlan(net.node(i).id, net.node(1).id);
}

// Zgłoszenia rozłożone po równo w czasie `spreadS`.
void schedule(Net& net, const std::vector<int>& stations, uint32_t count, uint32_t spreadS, uint32_t tMaxMs,
              size_t size = 174) {
    const uint32_t start = net.now();
    for (uint32_t i = 0; i < count; ++i) {
        const uint32_t due = start + (count > 1 ? static_cast<uint64_t>(i) * spreadS * 1000 / (count - 1) : 0);
        net.run(due);
        net.report(stations[i % stations.size()], size);
    }
    net.runUntil(tMaxMs, [&] {
        for (const auto& report : net.reports()) if (!report->closed) return false;
        return true;
    });
}

Assumptions assumptionsFor(const Params& params) {
    Assumptions a;
    a.senseMissPermille = params.miss;
    return a;
}

uint32_t hoursOr(const Params& params, uint32_t fallback) { return (params.hours ? params.hours : fallback) * 3600000u; }

// 1. Pięćdziesiąt zgłoszeń z końca łańcucha albo z całej sieci.
void reports(const Params& params, bool fromEnd) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, params.skip);
    net.start();
    net.run(10 * 60000);  // BEACON-y pierwszej serii i zbieganie rang
    std::vector<int> stations;
    if (fromEnd) stations.push_back(static_cast<int>(params.hops));
    else for (uint32_t i = 1; i <= params.hops; ++i) stations.push_back(static_cast<int>(i));
    net.trackStall = true;
    net.lastHackMs = 0;
    schedule(net, stations, params.reports, params.spreadS, net.now() + hoursOr(params, 6));
    emit(params, fromEnd ? "koniec" : "cala_siec", net);
}

// 2. Zmiana rodzica i poprawa drogi w dół.
std::string routesAlong(Net& net, uint16_t station, int last) {
    std::string out = ",\"route_";
    out += std::to_string(station) + "\":[";
    for (int i = 0; i <= last; ++i) {
        const Node& n = net.node(i);
        uint16_t via = n.root ? n.root->down(station) : n.shelter ? n.shelter->routes().down(station) : 0;
        if (i) out += ",";
        out += std::to_string(via == 0xFFFF ? 0 : via);
    }
    return out + "]";
}

void parentChange(const Params& params) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, 700);
    net.start();
    net.run(10 * 60000);
    const int moved = static_cast<int>(params.hops) / 2 + 1, far = static_cast<int>(params.hops);
    // Rozgrzanie: drogi uczą się z ruchu.
    schedule(net, {moved, far}, 6, 60, net.now() + 3600000);
    const std::string before = routesAlong(net, net.node(far).id, far);
    const uint32_t closedBefore = static_cast<uint32_t>(net.reports().size());
    const uint32_t floodsBefore = net.laptop().floods;
    uint32_t relayFloodsBefore = 0;
    for (size_t i = 0; i < net.size(); ++i) relayFloodsBefore += net.node(static_cast<int>(i)).stats.txFlood;
    // Przerwa w łączu do rodzica z planu: stacja musi przejść na rodzica zapasowego 6.
    net.setLinkPermille(moved, moved - 1, 0);
    schedule(net, {moved, far}, 10, 120, net.now() + hoursOr(params, 4));
    std::vector<uint32_t> close;
    uint32_t after = 0;
    for (size_t i = closedBefore; i < net.reports().size(); ++i) {
        const Report& report = *net.reports()[i];
        if (report.closed) { ++after; close.push_back((report.closedMs - report.createdMs) / 1000); }
    }
    uint32_t p50, maximum;
    percentiles(close, p50, maximum);
    uint32_t relayFloods = 0;
    for (size_t i = 0; i < net.size(); ++i) relayFloods += net.node(static_cast<int>(i)).stats.txFlood;
    std::string extra = before + routesAlong(net, net.node(far).id, far);
    extra += ",\"after_reports\":10,\"after_closed\":" + std::to_string(after);
    extra += ",\"after_close_p50_s\":" + std::to_string(p50) + ",\"after_close_max_s\":" + std::to_string(maximum);
    extra += ",\"after_laptop_floods\":" + std::to_string(net.laptop().floods - floodsBefore);
    extra += ",\"after_flood_frames\":" + std::to_string(relayFloods - relayFloodsBefore);
    extra += ",\"moved_parent\":" + std::to_string(net.node(moved).shelter->routes().parent());
    emit(params, "zmiana_rodzica", net, extra);
}

// 3. Stacja daje HACK i porzuca ruch. `who`: czyje zgłoszenia idą przez nią.
void blackHole(const Params& params, const std::string& who) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, 700);
    net.start();
    net.run(10 * 60000);
    const int hole = static_cast<int>(params.hops) / 2 + 1;
    net.node(hole).dropper = true;
    std::vector<int> stations;
    if (who == "dziecko") stations.push_back(hole + 1);
    else if (who == "koniec") stations.push_back(static_cast<int>(params.hops));
    else for (uint32_t i = hole + 1; i <= params.hops; ++i) stations.push_back(static_cast<int>(i));
    schedule(net, stations, params.reports, params.spreadS, net.now() + hoursOr(params, 8));
    std::string extra = ",\"child_parent\":" + std::to_string(net.node(hole + 1).shelter->routes().parent());
    emit(params, "porzucanie_" + who, net, extra);
}

// 5. Nasycenie: każda stacja zgłasza co `spreadS` przez godzinę, potem cisza i sprawdzenie, czy sieć się opróżnia.
void saturation(const Params& params) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, params.skip);
    net.start();
    net.run(10 * 60000);
    net.trackStall = true;
    const uint32_t load = net.now() + 3600000;
    uint32_t next = net.now();
    int station = 1;
    while (net.now() < load) {
        net.run(next);
        net.report(station);
        station = station % static_cast<int>(params.hops) + 1;
        next += params.spreadS * 1000 / params.hops;
    }
    net.runUntil(net.now() + hoursOr(params, 8), [&] {
        for (const auto& report : net.reports()) if (!report->closed) return false;
        return true;
    });
    std::string extra = ",\"closed_per_10min\":[";
    for (size_t i = 0; i < net.closedPerBucket.size(); ++i) extra += (i ? "," : "") + std::to_string(net.closedPerBucket[i]);
    extra += "],\"hacks_per_10min\":[";
    for (size_t i = 0; i < net.hacksPerBucket.size(); ++i) extra += (i ? "," : "") + std::to_string(net.hacksPerBucket[i]);
    extra += "]";
    emit(params, "nasycenie", net, extra);
}

uint32_t beaconsTotal(Net& net) {
    uint32_t total = 0;
    for (size_t i = 0; i < net.size(); ++i) total += net.node(static_cast<int>(i)).stats.txBeacon;
    return total;
}

// 6. Fala BEACON-ów: stanowisko wyłączone przez `hours` (domyślnie 2 h), potem wraca z nową epoką.
void beaconWave(const Params& params) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, params.skip);
    net.start();
    net.run(3600000);
    const uint32_t beforeOff = beaconsTotal(net);
    uint32_t parentsBefore = 0;
    for (size_t i = 0; i < net.size(); ++i) parentsBefore += net.node(static_cast<int>(i)).stats.parentChanges;
    net.laptop().setOpen(false);
    const uint32_t off = hoursOr(params, 2);
    // Stacje mają otwarte zgłoszenia w czasie przerwy: root milczy, więc pierwszy skok nie dostaje HACK.
    for (uint32_t i = 1; i <= params.hops; ++i) net.report(static_cast<int>(i));
    net.run(net.now() + off);
    const uint32_t duringOff = beaconsTotal(net) - beforeOff;
    uint32_t checksDropped = 0;
    net.epochSeed = 2;
    net.restartRoot(2);
    const uint32_t atReturn = beaconsTotal(net);
    std::vector<uint64_t> airAtReturn;
    for (size_t i = 0; i < net.size(); ++i) airAtReturn.push_back(net.node(static_cast<int>(i)).stats.airMs);
    uint32_t rankBackS = 0;
    const uint32_t returned = net.now();
    while (net.now() < returned + 3600000) {
        net.run(net.now() + 5000);
        uint32_t withRank = 0;
        for (size_t i = 1; i < net.size(); ++i) withRank += net.node(static_cast<int>(i)).shelter->routes().rank(net.nowS()) != 0xFFFF;
        if (!rankBackS && withRank == net.size() - 1) rankBackS = (net.now() - returned) / 1000;
    }
    const uint32_t hourAfter = beaconsTotal(net) - atReturn;
    uint32_t parentsAfter = 0;
    uint32_t ranked = 0;
    uint64_t maxAirAfter = 0;
    for (size_t i = 1; i < net.size(); ++i) {
        Node& n = net.node(static_cast<int>(i));
        parentsAfter += n.stats.parentChanges;
        checksDropped += n.shelter->beaconStats().dropped;
        ranked += n.shelter->routes().rank(net.nowS()) != 0xFFFF;
        maxAirAfter = std::max(maxAirAfter, n.stats.airMs - airAtReturn[i]);
    }
    std::string extra = ",\"beacons_first_hour\":" + std::to_string(beforeOff) +
                        ",\"beacons_off\":" + std::to_string(duringOff) +
                        ",\"beacons_hour_after\":" + std::to_string(hourAfter) +
                        ",\"beacon_checks_dropped\":" + std::to_string(checksDropped) +
                        ",\"parent_changes_off_and_after\":" + std::to_string(parentsAfter - parentsBefore) +
                        ",\"stations_with_rank\":" + std::to_string(ranked) +
                        ",\"max_air_after_ms\":" + std::to_string(maxAirAfter) +
                        ",\"rank_back_s\":" + std::to_string(rankBackS);
    emit(params, "fala_beacon", net, extra);
}

// 7. Budżet rozsyłania: po jednej wiadomości do każdej stacji bez znanej drogi. `grid` to szereg
// łańcuchów, a clique stacje słyszące się wzajemnie (założenie zachowawcze budżetu).
void floodBudget(const Params& params, bool clique) {
    const uint32_t stations = params.n ? params.n : 50;
    Net net(stations + 1, params.seed, assumptionsFor(params), params.variant);
    const uint32_t columns = clique ? 1 : (stations + params.hops - 1) / params.hops;
    if (clique) {
        for (uint32_t a = 0; a <= stations; ++a)
            for (uint32_t b = a + 1; b <= stations; ++b) net.link(static_cast<int>(a), static_cast<int>(b), params.p);
        // Root ma najwyżej 50 wpisów priority_keys, więc ponad 49 stacji wisi pod pierwszymi stacjami.
        for (uint32_t s = 1; s <= stations; ++s) net.setParents(static_cast<int>(s), s <= 49 ? 0 : static_cast<int>((s - 1) % 49 + 1), -1);
    } else {
        // `columns` łańcuchów po `hops`; sąsiednie łańcuchy słyszą się na tej samej głębokości słabiej.
        for (uint32_t s = 1; s <= stations; ++s) {
            const uint32_t column = (s - 1) % columns, depth = (s - 1) / columns;
            const int parent = depth ? static_cast<int>(s - columns) : 0;
            net.link(static_cast<int>(s), parent, params.p);
            net.setParents(static_cast<int>(s), parent, -1);
            if (column + 1 < columns && s + 1 <= stations) net.link(static_cast<int>(s), static_cast<int>(s + 1), params.p / 2);
        }
    }
    net.start();
    net.run(10 * 60000);
    for (uint32_t s = 1; s <= stations; ++s)
        net.laptop().enqueue(net.node(static_cast<int>(s)).id, 0x80000000u + s, 50);
    const uint32_t started = net.now();
    // Równolegle ruch w górę: 10 zgłoszeń z ostatnich stacji.
    for (uint32_t i = 0; i < 10; ++i) net.report(static_cast<int>(stations - i % std::min<uint32_t>(stations, 5)));
    const uint32_t tMax = net.now() + hoursOr(params, 4);
    uint32_t doneMs = 0;
    while (net.now() < tMax) {
        net.run(net.now() + 1000);
        if (!doneMs && net.downArrivedMs.size() == stations) doneMs = net.now();
        bool closed = true;
        for (const auto& report : net.reports()) closed = closed && report->closed;
        if (doneMs && closed) break;
    }
    std::vector<uint32_t> times;
    for (const auto& entry : net.downArrivedMs) times.push_back((entry.second - started) / 1000);
    uint32_t p50, maximum;
    percentiles(times, p50, maximum);
    std::string extra = ",\"down_stations\":" + std::to_string(stations) +
                        ",\"down_arrived\":" + std::to_string(net.downArrivedMs.size()) +
                        ",\"down_p50_s\":" + std::to_string(p50) + ",\"down_max_s\":" + std::to_string(maximum);
    emit(params, clique ? "budzet_slysza_sie" : "budzet_lancuchy", net, extra);
}

// 8. Wrogi węzeł obok stacji 7: podaje ramki z cudzym `src`, daje HACK i porzuca.
void hostile(const Params& params, bool withBeacon) {
    const int attacker = static_cast<int>(params.hops) + 1;
    Net net(params.hops + 2, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, 700);
    for (int neighbour : {6, 7, 8}) net.link(attacker, neighbour, params.p);
    net.setParents(attacker, 7, -1);
    Node& evil = net.node(attacker);
    evil.dropper = true;
    evil.forgeRelays = {net.node(6).id, net.node(7).id, net.node(8).id};
    net.start();
    net.run(10 * 60000);
    std::vector<uint16_t> victims;
    for (uint32_t i = 9; i <= params.hops; ++i) victims.push_back(net.node(static_cast<int>(i)).id);
    if (withBeacon) evil.lowRank = true;
    else net.forgeVictims(attacker, victims);
    std::vector<int> stations;
    for (uint32_t i = withBeacon ? 8 : 9; i <= params.hops; ++i) stations.push_back(static_cast<int>(i));
    if (withBeacon) {
        // Zanim atak: stacja 8 traci rodzica z planu, a jedynym kandydatem dynamicznym jest napastnik.
        net.run(net.now() + 5 * 60000);
        net.setLinkPermille(8, 7, 0);
    }
    schedule(net, stations, params.reports, params.spreadS, net.now() + hoursOr(params, 6));
    std::string extra = routesAlong(net, net.node(15).id, 15);
    uint32_t atAttacker = 0;
    for (int neighbour : {6, 7, 8}) {
        const Node& n = net.node(neighbour);
        for (uint16_t victim : victims) atAttacker += n.shelter->routes().down(victim) == evil.id;
    }
    extra += ",\"routes_via_attacker\":" + std::to_string(atAttacker);
    extra += ",\"station8_parent\":" + std::to_string(net.node(8).shelter->routes().parent());
    emit(params, withBeacon ? "wrogi_beacon" : "wrogi_src", net, extra);
}

// Kalibracja: pojedyncze rozsyłanie w pustym łańcuchu ma dotrzeć z prawdopodobieństwem p^hops, bo nie ma kolizji
// (jedna ramka naraz) ani ponowień. Porównanie z tym wzorem sprawdza model kanału i tor rozsyłania.
void calibrate(const Params& params) {
    const uint32_t trials = params.reports;
    uint32_t reached = 0;
    uint64_t firstMs = 0;
    for (uint32_t trial = 0; trial < trials; ++trial) {
        Params one = params;
        one.seed = params.seed * 7919u + trial;
        Variant none;
        Net net(params.hops + 1, one.seed, assumptionsFor(one), none);
        for (int i = 0; i < static_cast<int>(params.hops); ++i) net.link(i, i + 1, params.p);
        for (int i = 1; i <= static_cast<int>(params.hops); ++i) net.setParents(i, i - 1, -1);
        net.start();
        net.run(1000);
        for (size_t i = 0; i < net.size(); ++i) net.node(static_cast<int>(i)).nextBeaconMs = 0xFFFFFFFFu;
        net.laptop().enqueue(net.node(static_cast<int>(params.hops)).id, 0x80000001u, 50);
        // Pierwsza powtórka intencji po porażce przychodzi najwcześniej po 48 s; próba kończy się wcześniej.
        net.run(net.now() + 45000);
        const auto at = net.downArrivedMs.find(0x80000001u);
        if (at != net.downArrivedMs.end()) { ++reached; firstMs += at->second - 1000; }
    }
    double expected = 1.0;
    for (uint32_t i = 0; i < params.hops; ++i) expected *= params.p / 1000.0;
    // Wiadomość 50 B to koperta 75 B; ramka rozsyłana bez tagu pary ma 94 B.
    const uint32_t frameMs = lora::frameAirMs(wici_link::HEADER + wici_link::TAG + 75);
    printf("{\"scenario\":\"kalibracja\",\"p\":%u,\"hops\":%u,\"trials\":%u,\"reached\":%u,\"expected_permille\":%u,"
           "\"frame_ms\":%u,\"mean_arrival_ms\":%llu}\n",
           params.p, params.hops, trials, reached, static_cast<uint32_t>(expected * 1000 + 0.5), frameMs,
           static_cast<unsigned long long>(reached ? firstMs / reached : 0));
}

}  // namespace

int main(int argc, char** argv) {
    Params params;
    if (argc < 2) {
        fprintf(stderr, "wici_emulator <scenariusz> [nazwa=wartość ...]\n");
        return 2;
    }
    params.scenario = argv[1];
    for (int i = 2; i < argc; ++i) {
        const std::string arg = argv[i];
        const size_t eq = arg.find('=');
        if (eq == std::string::npos) return 2;
        const std::string name = arg.substr(0, eq);
        const uint32_t value = static_cast<uint32_t>(strtoul(arg.c_str() + eq + 1, nullptr, 10));
        if (name == "seed") params.seed = value;
        else if (name == "p") params.p = value;
        else if (name == "hops") params.hops = value;
        else if (name == "reports") params.reports = value;
        else if (name == "n") params.n = value;
        else if (name == "hours") params.hours = value;
        else if (name == "spread") params.spreadS = value;
        else if (name == "sense") params.sense = value;
        else if (name == "miss") params.miss = value;
        else if (name == "skip") params.skip = value;
        else if (name == "learn") params.variant.learnRoutes = value;
        else if (name == "alternate") params.variant.alternate = value;
        else if (name == "leave") params.variant.leaveAfterS = value;
        else if (name == "hold") params.variant.holdS = value;
        else if (name == "flood") params.variant.floodMsPerStation = value;
        else return 2;
    }
#ifndef WICI_EMU_VARIANT
    if (params.variant.learnRoutes || params.variant.alternate || params.variant.leaveAfterS) {
        fprintf(stderr, "ten plik wykonywalny to obecny kod bez wariantów\n");
        return 2;
    }
#else
    wici_variant::flags.learnRoutes = params.variant.learnRoutes;
    wici_variant::flags.floodStays = params.variant.alternate;
#endif
    const std::string& s = params.scenario;
    if (s == "koniec") reports(params, true);
    else if (s == "cala_siec") reports(params, false);
    else if (s == "zmiana_rodzica") parentChange(params);
    else if (s == "porzucanie_dziecko") blackHole(params, "dziecko");
    else if (s == "porzucanie_koniec") blackHole(params, "koniec");
    else if (s == "porzucanie_wszyscy") blackHole(params, "wszyscy");
    else if (s == "nasycenie") saturation(params);
    else if (s == "fala_beacon") beaconWave(params);
    else if (s == "budzet_slysza_sie") floodBudget(params, true);
    else if (s == "budzet_lancuchy") floodBudget(params, false);
    else if (s == "wrogi_src") hostile(params, false);
    else if (s == "wrogi_beacon") hostile(params, true);
    else if (s == "kalibracja") calibrate(params);
    else return 2;
    return 0;
}
