// SPDX-License-Identifier: MIT
// Scenariusze emulatora WICI-Link. Wynik: jeden wiersz JSON na przebieg; opis założeń w README.md.
// Użycie: wici_emulator <scenariusz> [seed=1] [p=900] [learn=0] [alternate=0] [leave=0] [hold=0]
//         [flood=0] [n=0] [reports=50] [hops=15] [hours=0]; pozostałe parametry opisuje README.md
#include <stdlib.h>

#include <algorithm>
#include <map>
#include <string>

#include "emulator.h"

using namespace emu;

namespace {

struct Params {
    std::string scenario;
    uint64_t seed = 1;
    uint32_t p = 900, hops = 15, reports = 50, n = 0, hours = 0, spreadS = 300;
    uint32_t sense = 1, miss = 20, skip = 0, trace = 0, hole = 0, selective = 0, fake = 0, fullrun = 0;
    uint32_t fakeEveryS = 0, fromEnd = 0, k1Stats = 0;
    uint32_t two = 0, bridge = 0, dead = 0, moved = 0, leaves = 1, downRounds = 0, downEveryS = 600, fakeBroadcast = 0;
    uint32_t evilParent = 0, evilDrop = 0, stale = 0, dead2 = 0;
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
    uint32_t closed = 0, probesClosed = 0;
    for (const auto& report : net.reports()) {
        if (report->probe) continue;
        const auto at = net.arrivedMs.find(report->id);
        if (at != net.arrivedMs.end()) arrive.push_back((at->second - report->createdMs) / 1000);
        if (report->closed) { ++closed; close.push_back((report->closedMs - report->createdMs) / 1000); }
    }
    for (const auto& report : net.reports()) {
        if (!report->probe) continue;
        probesClosed += report->closed;
    }
    uint32_t arriveP50, arriveMax, closeP50, closeMax;
    percentiles(arrive, arriveP50, arriveMax);
    percentiles(close, closeP50, closeMax);
    NodeStats total;
    uint64_t maxAir = 0;
    uint32_t maxSilent = 0, over30 = 0, probes = 0, longestMute = 0;
    for (size_t i = 0; i < net.size(); ++i) {
        const NodeStats& s = net.node(static_cast<int>(i)).stats;
        total.txUnicast += s.txUnicast; total.txFlood += s.txFlood; total.txHack += s.txHack; total.txBeacon += s.txBeacon;
        total.refusedBudget += s.refusedBudget; total.deferrals += s.deferrals; total.txDrops += s.txDrops;
        total.rxCollision += s.rxCollision; total.rxLost += s.rxLost; total.hackRefused += s.hackRefused;
        total.parentChanges += s.parentChanges; total.leaves += s.leaves; total.rxRejected += s.rxRejected;
        maxAir = std::max(maxAir, s.airMs);
        maxSilent = std::max(maxSilent, s.maxSilentS);
        over30 += s.maxSilentS >= 1800;
        probes += s.probes;
        longestMute = std::max(longestMute, s.longestMuteS);
    }
    std::string attack;
    if (net.k1Stats) {
        uint32_t overCap = 0, unicastRefused = 0, over25 = 0, full60 = 0, stationsFull = 0, floods120 = 0;
        uint64_t overCapMs = 0;
        for (size_t i = 0; i < net.size(); ++i) {
            const NodeStats& s = net.node(static_cast<int>(i)).stats;
            overCap += s.floodOverCap; overCapMs += s.floodOverCapMs; unicastRefused += s.unicastRefused;
            over25 = std::max(over25, s.over25S); full60 = std::max(full60, s.full60S);
            stationsFull += s.full60S > 0;
            floods120 = std::max(floods120, s.maxFloods120S);
        }
        attack = ",\"flood_over_cap\":" + std::to_string(overCap) + ",\"flood_over_cap_s\":" + std::to_string(overCapMs / 1000) +
                 ",\"unicast_refused\":" + std::to_string(unicastRefused) + ",\"max_over25_s\":" + std::to_string(over25) +
                 ",\"max_full60_s\":" + std::to_string(full60) + ",\"stations_full60\":" + std::to_string(stationsFull) +
                 ",\"max_floods_120s\":" + std::to_string(floods120);
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
           net.variant().floodMsPerStation, seconds, net.realReports(), net.arrivedCount, closed,
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
           "\"duplicates\":%u,\"settled\":%u,\"floods_deferred\":%u,\"off_planned\":%u,"
           "\"probes\":%u,\"probes_closed\":%u,\"longest_mute_s\":%u%s%s}\n",
           laptop.floods, laptop.routed, laptop.refused, laptop.openIntents(), laptop.deliveredIntents,
           laptop.duplicates, laptop.rejected, laptop.floodsDeferred, offPlanned, probes, probesClosed, longestMute,
           attack.c_str(), extra.c_str());
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
    net.runUntil(tMaxMs, [&] { return net.allClosed(); });
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
    net.trace = params.trace;
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
    net.trace = params.trace;
    chain(net, params, 700);
    net.start();
    net.run(10 * 60000);
    const int hole = params.hole ? static_cast<int>(params.hole) : static_cast<int>(params.hops) / 2 + 1;
    if (params.selective == 1) net.node(hole).selective = true;
    else if (params.selective == 0) net.node(hole).dropper = true;  // 2: uczciwy przekaźnik, tylko podsuwa ramki
    if (params.fake) net.node(hole).fakeDownTo = net.node(hole + 1).id;
    net.node(hole).fakeNoRoute = params.fake == 2;
    const uint32_t started = net.now();
    std::vector<int> stations;
    if (who == "dziecko") stations.push_back(hole + 1);
    else if (who == "koniec") stations.push_back(static_cast<int>(params.hops));
    else for (uint32_t i = hole + 1; i <= params.hops; ++i) stations.push_back(static_cast<int>(i));
    schedule(net, stations, params.reports, params.spreadS, net.now() + hoursOr(params, 8));
    std::string extra = ",\"child_parent\":" + std::to_string(net.node(hole + 1).shelter->routes().parent());
    const uint32_t childLeave = net.node(hole + 1).stats.firstLeaveMs;
    extra += ",\"child_left_s\":" + std::to_string(childLeave ? (childLeave - started) / 1000 : 0);
    extra += ",\"hole\":" + std::to_string(hole);
    emit(params, "porzucanie_" + who, net, extra);
}

// 3a. Stanowisko wyłączone na `hours` (domyślnie 2 h), a ruch tylko z końca łańcucha. Sprawdza, czy próbki i progi
// przenoszą cały łańcuch na zapasowych rodziców i jak szybko sieć wraca.
void outage(const Params& params) {
    Net net(params.hops + 1, params.seed, assumptionsFor(params), params.variant);
    chain(net, params, params.skip ? params.skip : 700);
    net.start();
    net.run(10 * 60000);
    const int far = static_cast<int>(params.hops);
    schedule(net, {far}, 5, 60, net.now() + 3600000);
    const uint32_t off = net.now();
    net.laptop().setOpen(false);
    const auto airNow = [&] {
        uint64_t total = 0;
        for (size_t i = 0; i < net.size(); ++i) total += net.node(static_cast<int>(i)).stats.airMs;
        return total;
    };
    const auto statTotal = [&](uint32_t NodeStats::*field) {
        uint32_t total = 0;
        for (size_t i = 0; i < net.size(); ++i) total += net.node(static_cast<int>(i)).stats.*field;
        return total;
    };
    const auto offPlanned = [&] {
        uint32_t total = 0;
        for (size_t i = 1; i < net.size(); ++i) total += net.node(static_cast<int>(i)).shelter->routes().parent() != net.node(static_cast<int>(i)).planned;
        return total;
    };
    const uint64_t airBefore = airNow();
    const uint32_t leavesBefore = statTotal(&NodeStats::leaves), probesBefore = statTotal(&NodeStats::probes);
    size_t firstReport = net.reports().size();
    for (uint32_t i = 0; i < 5; ++i) {
        net.run(net.now() + 300000);
        net.report(far);
    }
    net.run(off + hoursOr(params, 2));
    const uint32_t leavesOff = statTotal(&NodeStats::leaves) - leavesBefore, probesOff = statTotal(&NodeStats::probes) - probesBefore;
    const uint32_t airOff = static_cast<uint32_t>((airNow() - airBefore) / 1000), offAtReturn = offPlanned();
    uint64_t maxAirOff = 0;
    for (size_t i = 1; i < net.size(); ++i) maxAirOff = std::max<uint64_t>(maxAirOff, net.node(static_cast<int>(i)).stats.airMs);
    net.epochSeed = 2;
    net.restartRoot(2);
    const uint32_t returned = net.now();
    uint32_t offAfterHour = 0, offAfter2h = 0, allClosedS = 0;
    for (uint32_t minute = 1; minute <= 360; ++minute) {
        net.run(returned + minute * 60000);
        if (minute == 60) offAfterHour = offPlanned();
        if (minute == 121) offAfter2h = offPlanned();
        if (!allClosedS && net.allClosed()) allClosedS = minute * 60;
    }
    uint32_t oldClosedMax = 0;
    for (size_t i = firstReport; i < net.reports().size(); ++i) {
        const Report& report = *net.reports()[i];
        if (!report.probe && report.closed && report.closedMs > returned) oldClosedMax = std::max(oldClosedMax, (report.closedMs - returned) / 1000);
    }
    std::string extra = ",\"leaves_off\":" + std::to_string(leavesOff) + ",\"probes_off\":" + std::to_string(probesOff);
    extra += ",\"air_off_s\":" + std::to_string(airOff) + ",\"off_planned_return\":" + std::to_string(offAtReturn);
    extra += ",\"off_planned_1h\":" + std::to_string(offAfterHour) + ",\"off_planned_2h\":" + std::to_string(offAfter2h);
    extra += ",\"closed_after_return_s\":" + std::to_string(allClosedS) + ",\"last_closed_after_return_s\":" + std::to_string(oldClosedMax);
    emit(params, "przerwa", net, extra);
}

// 5a. Drzewo: dwa pnie do 15 skoków z odgałęzieniami, razem 50 stacji; dzieci jednego rodzica słyszą się wzajemnie.
// Każda stacja zgłasza przez godzinę, potem brak nowych. Sprawdza zakleszczenie poza łańcuchem.
void tree(const Params& params) {
    struct Place { int parent, grand; };
    std::vector<Place> places(1, Place{-1, -1});
    const auto add = [&](int parent) {
        const int grand = places[static_cast<size_t>(parent)].parent;
        places.push_back(Place{parent, grand});
        return static_cast<int>(places.size()) - 1;
    };
    std::vector<int> trunk[2];
    for (int t = 0; t < 2; ++t) {
        int last = 0;
        for (int depth = 1; depth <= 15; ++depth) {
            last = add(last);
            trunk[t].push_back(last);
        }
    }
    for (int t = 0; t < 2; ++t) {
        for (int fork : {4, 9}) {  // odgałęzienia na głębokości 5 i 10, po 5 stacji
            int last = trunk[t][static_cast<size_t>(fork)];
            for (int depth = 0; depth < 5; ++depth) last = add(last);
        }
    }
    Net net(places.size(), params.seed, assumptionsFor(params), params.variant);
    for (size_t i = 1; i < places.size(); ++i) {
        const Place& place = places[i];
        net.link(static_cast<int>(i), place.parent, params.p);
        if (params.skip && place.grand >= 0) net.link(static_cast<int>(i), place.grand, params.skip);
        net.setParents(static_cast<int>(i), place.parent, params.skip && place.grand >= 0 ? place.grand : -1);
        for (size_t j = 1; j < i; ++j)
            if (places[j].parent == place.parent) net.interfere(static_cast<int>(i), static_cast<int>(j));
    }
    if (!net.variant().learnRoutes) {
        // Plan roota jak w łańcuchu: stacja za pierwszą stacją swojego pnia.
        for (size_t i = 1; i < places.size(); ++i) {
            int top = static_cast<int>(i);
            while (places[static_cast<size_t>(top)].parent != 0) top = places[static_cast<size_t>(top)].parent;
            if (top != static_cast<int>(i)) net.rootPlan(net.node(static_cast<int>(i)).id, net.node(top).id);
        }
    }
    net.start();
    net.run(10 * 60000);
    net.trackStall = true;
    const uint32_t load = net.now() + 3600000;
    uint32_t next = net.now();
    size_t station = 1;
    while (net.now() < load) {
        net.run(next);
        net.report(static_cast<int>(station));
        station = station % (places.size() - 1) + 1;
        next += params.spreadS * 1000 / static_cast<uint32_t>(places.size() - 1);
    }
    net.runUntil(net.now() + hoursOr(params, 8), [&] { return net.allClosed(); });
    uint32_t minHacks = 0xFFFFFFFFu;
    for (size_t bucket = 1; bucket < net.hacksPerBucket.size() && bucket * 600000 < load; ++bucket)
        minHacks = std::min(minHacks, net.hacksPerBucket[bucket]);
    std::string extra = ",\"min_hacks_per_10min_loaded\":" + std::to_string(minHacks == 0xFFFFFFFFu ? 0 : minHacks);
    emit(params, "drzewo", net, extra);
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
    net.runUntil(net.now() + hoursOr(params, 8), [&] { return net.allClosed(); });
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
    const uint32_t endMs = net.now() + hoursOr(params, 6);
    schedule(net, stations, params.reports, params.spreadS, endMs);
    if (params.fullrun) net.run(endMs);  // próba bezczynnej sieci: napastnik wywołuje próbki do końca czasu
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

// 8a. Sąsiad z poprawnym tagiem pary podsuwa ramki K1 w dół do numerów bez drogi, a poza tym przekazuje uczciwie.
// Bez `n`: łańcuch z napastnikiem w miejscu `hole`, celem są sąsiedzi. Z `n`: wszyscy się słyszą, celem osiem stacji.
// `fakeevery=0` to ta sama sieć bez ataku, jako punkt odniesienia.
void floodAttack(const Params& params) {
    const bool clique = params.n != 0;
    const int stations = clique ? static_cast<int>(params.n) : static_cast<int>(params.hops);
    Net net(static_cast<size_t>(stations) + 1, params.seed, assumptionsFor(params), params.variant);
    net.k1Stats = true;
    if (clique) {
        for (int a = 0; a <= stations; ++a)
            for (int b = a + 1; b <= stations; ++b) net.link(a, b, params.p);
        for (int s = 1; s <= stations; ++s) net.setParents(s, s <= 49 ? 0 : (s - 1) % 49 + 1, -1);
    } else {
        chain(net, params, params.skip);
    }
    net.start();
    net.run(10 * 60000);
    const int attacker = clique ? 1 : params.hole ? static_cast<int>(params.hole) : stations / 2 + 1;
    Node& evil = net.node(attacker);
    evil.fakeEveryMs = params.fakeEveryS * 1000;
    if (params.fakeEveryS) {
        if (clique) {
            for (int s = 2; s <= 9; ++s) evil.fakeTargets.push_back(net.node(s).id);
        } else {
            const int reach = params.skip ? 2 : 1;
            for (int s = attacker - reach; s <= attacker + reach; ++s)
                if (s >= 1 && s <= stations && s != attacker) evil.fakeTargets.push_back(net.node(s).id);
        }
    }
    std::vector<int> senders;
    if (params.fromEnd) senders.push_back(stations);
    else if (clique) for (int s = stations; s > stations - 10; --s) senders.push_back(s);
    else for (int s = 1; s <= stations; ++s) if (s != attacker) senders.push_back(s);
    const uint32_t endMs = net.now() + hoursOr(params, 4);
    schedule(net, senders, params.reports, params.spreadS, endMs);
    net.run(endMs);  // ten sam czas w każdym przebiegu: obciążenie jest porównywalne
    emit(params, "atak_k1", net);
}

// 8b. Reguła „rozsyłanie w dół tylko od rodzica”. Kształty: łańcuch, `n` słyszących się albo `two=1`: dwa łańcuchy
// z łączami poprzecznymi i bez rodziców zapasowych, jedyny kształt, w którym kopia od sąsiada jest drogą obejścia.
// `dead`: stacja gaśnie na początku ruchu. `moved`, `leaves`: stacja zmienia rodzica po 30 min, z blokadą `hold`.
// `downrounds`: tyle serii wiadomości w dół co `downevery` sekund do stacji za awarią albo do wszystkich.
Net* currentNet = nullptr;

void floodRule(const Params& params) {
    const bool clique = params.n != 0, two = params.two != 0;
    const int depth = static_cast<int>(params.hops);
    // `evilparent` w łańcuchu: dodatkowy węzeł napastnika obok tej stacji, poza numeracją łańcucha.
    const bool evilChain = params.evilParent && !clique;
    const int stations = clique ? static_cast<int>(params.n) : two ? 2 * depth : depth + (evilChain ? 1 : 0);
    Net net(static_cast<size_t>(stations) + 1, params.seed, assumptionsFor(params), params.variant);
    net.k1Stats = true;
    net.trace = params.trace;
    currentNet = &net;
#ifdef WICI_EMU_VARIANT
    wici_variant::flags.floodCopy = [](unsigned kind, unsigned short own, const unsigned char* header) { currentNet->noteCopy(kind, own, header); };
    wici_variant::flags.hopEvent = [](unsigned kind, unsigned short own, unsigned short other, unsigned short recipient) {
        currentNet->noteHop(kind, own, other, recipient);
    };
#endif
    if (clique) {
        for (int a = 0; a <= stations; ++a)
            for (int b = a + 1; b <= stations; ++b) net.link(a, b, params.p);
        for (int s = 1; s <= stations; ++s) net.setParents(s, s <= 49 ? 0 : (s - 1) % 49 + 1, -1);
        if (!net.variant().learnRoutes)
            for (int s = 50; s <= stations; ++s) net.rootPlan(net.node(s).id, net.node((s - 1) % 49 + 1).id);
    } else if (two) {
        for (int column = 0; column < 2; ++column) {
            const int first = column * depth;
            for (int d = 1; d <= depth; ++d) {
                const int s = first + d, parent = d == 1 ? 0 : s - 1;
                net.link(s, parent, params.p);
                net.setParents(s, parent, -1);
                if (d > 1 && !net.variant().learnRoutes) net.rootPlan(net.node(s).id, net.node(first + 1).id);
            }
        }
        // Jedno łącze obejścia: przy wielu odbiorca słyszy kopię wprost od sąsiedniego łańcucha i przekaźnik nie jest potrzebny.
        // Do stacji dwa skoki bliżej roota, bo rodzic dynamiczny musi mieć niższą rangę (Table::usable).
        if (params.bridge) net.link(static_cast<int>(params.bridge), depth + static_cast<int>(params.bridge) - 2, 700);
        else for (int d = 1; d <= depth; ++d) net.link(d, depth + d, 700);
    } else {
        chain(net, params, params.skip, depth);
    }
    const int victim = static_cast<int>(params.evilParent);
    if (evilChain) {
        // Napastnik z tagiem pary słyszy stację `victim` i jej sąsiadów; jego rodzic z planu to stacja nad nią.
        for (int s = victim - 1; s <= victim + 1; ++s) net.link(stations, s, params.p);
        net.setParents(stations, victim - 1, -1);
        if (!net.variant().learnRoutes) net.rootPlan(net.node(stations).id, net.node(1).id);
    }
    // Awaria dwóch sąsiednich stacji: jedynym wyjściem stacji za nimi jest łącze do stacji nad awarią.
    if (params.dead2 && !clique) net.link(static_cast<int>(params.dead) + 2, static_cast<int>(params.dead) - 1, 700);
    // Próba starej drogi w łańcuchu: łącze stacji 2 ze stacją 5, która nie ma jej za rodzica.
    if (params.stale && !clique) net.link(2, 5, 700);
    net.start();
    net.run(10 * 60000);
    const int attacker = evilChain ? stations : clique ? 1 : params.hole ? static_cast<int>(params.hole) : depth / 2 + 1;
    std::vector<int> victims;
    if (params.evilParent) {
        // Napastnik ogłasza fałszywie niską rangę; ofiary tracą rodzica planowego i zapasowego, więc jedynym
        // kandydatem jest napastnik (w sieci słyszącej się: najniższa ranga wśród wszystkich).
        Node& evil = net.node(attacker);
        evil.lowRank = true;
        evil.dropper = params.evilDrop != 0;
        if (evilChain) {
            victims.push_back(victim);
            net.setLinkPermille(victim, victim - 1, 0);
            if (victim >= 2) net.setLinkPermille(victim, victim - 2, 0);
        } else {
            for (int s = 2; s < 2 + victim; ++s) {
                victims.push_back(s);
                net.setLinkPermille(s, 0, 0);
            }
        }
    }
    if (params.fakeEveryS && params.evilParent) {
        Node& evil = net.node(attacker);
        evil.fakeEveryMs = params.fakeEveryS * 1000;
        if (evilChain) {
            for (int s = victim - 1; s <= victim + 1; ++s) evil.fakeTargets.push_back(net.node(s).id);
        } else {
            for (int s : victims) evil.fakeTargets.push_back(net.node(s).id);
        }
    } else if (params.fakeEveryS) {
        Node& evil = net.node(attacker);
        evil.fakeEveryMs = params.fakeEveryS * 1000;
        evil.fakeBroadcast = params.fakeBroadcast != 0;
        if (clique) {
            for (int s = 2; s <= 9; ++s) evil.fakeTargets.push_back(net.node(s).id);
            // Dzieci napastnika: tu reguła z założenia przepuszcza.
            for (int s = 50; s <= stations; s += 49) evil.fakeTargets.push_back(net.node(s).id);
        } else {
            const int reach = params.skip ? 2 : 1;
            for (int s = attacker - reach; s <= attacker + reach; ++s)
                if (s >= 1 && s <= depth && s != attacker) evil.fakeTargets.push_back(net.node(s).id);
        }
    }
    const uint32_t started = net.now(), endMs = started + hoursOr(params, 4);
    if (params.dead) net.node(static_cast<int>(params.dead)).dead = true;
    if (params.dead && params.dead2) net.node(static_cast<int>(params.dead) + 1).dead = true;
    const auto alive = [&](int s) {
        return s != static_cast<int>(params.dead) && !(params.dead2 && s == static_cast<int>(params.dead) + 1) &&
               !(evilChain && s == stations);
    };
    std::vector<int> targets, senders;
    const int fault = params.dead ? static_cast<int>(params.dead) : static_cast<int>(params.moved);
    if (fault && !clique) {
        const int last = fault <= depth ? depth : 2 * depth;
        for (int s = fault; s <= last; ++s) if (alive(s)) targets.push_back(s);
    } else if (fault) {
        // W sieci słyszącej się: stacja i jej dzieci.
        for (int s = fault; s <= stations; s += 49) if (alive(s)) targets.push_back(s);
    } else if (params.stale) {
        // Adresaci, do których nadawca ma starą drogę przez sąsiada bez tej drogi.
        if (clique) for (int i = 0; i < static_cast<int>(params.stale); ++i) targets.push_back(2 + i);
        else targets.push_back(12);
    } else {
        for (int s = 1; s <= stations; ++s) if (alive(s)) targets.push_back(s);
    }
    if (params.fromEnd) senders.push_back(targets.empty() ? stations : targets.back());
    else for (int s = 1; s <= stations; ++s) if (alive(s) && !(params.fakeEveryS && s == attacker)) senders.push_back(s);
    struct Event { uint32_t atMs; int kind, station; };
    std::vector<Event> events;
    for (uint32_t i = 0; i < params.reports; ++i)
        events.push_back({started + static_cast<uint32_t>(static_cast<uint64_t>(i) * params.spreadS * 1000 / std::max(params.reports, 1u)), 0,
                          senders[i % senders.size()]});
    for (uint32_t round = 0; round < params.downRounds; ++round)
        for (size_t i = 0; i < targets.size(); ++i)
            events.push_back({started + round * params.downEveryS * 1000 + static_cast<uint32_t>(i) * 1000, 1, targets[i]});
    if (params.moved)
        for (uint32_t i = 0; i < params.leaves; ++i) events.push_back({started + 1800000 + i * 60000, 2, static_cast<int>(params.moved)});
    if (params.stale)
        for (uint32_t round = 0; round < params.downRounds; ++round) events.push_back({started + round * params.downEveryS * 1000, 3, 0});
    std::stable_sort(events.begin(), events.end(), [](const Event& a, const Event& b) { return a.atMs < b.atMs; });
    uint32_t downId = 0x80000000u;
    std::map<uint32_t, uint32_t> downSent;
    // Czas, przez który ofiara ma napastnika za rodzica, próbkowany co minutę.
    uint32_t victimMinutes = 0, sampledMinutes = 0, nextSampleMs = started;
    const auto runTo = [&](uint32_t untilMs) {
        while (nextSampleMs <= untilMs) {
            net.run(nextSampleMs);
            nextSampleMs += 60000;
            if (victims.empty()) continue;
            ++sampledMinutes;
            for (int v : victims) victimMinutes += net.node(v).shelter->routes().parent() == net.node(attacker).id;
        }
        net.run(untilMs);
    };
    const auto injectStale = [&]() {
#ifdef WICI_EMU_VARIANT
        // Nadawca ma starą drogę do adresata przez sąsiada, dla którego nie jest rodzicem, a sąsiad tej drogi nie ma.
        if (clique) {
            for (int i = 0; i < static_cast<int>(params.stale); ++i)
                net.node(0).root->routes().learn(net.node(2 + i).id, net.node(50 + i).id, true);
        } else {
            wici_route::Table& at5 = net.node(5).shelter->routes();
            at5.forget(net.node(12).id, at5.down(net.node(12).id));
            net.node(2).shelter->routes().learn(net.node(12).id, net.node(5).id, true);
        }
#endif
    };
    for (const Event& event : events) {
        runTo(event.atMs);
        if (event.kind == 3) { injectStale(); continue; }
        if (event.kind == 0) net.report(event.station);
        else if (event.kind == 1) {
            downSent[++downId] = net.now();
            net.laptop().enqueue(net.node(event.station).id, downId, 50);
        } else net.leave(net.node(event.station), net.nowS());
    }
    runTo(endMs);
    std::vector<uint32_t> times;
    for (const auto& sent : downSent) {
        const auto at = net.downArrivedMs.find(sent.first);
        if (at != net.downArrivedMs.end()) times.push_back((at->second - sent.second) / 1000);
    }
    uint32_t p50, maximum;
    percentiles(times, p50, maximum);
    uint32_t forwarded = 0, heard = 0, lost = 0;
    for (const auto& copy : net.refusedCopies) {
        const bool sent = net.forwardedCopies.count(copy) != 0, fromParent = net.parentCopies.count(copy) != 0;
        forwarded += sent;
        heard += fromParent;
        lost += fromParent && !sent;
    }
    // Ta sama miara bez warunku odrzucenia: kopia od rodzica usłyszana przez przekaźnik, ale nieprzekazana. Punkt
    // odniesienia, bo kopia może przepaść też z obciążenia (pełna kolejka, wygaśnięcie).
    uint32_t parentCopies = 0, parentUnsent = 0;
    for (const auto& copy : net.parentCopies) {
        const uint16_t recipient = static_cast<uint16_t>(copy.second[3]) << 8 | copy.second[4];
        if (recipient == copy.first || (recipient >= 900 && recipient < 950)) continue;
        ++parentCopies;
        parentUnsent += net.forwardedCopies.count(copy) == 0;
    }
    // Właściwa pułapka: kopia od rodzica uznana za widzianą, choć ta stacja jej nie przekazała.
    uint32_t trapped = 0, parentFull = 0;
    for (const auto& copy : net.seenCopies) trapped += net.forwardedCopies.count(copy) == 0;
    for (const auto& copy : net.fullCopies) parentFull += net.forwardedCopies.count(copy) == 0;
    std::string extra = ",\"parent_seen_unsent\":" + std::to_string(trapped) + ",\"parent_full_unsent\":" + std::to_string(parentFull) +
                        ",\"parent_copies\":" + std::to_string(parentCopies) + ",\"parent_unsent\":" + std::to_string(parentUnsent) +
                        ",\"down_total\":" + std::to_string(downSent.size()) + ",\"down_arrived\":" + std::to_string(times.size()) +
                        ",\"down_p50_s\":" + std::to_string(p50) + ",\"down_max_s\":" + std::to_string(maximum) +
                        ",\"refused_real\":" + std::to_string(net.refusedCopies.size()) +
                        ",\"refused_then_forwarded\":" + std::to_string(forwarded) +
                        ",\"refused_parent_heard\":" + std::to_string(heard) + ",\"refused_parent_lost\":" + std::to_string(lost) +
                        ",\"refused_unicast\":" + std::to_string(net.refusedUnicast) +
                        ",\"refused_unicast_attack\":" + std::to_string(net.refusedUnicastAttack) +
                        ",\"refused_rounds\":" + std::to_string(net.refusedRounds) +
                        ",\"refused_rounds_on_parent\":" + std::to_string(net.refusedRoundsOnParent) +
                        ",\"refused_forgets\":" + std::to_string(net.refusedForgets) +
                        ",\"refused_parent_changes\":" + std::to_string(net.refusedParentChanges) +
                        ",\"failed_rounds\":" + std::to_string(net.failedRounds) +
                        ",\"victim_on_attacker_pm\":" + std::to_string(sampledMinutes ? victimMinutes * 1000 / (sampledMinutes * victims.size()) : 0);
    emit(params, "regula_rodzica", net, extra);
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
        else if (name == "trace") params.trace = value;
        else if (name == "hole") params.hole = value;
        else if (name == "selective") params.selective = value;
        else if (name == "fake") params.fake = value;
        else if (name == "fullrun") params.fullrun = value;
        else if (name == "leaven") params.variant.leaveCount = value;
        else if (name == "permessage") params.variant.perMessage = value;
        else if (name == "probe") params.variant.probeS = value;
        else if (name == "probeevery") params.variant.probeEveryS = value;
        else if (name == "probemode") params.variant.probeMode = value;
        else if (name == "learn") params.variant.learnRoutes = value;
        else if (name == "alternate") params.variant.alternate = value;
        else if (name == "leave") params.variant.leaveAfterS = value;
        else if (name == "hold") params.variant.holdS = value;
        else if (name == "flood") params.variant.floodMsPerStation = value;
        else if (name == "sticky") params.variant.stickyRoutes = value;
        else if (name == "k1flood") params.variant.k1Flood = value;
        else if (name == "floodparent") params.variant.floodFromParent = value;
        else if (name == "two") params.two = value;
        else if (name == "bridge") params.bridge = value;
        else if (name == "dead") params.dead = value;
        else if (name == "moved") params.moved = value;
        else if (name == "leaves") params.leaves = value;
        else if (name == "downrounds") params.downRounds = value;
        else if (name == "downevery") params.downEveryS = value;
        else if (name == "fakebroadcast") params.fakeBroadcast = value;
        else if (name == "evilparent") params.evilParent = value;
        else if (name == "evildrop") params.evilDrop = value;
        else if (name == "stale") params.stale = value;
        else if (name == "dead2") params.dead2 = value;
        else if (name == "fakeevery") params.fakeEveryS = value;
        else if (name == "fromend") params.fromEnd = value;
        else if (name == "nopool") params.variant.noPool = value;
        else return 2;
    }
#ifndef WICI_EMU_VARIANT
    if (params.variant.learnRoutes || params.variant.alternate || params.variant.leaveAfterS || params.variant.leaveCount ||
        params.variant.k1Flood || params.variant.stickyRoutes || params.variant.floodFromParent != 2) {
        fprintf(stderr, "ten plik wykonywalny to obecny kod bez wariantów\n");
        return 2;
    }
#else
    wici_variant::flags.learnRoutes = params.variant.learnRoutes;
    wici_variant::flags.floodStays = params.variant.alternate;
    wici_variant::flags.stickyRoutes = params.variant.stickyRoutes;
    wici_variant::flags.k1FloodKeepsPriority = params.variant.k1Flood;
    wici_variant::flags.floodFromParent = params.variant.floodFromParent;
#endif
    const std::string& s = params.scenario;
    if (s == "koniec") reports(params, true);
    else if (s == "cala_siec") reports(params, false);
    else if (s == "zmiana_rodzica") parentChange(params);
    else if (s == "porzucanie_dziecko") blackHole(params, "dziecko");
    else if (s == "porzucanie_koniec") blackHole(params, "koniec");
    else if (s == "porzucanie_wszyscy") blackHole(params, "wszyscy");
    else if (s == "nasycenie") saturation(params);
    else if (s == "przerwa") outage(params);
    else if (s == "drzewo") tree(params);
    else if (s == "fala_beacon") beaconWave(params);
    else if (s == "budzet_slysza_sie") floodBudget(params, true);
    else if (s == "budzet_lancuchy") floodBudget(params, false);
    else if (s == "wrogi_src") hostile(params, false);
    else if (s == "wrogi_beacon") hostile(params, true);
    else if (s == "atak_k1") floodAttack(params);
    else if (s == "regula_rodzica") floodRule(params);
    else if (s == "kalibracja") calibrate(params);
    else return 2;
    return 0;
}
