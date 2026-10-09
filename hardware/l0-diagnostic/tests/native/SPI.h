#pragma once
#include "Arduino.h"
#include <vector>
constexpr int MSBFIRST=1, LSBFIRST=0, SPI_MODE0=0;
struct SPISettings {
    uint32_t hz;int order;int mode;
    SPISettings(uint32_t h,int o,int m):hz(h),order(o),mode(m) {}
};
struct SPIClass {
    std::array<uint8_t,512*1024> bytes{};
    std::vector<std::vector<uint8_t>> lcd;
    unsigned depth=0,writes=0;
    bool wel=false,corruptRead=false;
    uint8_t op=0;unsigned position=0;uint32_t address=0;
    SPISettings settings{0,MSBFIRST,SPI_MODE0};
    void begin(int=-1,int=-1,int=-1,int=-1) {}
    void beginTransaction(SPISettings s) { assert(depth==0);++depth;settings=s; }
    void endTransaction() { assert(depth==1);--depth; }
    uint8_t transfer(uint8_t value) {
        assert(depth==1);assert(!(pins[8]==LOW && pins[7]==HIGH));
        if(pins[7]==HIGH) {
            assert(settings.order==LSBFIRST);lcd.back().push_back(value);return 0;
        }
        assert(pins[8]==LOW && settings.order==MSBFIRST);
        if(position++==0) {op=value;if(op==0x06)wel=true;return 0;}
        if(op==0x9F) {const uint8_t id[]={0x7f,0x7f,0x7f,0x7f,0x7f,0x7f,0xc2,0x2c,0xa1};assert(position<=10);return id[position-2];}
        if(op==0x05)return 0;
        if(op==0x03 || op==0x02) {
            if(position<=4) {address=(address<<8)|value;return 0;}
            address%=bytes.size();
            if(op==0x03)return bytes[address++]^(corruptRead?1:0);
            if(wel) {bytes[address]=value;++writes;}++address;return 0;
        }
        return 0;
    }
    void transfer(void* buffer,size_t count) {
        auto* data=static_cast<uint8_t*>(buffer);
        for(size_t i=0;i<count;++i)data[i]=transfer(data[i]);
    }
};
extern SPIClass SPI;
