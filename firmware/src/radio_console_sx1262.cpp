// SPDX-License-Identifier: MIT
// SX1262 w programie stacji (stacja pilotażowa L0, środowisko l0) w profilu LoRa (lora_profile.h).
// Polecenia jak na stanowiskach A i B, z różnicami układu: RADIO podaje tekst wersji z rejestru 0x0320,
// tryb z bajtu statusu, błędy układu i stany BUSY, DIO1, RXEN; CONFIG i VERIFY dotyczą profilu LoRa
// (pole p1_ok w INFO i RADIO oznacza tu zapisany i zweryfikowany profil LoRa); REG i REGW mają adres
// 16-bitowy; SLEEP sprawdza zachowanie trybu Rx Boosted po uśpieniu. Bez CAL i SDN.
#if defined(WICI_L0)
#include "radio_console.h"

#include "board.h"
#include "cmdargs.h"
#include "lora_profile.h"
#include "platform.h"
#include "sx1262.h"
#include "sx1262_link.h"

namespace radiocon {

const char* const NAME = "SX1262";
const char* const PROFILE = "LoRa";
const int8_t TX_POWER_DBM = lora::TX_POWER_DBM;

namespace {

sx1262::Radio chip(platform::bus(), board::RADIO_CS, board::RADIO_RESET, board::RADIO_BUSY, board::SPI_HZ);
sx1262::LinkDriver driver(chip, board::RADIO_RXEN);
measure::Bench* bench = nullptr;
bool radioOk = false;
bool configured = false;  // profil LoRa zapisany i zweryfikowany odczytem
bool modified = false;    // rejestr zmieniony poleceniem REGW (tylko w trybie przygotowania; CONFIG cofa)

using cmdargs::boolName;

void identify() { radioOk = chip.identify().sx126x; }

void printRadio() {
    const sx1262::Identity id = chip.identify();
    radioOk = id.sx126x;
    const sx1262::Status st = chip.status();
    const uint16_t errors = chip.deviceErrors();
    Serial.printf("{\"radio\":\"SX1262\",\"version\":\"%s\",\"status\":\"0x%02X\",\"state\":\"%s\",\"device_errors\":\"0x%04X\","
                  "\"busy\":%s,\"dio1\":%d,\"rxen\":%s,\"irq_seen\":\"0x%04X\",\"busy_timeouts\":%lu,\"p1_ok\":%s,\"ok\":%s}\n",
                  id.version, st.raw, sx1262::modeName(st.mode()), errors, boolName(chip.busy()), digitalRead(board::RADIO_DIO1),
                  boolName(driver.rxenHigh()), driver.irqSeen(), static_cast<unsigned long>(chip.busyTimeouts()), boolName(configured),
                  boolName(radioOk));
}

void printVerify(const char* step, const sx1262::VerifyResult& result) {
    Serial.printf("{\"%s\":%s,\"checked\":%u,\"mismatches\":%u", step, boolName(result.mismatches == 0), result.checked,
                  result.mismatches);
    if (result.mismatches) {
        Serial.printf(",\"first\":\"%s\",\"reg\":\"0x%04X\",\"expected\":\"0x%02X\",\"actual\":\"0x%02X\"", result.firstName,
                      result.firstAddress, result.expected, result.actual);
    }
    Serial.printf(",\"state\":\"%s\"}\n", driver.stateName());
}

// Zapis profilu LoRa po resecie układu, weryfikacja odczytem i ponowny zapis FOFF; ustala p1Ok.
sx1262::VerifyResult configureLora() {
    bench->stop();
    chip.reset();
    const sx1262::VerifyResult result = driver.configure();
    configured = result.mismatches == 0;
    modified = false;
    bench->applyOffset();
    return result;
}

// f_RF = słowo x f_xtal / 2^25 (karta, SetRfFrequency); FOFF zmienia słowo o całe kroki.
void printFrequency() {
    const uint32_t word = driver.rfWord();
    const double hz = word * driver.frequencyStepHz();
    Serial.printf("{\"rf_word\":\"0x%08lX\",\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,\"offset_step_hz\":%.4f,\"rf_offset\":%ld,"
                  "\"bw_hz\":%lu,\"sf\":%u}\n",
                  static_cast<unsigned long>(word), hz, static_cast<unsigned long>(lora::CARRIER_HZ), hz - lora::CARRIER_HZ,
                  driver.frequencyStepHz(), static_cast<long>(driver.frequencyOffsetRaw()), static_cast<unsigned long>(lora::BANDWIDTH_HZ),
                  lora::SPREADING_FACTOR);
}

void printRssi() {
    const radiolink::Rssi r = driver.rssi();
    Serial.printf("{\"rssi_valid\":%s,\"rssi_dbm\":%d,\"state\":\"%s\"}\n", boolName(r.valid), r.dbm, driver.stateName());
}

bool parseAddress(const char* word, uint32_t& address) { return cmdargs::parseUint(word, 0, 0xFFFF, address, 16); }

}  // namespace

radiolink::Driver& link() { return driver; }

void printProfile() {
    Serial.printf("\"carrier_hz\":%lu,\"bw_hz\":%lu,\"sf\":%u,\"cr\":\"4/%u\",\"preamble\":%u,\"sync_word\":\"0x%02X\",",
                  static_cast<unsigned long>(lora::CARRIER_HZ), static_cast<unsigned long>(lora::BANDWIDTH_HZ), lora::SPREADING_FACTOR,
                  lora::CODING_RATE, lora::PREAMBLE_SYMBOLS, lora::SYNC_WORD);
}

void attach(measure::Bench& b) { bench = &b; }

void begin() {
    pinMode(board::RADIO_DIO1, INPUT);
    chip.begin();    // NSS wysoki, NRESET napędzany wysoko
    driver.begin();  // RXEN niski
}

void start() {
    chip.reset();
    identify();
    if (radioOk) configureLora();
}

bool ok() { return radioOk; }
// Rejestry zmienione przez REGW: nadawanie tylko w trybie przygotowania, poza nim do CONFIG.
bool p1Ok() { return configured && (!modified || bench->prep); }

bool check() {
    // lost: profil utracony w pracy (nie poleceniem RESET ani REGW), więc wraca bez CONFIG.
    static bool lost = false;
    identify();
    if (!radioOk) { lost = lost || configured; configured = false; return false; }
    if (configured ? modified || !driver.profileLost() : !lost) return false;
    configureLora();
    lost = !configured;
    return configured;
}

void report() {
    printRadio();
    if (radioOk) {
        printVerify("verify", driver.verify());
        printFrequency();
    }
}

void printState() {
    const sx1262::Status st = chip.status();
    Serial.printf("{\"state\":\"%s\",\"status\":\"0x%02X\",\"rxen\":%s,\"busy\":%s}\n", sx1262::modeName(st.mode()), st.raw,
                  boolName(driver.rxenHigh()), boolName(chip.busy()));
}

bool handle(const char* cmd, char* words[], size_t n) {
    if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        // NRESET na 1 ms: rejestry wracają do wartości domyślnych (Rx w trybie oszczędnym), p1_ok = false.
        bench->stop();
        chip.reset();
        configured = false;
        printRadio();
    } else if (!strcmp(cmd, "CONFIG")) printVerify("config", configureLora());
    else if (!strcmp(cmd, "VERIFY")) printVerify("verify", driver.verify());
    else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "IDLE")) {
        bench->stop();
        Serial.printf("{\"idle\":%s}\n", boolName(chip.status().mode() == sx1262::MODE_STBY_RC));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        uint32_t address = 0;
        if (!parseAddress(words[0], address)) { Serial.println("{\"error\":\"REG <0000-FFFF>\"}"); return true; }
        const uint8_t value = chip.readReg(static_cast<uint16_t>(address));
        Serial.printf("{\"reg\":\"0x%04X\",\"value\":\"0x%02X\",\"status\":\"0x%02X\"}\n", static_cast<unsigned>(address), value,
                      chip.lastStatus().raw);
    } else if (!strcmp(cmd, "REGW") && n == 2) {
        // Zapis rejestru do prób (np. słowo synchronizacji 0x0740/0x0741 wobec RNode), tylko w trybie
        // przygotowania; VERIFY pokaże różnicę wobec profilu, CONFIG ją cofa.
        if (!bench->prep) {
            Serial.println("{\"error\":\"preparation mode off: PREP 1\"}");
            return true;
        }
        uint32_t address = 0, value = 0;
        if (!parseAddress(words[0], address) || !cmdargs::parseUint(words[1], 0, 0xFF, value, 16)) {
            Serial.println("{\"error\":\"REGW <0000-FFFF> <00-FF>\"}");
            return true;
        }
        bench->stop();
        chip.writeReg(static_cast<uint16_t>(address), static_cast<uint8_t>(value));
        modified = true;
        Serial.printf("{\"reg\":\"0x%04X\",\"written\":\"0x%02X\",\"value\":\"0x%02X\"}\n", static_cast<unsigned>(address),
                      static_cast<unsigned>(value), chip.readReg(static_cast<uint16_t>(address)));
    } else if (!strcmp(cmd, "SLEEP")) {
        // Uśpienie z ciepłym startem i wybudzenie: Rx Boosted (0x08AC = 0x96) ma przetrwać dzięki liście
        // rejestrów zachowywanych (radio.md, profil LoRa). Odbiór wraca poleceniem RX.
        bench->stop();
        uint8_t gain = 0;
        const bool woke = driver.sleepAndWake(gain);
        Serial.printf("{\"sleep\":%s,\"rx_gain\":\"0x%02X\",\"boosted\":%s,\"state\":\"%s\"}\n", boolName(woke), gain,
                      boolName(gain == sx1262::RX_GAIN_BOOSTED), driver.stateName());
    } else return false;
    return true;
}

const char* helpCommands() {
    return ",\"RADIO\",\"RESET\",\"CONFIG\",\"VERIFY\",\"FREQ\",\"IDLE\",\"RSSI\",\"STATE\",\"REG <0000-FFFF>\",\"REGW <0000-FFFF> <00-FF>\",\"SLEEP\"";
}

}  // namespace radiocon

#endif
