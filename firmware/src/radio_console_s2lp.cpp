// SPDX-License-Identifier: MIT
// S2-LP w programie stacji (stanowisko B, bench-b). Polecenia jak na stanowisku A, z różnicami
// układu: RADIO podaje PARTNUM, VERSION i bajty statusu, STATE stan głównego sterownika, REG
// adres 8-bitowy, FREQ słowo SYNT; SDN <0|1> steruje pinem wyłączenia; CAL nie występuje
// (S2-LP kalibruje VCO sam przy każdym przejściu do LOCK, DS11896 rozdział 5.4.1).
#if defined(WICI_BENCH_B)
#include "radio_console.h"

#include "board.h"
#include "platform.h"
#include "s2lp.h"
#include "s2lp_link.h"
#include "s2lp_p1_registers.h"

namespace radiocon {

const char* const NAME = "S2LP";
const uint16_t RX_FILTER_HZ = p1s2::RX_FILTER_HZ;
const int8_t TX_POWER_DBM = p1s2::TX_POWER_DBM;

namespace {

s2lp::Radio chip(platform::bus(), board::RADIO_CS, board::RADIO_SDN, board::SPI_HZ);
s2lp::LinkDriver driver(chip);
measure::Bench* bench = nullptr;
bool radioOk = false;
bool configured = false;  // tablica P1 zapisana i zweryfikowana odczytem
const uint8_t radioGpios[] = {board::RADIO_GPIO0, board::RADIO_GPIO1, board::RADIO_GPIO2, board::RADIO_GPIO3};

const char* boolName(bool value) { return value ? "true" : "false"; }

void identify() { radioOk = chip.identify().s2lp; }

void printRadio() {
    const s2lp::Identity id = chip.identify();
    radioOk = id.s2lp;
    const s2lp::Status st = chip.status();
    Serial.printf("{\"radio\":\"S2LP\",\"partnumber\":\"0x%02X\",\"partversion\":\"0x%02X\",\"cut\":\"%s\",\"mc_state1\":\"0x%02X\","
                  "\"mc_state0\":\"0x%02X\",\"state\":\"%s\",\"xo_on\":%s,\"sdn\":%s,\"gpio\":[%d,%d,%d,%d],\"irq_seen\":\"0x%08lX\","
                  "\"p1_ok\":%s,\"ok\":%s}\n",
                  id.partNumber, id.version, s2lp::versionName(id.version), st.mcState1, st.mcState0,
                  s2lp::stateName(st.state()), boolName(st.xoOn()), boolName(chip.isShutdown()),
                  digitalRead(board::RADIO_GPIO0), digitalRead(board::RADIO_GPIO1), digitalRead(board::RADIO_GPIO2),
                  digitalRead(board::RADIO_GPIO3), static_cast<unsigned long>(driver.irqSeen()), boolName(configured),
                  boolName(radioOk));
}

void printVerify(const char* step, const s2lp::VerifyResult& result) {
    Serial.printf("{\"%s\":%s,\"checked\":%u,\"mismatches\":%u", step, boolName(result.mismatches == 0), result.checked,
                  result.mismatches);
    if (result.mismatches) {
        Serial.printf(",\"first\":\"%s\",\"reg\":\"0x%02X\",\"expected\":\"0x%02X\",\"actual\":\"0x%02X\"", result.firstName,
                      result.firstAddress, result.expected, result.actual);
    }
    Serial.printf(",\"state\":\"%s\"}\n", s2lp::stateName(chip.status().state()));
}

// Zapis tablicy P1 w READY, weryfikacja odczytem i ponowny zapis FOFF; ustala p1Ok.
s2lp::VerifyResult configureP1() {
    bench->stop();
    const s2lp::VerifyResult result = chip.configure(p1s2::REGISTERS, p1s2::REGISTER_COUNT);
    configured = result.mismatches == 0;
    bench->applyOffset();
    return result;
}

// f_base = f_xo * SYNT / 2^19 / B / D (DS11896, eq. 7); FOFF zmienia SYNT o całe kroki.
void printFrequency() {
    uint8_t synt[4];
    chip.readRegs(s2lp::SYNT3, synt, 4);
    const uint32_t word = (static_cast<uint32_t>(synt[0] & 0x0F) << 24) | (static_cast<uint32_t>(synt[1]) << 16) |
                          (static_cast<uint32_t>(synt[2]) << 8) | synt[3];
    const uint8_t band = (synt[0] & 0x10) ? 8 : 4;
    const double stepHz = static_cast<double>(p1s2::F_XO_HZ) / 524288.0 / band / p1s2::REF_DIVIDER;
    const double hz = word * stepHz;
    Serial.printf("{\"synt\":\"0x%07lX\",\"band\":%u,\"hz\":%.1f,\"target_hz\":%lu,\"error_hz\":%.1f,\"offset_step_hz\":%.2f,"
                  "\"synt_offset\":%ld}\n",
                  static_cast<unsigned long>(word), band, hz, static_cast<unsigned long>(p1s2::CARRIER_HZ), hz - p1s2::CARRIER_HZ,
                  stepHz, static_cast<long>(driver.frequencyOffsetRaw()));
}

void printRssi() {
    const radiolink::Rssi r = driver.rssi();
    Serial.printf("{\"rssi_valid\":%s,\"rssi_dbm\":%d,\"rssi_offset_db\":%d,\"state\":\"%s\"}\n", boolName(r.valid), r.dbm,
                  s2lp::RSSI_OFFSET_DB, s2lp::stateName(chip.status().state()));
}

}  // namespace

radiolink::Driver& link() { return driver; }

void attach(measure::Bench& b) { bench = &b; }

void begin() {
    for (uint8_t pin : radioGpios) pinMode(pin, INPUT);  // GPIO0 = nIRQ, GPIO2 = słowo synchronizacji (J11)
    chip.begin();  // CSn wysoki, SDN niski
}

void start() {
    chip.reset();
    identify();
    if (radioOk) configureP1();
}

bool ok() { return radioOk; }
bool p1Ok() { return configured; }

void report() {
    printRadio();
    if (radioOk) {
        printVerify("verify", chip.verify(p1s2::REGISTERS, p1s2::REGISTER_COUNT));
        printFrequency();
    }
}

void printState() {
    const s2lp::Status st = chip.status();
    Serial.printf("{\"state\":\"%s\",\"mc_state1\":\"0x%02X\",\"mc_state0\":\"0x%02X\",\"xo_on\":%s,\"txbytes\":%u,\"rxbytes\":%u}\n",
                  s2lp::stateName(st.state()), st.mcState1, st.mcState0, boolName(st.xoOn()),
                  chip.readReg(s2lp::TX_FIFO_STATUS), chip.readReg(s2lp::RX_FIFO_STATUS));
}

bool handle(const char* cmd, char* words[], size_t n) {
    if (!strcmp(cmd, "RADIO")) printRadio();
    else if (!strcmp(cmd, "RESET")) {
        // SDN na 1 ms, potem SRES: rejestry wracają do wartości domyślnych, p1_ok = false.
        bench->stop();
        chip.reset();
        configured = false;
        printRadio();
    } else if (!strcmp(cmd, "SDN") && n == 1) {
        bench->stop();
        chip.shutdown(atoi(words[0]) != 0);  // wyłączenie kasuje rejestry
        configured = false;
        Serial.printf("{\"sdn\":%s}\n", boolName(chip.isShutdown()));
    } else if (!strcmp(cmd, "CONFIG")) printVerify("config", configureP1());
    else if (!strcmp(cmd, "VERIFY")) printVerify("verify", chip.verify(p1s2::REGISTERS, p1s2::REGISTER_COUNT));
    else if (!strcmp(cmd, "FREQ")) printFrequency();
    else if (!strcmp(cmd, "IDLE")) {
        bench->stop();
        Serial.printf("{\"idle\":%s}\n", boolName(chip.status().state() == s2lp::STATE_READY));
        printState();
    } else if (!strcmp(cmd, "RSSI")) printRssi();
    else if (!strcmp(cmd, "STATE")) printState();
    else if (!strcmp(cmd, "REG") && n == 1) {
        const uint8_t address = static_cast<uint8_t>(strtoul(words[0], nullptr, 16));
        const uint8_t value = chip.readReg(address);
        const s2lp::Status st = chip.lastStatus();
        Serial.printf("{\"reg\":\"0x%02X\",\"value\":\"0x%02X\",\"mc_state1\":\"0x%02X\",\"mc_state0\":\"0x%02X\"}\n", address, value,
                      st.mcState1, st.mcState0);
    } else return false;
    return true;
}

const char* helpCommands() { return ",\"RADIO\",\"RESET\",\"SDN <0|1>\",\"CONFIG\",\"VERIFY\",\"FREQ\",\"IDLE\",\"RSSI\",\"STATE\",\"REG <hex>\""; }

}  // namespace radiocon

#endif
