// SPDX-License-Identifier: MIT
// Szacunek godzin pracy z ogniw na płytce v2 (docs/spec/oprogramowanie.md, `zasilanie_aa` i `ogniwa_czas`):
// bilans energii, bo stacja nie mierzy prądu. Przy każdym pomiarze zasilania (power.h, co 60 s) program dolicza
// energię pobraną z ogniw od poprzedniego pomiaru, z czasu pracy MCU bez uśpienia, czasu uśpienia i czasu
// nadawania razy stałe prądy szyny 3,3 V. Godziny = pozostała energia kompletu / średni pobór z ostatnich pomiarów.
//
// - Energia liczy się tylko przy pracy z ogniw; przy 12 V ogniwa nie oddają energii.
// - Pobór z ogniw = moc szyny 3,3 V / sprawność przetwornicy × V / (V − spadek diody ogniw).
// - Średni pobór to średnia wykładnicza z pomiarów z wagą AVERAGE_WEIGHT (około pół godziny przy pomiarze co
//   minutę), więc nagły ruch albo cisza zmienia szacunek stopniowo.
// - Przy alarmie wymien_ogniwa szacunek pokazuje najwyżej 1 h, bo tak mówi tekst alarmu; inaczej najmniej 1 h.
// - Nowy komplet: licznik zeruje się, gdy pierwszy pomiar po starcie albo po przerwie bez ogniw (poniżej
//   ABSENT_MV) jest wyższy o co najmniej FRESH_STEP_MV od ostatniego zapisanego. Ten sam komplet bez obciążenia
//   (12 V) ma wyższe napięcie niż pod obciążeniem (praca z ogniw), stąd zależność od źródła:
//   - to samo źródło: porównanie wprost;
//   - zapisane przy 12 V, teraz praca z ogniw: porównanie wprost, bo pod obciążeniem ten sam komplet ma niższe
//     napięcie, więc skok o FRESH_STEP_MV oznacza inny komplet;
//   - zapisane przy pracy z ogniw, teraz 12 V: skok niczego nie dowodzi. Program zostawia zapisane napięcie spod
//     obciążenia i rozstrzyga przy pierwszym pomiarze z ogniw, czyli zanim policzy energię. Pomiar przy 12 V niższy
//     niż zapisane + FRESH_STEP_MV kończy oczekiwanie bez zerowania, bo nowy komplet pod obciążeniem byłby jeszcze
//     niższy. Przykład: stacja wyłączyła się przy 4,0 V na ogniwach, nowy komplet włożony przy 12 V pokazuje 7,1 V,
//     a licznik zeruje się, gdy po odłączeniu 12 V ogniwa pod obciążeniem pokażą ponad 4,4 V.
//   Częściowo zużyty komplet też może wyzerować licznik; wtedy szacunek jest za wysoki aż do wymien_ogniwa.
//   Ten sam komplet włożony z powrotem po odpoczynku może pod obciążeniem chwilowo pokazać o FRESH_STEP_MV więcej
//   niż przed wyłączeniem i też wyzerować licznik; sprawdzić na płytce.
// - Licznik i ostatnie napięcie leżą w FRAM (journal::Journal::writeCells), więc przetrwają restart i wyłączenie.
//
// Stałe pochodzą z modelu energii (software/reference/obliczenia.py: komplet 4 × 4,5 Wh × 0,8, MCU 45 mA w pracy
// i 3 mA w uśpieniu, ekran 0,5 mA, FRAM, przyciski i nadzorca 0,5 mA, dioda 0,35 V), z pomiaru modułu Wio-SX1262
// z 2026-11-17 (odbiór 6,2 mA, nadawanie około 60 mA; hardware/xiao-wici/evidence/prad-wio-2026-11-17.md) i z
// oszacowania sprawności LTC3115-1 przy 3,3 V (74–83%, hardware/r02/zasilanie.md; tu środek 78%). Metodę, miejsce
// w FRAM i rozpoznanie nowego kompletu przyjął właściciel 2026-11-18; stałe trzeba zmierzyć na płytce v2.
// Bez zależności od Arduino; sprawdzany na komputerze (tests/test_firmware_host.py).
#pragma once

#include <stdint.h>

namespace cells {

constexpr uint32_t CAPACITY_UWH = 14400000;   // użytkowa energia kompletu 4 × AA Li-FeS2 [µWh]
constexpr uint32_t RAIL_MV = 3300;
constexpr uint32_t AWAKE_UA = 45000;          // MCU bez uśpienia
constexpr uint32_t SLEEP_UA = 3000;           // MCU w lekkim uśpieniu (z płytką DevKitC i wybudzeniami)
constexpr uint32_t RADIO_RX_UA = 6200;        // Wio-SX1262 w odbiorze (stale)
constexpr uint32_t RADIO_TX_UA = 60000;       // Wio-SX1262 w nadawaniu 13 dBm (zamiast odbioru)
constexpr uint32_t OTHER_UA = 1000;           // ekran, FRAM, przyciski, nadzorca
constexpr uint32_t EFFICIENCY_PERCENT = 78;   // LTC3115-1 przy 3,3 V
constexpr uint32_t DIODE_MV = 350;            // dioda ogniw
constexpr uint32_t AVERAGE_WEIGHT = 30;       // średnia wykładnicza poboru: nowy pomiar z wagą 1/30
constexpr uint16_t ABSENT_MV = 1000;          // poniżej: brak ogniw
constexpr uint16_t FRESH_STEP_MV = 400;       // skok napięcia przy nowym komplecie

// Stan w FRAM: zużyta energia, ostatnie napięcie ogniw i źródło przy nim.
struct Saved {
    bool valid = false;
    uint32_t usedUwh = 0;
    uint16_t lastMv = 0;
    bool lastOnCells = false;
};

class Estimator {
public:
    void begin(const Saved& saved);
    // Po każdym pomiarze zasilania: czasy od poprzedniego pomiaru [ms] (praca bez uśpienia, uśpienie, nadawanie),
    // ostatni pomiar ogniw [mV], średnia ogniw [mV] (do spadku na diodzie) i źródło. Zwraca true, gdy stan trzeba
    // zapisać w FRAM (saved()).
    bool update(uint32_t awakeMs, uint32_t sleptMs, uint32_t txMs, uint16_t lastMv, uint16_t meanMv, bool onCells);
    Saved saved() const;

    bool known() const { return averageUw_ > 0; }   // jest średni pobór z pracy z ogniw
    uint32_t hours(bool replaceCells) const;        // szacunek do ekranu; 0 bez szacunku
    uint32_t usedUwh() const { return usedUwh_; }
    uint32_t averageUw() const { return averageUw_; }
    uint32_t freshSets() const { return freshSets_; }   // nowe komplety od startu

    // Pobór z ogniw [µW] dla podanych udziałów czasu (do testu i POWER).
    static uint32_t inputUw(uint32_t awakeMs, uint32_t sleptMs, uint32_t txMs, uint16_t meanMv);

private:
    bool started_ = false;
    bool absent_ = false;      // ostatni pomiar bez ogniw
    uint32_t usedUwh_ = 0;
    uint16_t lastMv_ = 0;
    bool lastOnCells_ = false;
    bool pending_ = false;     // skok przy 12 V wobec napięcia spod obciążenia: rozstrzyga pierwszy pomiar z ogniw
    uint16_t storedMv_ = 0;    // ostatnie zapisane napięcie (próg zapisu)
    uint32_t averageUw_ = 0;
    uint32_t freshSets_ = 0;
    uint64_t remainderUwms_ = 0;   // reszta energii poniżej 1 µWh [µW·ms]
};

}  // namespace cells
