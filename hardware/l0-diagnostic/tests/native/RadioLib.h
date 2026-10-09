#pragma once
#include "SPI.h"
constexpr int RADIOLIB_NC=-1,RADIOLIB_ERR_NONE=0,RADIOLIB_SX126X_SYNC_WORD_PRIVATE=0x12;
struct RadioState {int beginCode=0,receiveCode=0,standbyCode=0,readCode=0,txCode=0;unsigned tx=0;String packet;};
extern RadioState radioState;
struct Module {Module(int,int,int,int,SPIClass&,SPISettings) {}};
struct SX1262 {
    SX1262(Module* module) { delete module; }
    void setRfSwitchPins(int rx,int tx) {assert(rx==42 && tx==RADIOLIB_NC);}
    int begin(double f,double bw,int sf,int cr,int sync,int power,int pre,double tcxo) {
        assert(f==869.525 && bw==125 && sf==7 && cr==5 && sync==0x12 && power==0 && pre==8 && tcxo==1.8);
        assert(SPI.depth==0);return radioState.beginCode;
    }
    int setDio2AsRfSwitch(bool enabled) {assert(enabled);return 0;}
    int setRxBoostedGainMode(bool enabled) {assert(enabled);return 0;}
    void setDio1Action(void(*)()) {}
    void clearDio1Action() {}
    int startReceive() {assert(SPI.depth==0);return radioState.receiveCode;}
    int standby() {assert(SPI.depth==0);return radioState.standbyCode;}
    uint32_t getTimeOnAir(size_t) {return 100000;}
    int transmit(String&) {assert(SPI.depth==0);++radioState.tx;return radioState.txCode;}
    int readData(String& packet) {assert(SPI.depth==0);packet=radioState.packet;return radioState.readCode;}
    double getRSSI() {return -60;}
    double getSNR() {return 9;}
};
