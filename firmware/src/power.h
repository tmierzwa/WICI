// SPDX-License-Identifier: MIT
// Pomiar zasilania stacji na płytce v2 (docs/spec/elektronika.md, „progi ogniw”; hardware/plytka-v2/README.md,
// „Pomiar”): napięcie kompletu ogniw AA przez dzielnik włączany kluczem DIV_EN i napięcie wejścia 12 V przez
// stały dzielnik sterownika U5. Tu są tylko reguły; piny i ADC obsługuje main.cpp.
//
// Pomiar ogniw:
// - dzielnik ogniw jest włączony tylko na czas pomiaru (R44 + R45 = 49 kΩ pobierałyby stale około 0,12 mA z 6 V); odczyt
//   najwcześniej SETTLE_MS po włączeniu (filtr 1,8 ms τ na wejściu ADC, README płytki);
// - progi liczą się z filtrowanej średniej z okresów samego odbioru, bo impulsy nadawania chwilowo obniżają
//   napięcie zimnych ogniw. Pomiar nie zaczyna się, dopóki od końca nadawania nie minie AFTER_TX_MS, a nadawanie
//   w trakcie pomiaru go przerywa (pomiar wraca po przerwie);
// - pomiar co PERIOD_MS, pierwszy zaraz po starcie; średnia krocząca z AVERAGE pomiarów, przed zebraniem
//   wszystkich z tych, które są (start z wyczerpanymi ogniwami ma decyzję od razu);
// - `wymien_ogniwa` od średniej poniżej REPLACE_MV, zejście przy średniej co najmniej CLEAR_MV (nowy komplet
//   włożony przy 12 V, jak każe instrukcja). Alarm jest też przy pracy z 12 V bez ogniw (średnia około 0 V):
//   stacja nie ma wtedy rezerwy;
// - kontrolowane wyłączenie przy średniej poniżej SHUTDOWN_MV, tylko przy pracy z ogniw (przy 12 V stacja ma
//   zasilanie). Samo wyłączenie (zapis, `wylaczanie`, `mozna_wyjac`, KILL) robi program wyłącznika.
//
// Źródło zasilania jak łącznik 12 V (elektronika.md, tabela stanów 12 V): ogniwa, gdy pomiar 12 V jest poniżej
// MAINS_OFF_MV albo powyżej MAINS_HIGH_MV (wejście odcięte przez OVP); 12 V od MAINS_ON_MV; w paśmie między
// MAINS_OFF_MV a MAINS_ON_MV stan poprzedni. Przed pierwszym pomiarem i przy pierwszym pomiarze w paśmie
// stacja przyjmuje 12 V: błędne „ogniwa” przy 12 V wyłączyłoby stację, która ma zasilanie, a błędne „12 V”
// przy ogniwach tylko opóźnia wyłączenie do następnego pomiaru poza pasmem.
//
// Wartości PERIOD_MS, AVERAGE, AFTER_TX_MS, CLEAR_MV, rozpoznanie źródła i alarm bez ogniw przyjął właściciel
// 2026-11-18; do sprawdzenia na płytce (czas po nadawaniu oscyloskopem na zimnych ogniwach, progi łącznika).
// Czas w ms z millis(); różnice odporne na przejście przez zero.
// Bez zależności od Arduino; sprawdzany na komputerze (tests/test_firmware_host.py).
#pragma once

#include <stdint.h>

namespace power {

constexpr uint32_t PERIOD_MS = 60000;     // pomiar co minutę
constexpr uint8_t AVERAGE = 5;            // średnia krocząca z 5 pomiarów (5 min)
constexpr uint32_t AFTER_TX_MS = 2000;    // po końcu nadawania tyle bez pomiaru
constexpr uint32_t SETTLE_MS = 20;        // od włączenia DIV_EN do odczytu ADC
constexpr uint32_t CELLS_DIVIDER_X10 = 49;   // R44 39,0 kΩ / R45 10,0 kΩ: V_AA = V_AA_DIV × 4,9
constexpr uint32_t MAINS_DIVIDER = 16;       // R37+R38 / R39: V12 = V_12_DIV × 16 (board_v2.h, VTEST_DIVIDER)
constexpr uint16_t REPLACE_MV = 4400;     // wymien_ogniwa (1,1 V na ogniwo)
constexpr uint16_t CLEAR_MV = 4600;       // zejście wymien_ogniwa
constexpr uint16_t SHUTDOWN_MV = 4000;    // kontrolowane wyłączenie przy pracy z ogniw
constexpr uint16_t MAINS_OFF_MV = 10500;  // łącznik 12 V odłącza najpóźniej tu
constexpr uint16_t MAINS_ON_MV = 12400;   // i załącza najpóźniej tu
constexpr uint16_t MAINS_HIGH_MV = 17000; // powyżej: wejście odcięte przez OVP
constexpr uint16_t MAINS_PRESENT_MV = 8000;  // od tego pomiaru źródło 12 V jest podłączone (alarmy 12 V)

enum class Source : uint8_t { MAINS12, CELLS };
const char* sourceName(Source source);   // "12v" albo "aa" (usb-protocol.md, `power.source`)
// Alarm energii (usb-protocol.md, `power.alarm`; elektronika.md, „Stany zasilania 12 V”), tylko przy pracy z ogniw:
// - MAINS_HIGH (za_wysokie_12v): pomiar 12 V powyżej MAINS_HIGH_MV, łącznik odciął wejście (OVP);
// - MAINS_LOW (odlaczone_12v): źródło 12 V podłączone (pomiar od MAINS_PRESENT_MV), ale za niskie, by łącznik je
//   załączył albo utrzymał (poniżej 10,5 V w pracy albo poniżej 12,4 V przy podłączeniu). Bez przewodu 12 V
//   (pomiar około 0 V) alarmu nie ma, bo stacja może pracować z samych ogniw;
// - REPLACE_CELLS (wymien_ogniwa) ma pierwszeństwo w jednym polu `alarm`, bo bez wymiany stacja się wyłączy; ekran
//   pokazuje każdy z alarmów osobno.
// Próg MAINS_PRESENT_MV (dolna granica zbocza samoczynnego włączenia) przyjął właściciel 2026-11-18.
enum class Alarm : uint8_t { NONE, REPLACE_CELLS, MAINS_LOW, MAINS_HIGH };
// Nagłówkowa (bez power.cpp), bo używa jej też usbproto.cpp.
inline const char* alarmName(Alarm alarm) {
    switch (alarm) {
        case Alarm::REPLACE_CELLS: return "wymien_ogniwa";
        case Alarm::MAINS_LOW: return "odlaczone_12v";
        case Alarm::MAINS_HIGH: return "za_wysokie_12v";
        default: return "none";
    }
}

// Co zrobić teraz z dzielnikiem ogniw.
enum class Step : uint8_t {
    NONE,     // nic
    ENABLE,   // włączyć DIV_EN
    READ,     // odczytać oba ADC, podać sample(), wyłączyć DIV_EN
    DISABLE,  // pomiar przerwany przez nadawanie: wyłączyć DIV_EN
};

class Monitor {
public:
    // Wołać w każdym obiegu pętli. sinceTxMs: czas od końca ostatniego nadawania, 0 w trakcie nadawania,
    // 0xFFFFFFFF bez nadawania od startu (radiolink::Driver::sinceTxMs).
    Step poll(uint32_t nowMs, uint32_t sinceTxMs);
    // Odczyt po Step::READ: napięcia na pinach ADC [mV].
    void sample(uint32_t nowMs, uint32_t cellsPinMv, uint32_t mainsPinMv);
    // Czas do następnego kroku [ms] po ostatnim poll() (pętla czuwania, standby.h).
    uint32_t untilMs(uint32_t nowMs) const;

    bool measured() const { return count_ > 0; }
    uint16_t cellsMv() const { return cellsMv_; }   // średnia krocząca
    uint16_t lastCellsMv() const { return lastCellsMv_; }
    uint16_t mainsMv() const { return mainsMv_; }   // ostatni pomiar
    uint8_t samples() const { return count_; }
    uint32_t aborted() const { return aborted_; }   // pomiary przerwane nadawaniem
    Source source() const { return source_; }
    bool replaceCells() const { return replace_; }  // alarm wymien_ogniwa
    bool mainsHigh() const { return measured() && source_ == Source::CELLS && mainsMv_ > MAINS_HIGH_MV; }
    bool mainsLow() const {
        return measured() && source_ == Source::CELLS && mainsMv_ >= MAINS_PRESENT_MV && mainsMv_ <= MAINS_HIGH_MV;
    }
    Alarm alarm() const {
        return replace_ ? Alarm::REPLACE_CELLS : mainsHigh() ? Alarm::MAINS_HIGH : mainsLow() ? Alarm::MAINS_LOW : Alarm::NONE;
    }
    bool shutdown() const { return measured() && source_ == Source::CELLS && cellsMv_ < SHUTDOWN_MV; }

private:
    bool started_ = false;
    bool settling_ = false;
    uint32_t dueMs_ = 0;       // termin następnego pomiaru
    uint32_t enabledMs_ = 0;   // włączenie DIV_EN
    uint32_t pollMs_ = 0;      // ostatni poll()
    uint32_t sinceTxMs_ = 0xFFFFFFFFu;
    uint16_t ring_[AVERAGE] = {};
    uint8_t next_ = 0;
    uint8_t count_ = 0;
    uint16_t cellsMv_ = 0;
    uint16_t lastCellsMv_ = 0;
    uint16_t mainsMv_ = 0;
    uint32_t aborted_ = 0;
    Source source_ = Source::MAINS12;
    bool replace_ = false;
};

}  // namespace power
