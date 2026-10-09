// Exercise actual main.cpp + FRAM + Sharp drivers; hardware/timer/RF are simulated.
#include "Arduino.h"
#include "SPI.h"
#include "RadioLib.h"
#include "sharp.h"
#include <iostream>
uint32_t mockNow=0;
std::array<int,49> pins;
bool timerOk=true,buzzerTimerOk=true;
unsigned buzzerDuty=0;
SerialMock Serial;
EspMock ESP;
SPIClass SPI;
RadioState radioState;
void gpioHook(int pin,int value) {
    if(pin==8 && pins[pin]!=value) {
        if(value==HIGH && SPI.op==0x02)SPI.wel=false;
        SPI.op=0;SPI.position=0;SPI.address=0;
    }
    if(pin==7 && value==HIGH && pins[pin]!=value)SPI.lcd.emplace_back();
}
namespace sharp {
bool Display::beginExtcomin() { return timerOk; }
uint32_t Display::extcominCounter() const { return extcominOk_?123:0; }
}
#include "../../src/main.cpp"
void feed(const std::string& line) {
    for(char c:line)Serial.input.push_back(c);
    pollUsb();
}
bool contains(const char* text) {return Serial.output.find(text)!=std::string::npos;}
int main(int argc,char** argv) {
    assert(argc==2);pins.fill(HIGH);
    const std::string scenario=argv[1];
    if(scenario=="lcd-failure")timerOk=false;
    setup();assert(SPI.writes==0);assert(SPI.depth==0);
    if(scenario=="console") {
        std::cout<<Serial.output<<std::flush;Serial.output.clear();
        std::string line;
        while(std::getline(std::cin,line)) {
            feed(line+"\n");std::cout<<Serial.output<<std::flush;Serial.output.clear();
        }
    } else if(scenario=="boot") {
        assert(radioOk && framOk && lcdOk && buzzerOk);
        assert(contains("INFO l0-0.2 001122334455 1"));
        assert(pins[7]==LOW && pins[8]==HIGH && pins[16]==HIGH && pins[15]==LOW && buzzerDuty==0);
        assert(!SPI.lcd.empty() && SPI.lcd.front()==std::vector<uint8_t>({4,0}));
    } else if(scenario=="fram") {
        assert(memory.read(diagnostic::FRAM_SIZE,nullptr,0));
        assert(memory.write(diagnostic::FRAM_SIZE,nullptr,0));
        assert(!memory.read(diagnostic::FRAM_SIZE,nullptr,1));
        Serial.output.clear();execute("FRAMTEST ERASE 00000001");
        assert(contains("FRAM_DONE 00000001 WRITE") && !contains("ERR "));
        std::cout<<Serial.output;
        unsigned writes=SPI.writes;
        setup();assert(SPI.writes==writes);Serial.output.clear();execute("FRAMVERIFY 00000001");
        assert(SPI.writes==writes && contains("FRAM_DONE 00000001 VERIFY"));
        SPI.bytes[0]^=1;Serial.output.clear();execute("FRAMVERIFY 00000001");
        assert(contains("ERR fram_compare") && !contains("FRAM_DONE"));
    } else if(scenario=="guard") {
        execute("GUARD ERASE");assert(mode==Mode::Guard && SPI.depth==1 && pins[8]==LOW);
        assert(contains("GUARD_START"));unsigned writes=SPI.writes;
        for(const char* cmd:{"RDID","LCD 1","PAUSE 10000","TX TEST","MIXSTART ERASE"})execute(cmd);
        assert(SPI.writes==writes && SPI.depth==1 && radioState.tx==0);
        loop();assert(SPI.writes==writes+32);
        execute("STOP");assert(mode==Mode::Idle && SPI.depth==0 && pins[8]==HIGH);
        radioState.standbyCode=-1;execute("GUARD ERASE");assert(mode==Mode::Idle && SPI.depth==0);
    } else if(scenario=="mixed") {
        mockNow=0xFFFFFF00;startMixed();assert(mode==Mode::Mixed);
        uint32_t before=millis();execute("PAUSE 10000");assert(millis()==before);
        for(const char* cmd:{"LCD 1","RDID","LED 1","GUARD ERASE","FRAMVERIFY 1"})execute(cmd);
        assert(mode==Mode::Mixed && SPI.writes==0);
        Serial.output.clear();SPI.lcd.clear();
        while(mode==Mode::Mixed) {mockNow+=200;pollMixed();SPI.lcd.clear();}
        assert(mixCycles==4500 && mixErrors==0 && lcdFrames==mixCycles);
        assert(contains("MIX_DONE 4500 0 4500 900000 400"));
        std::cout<<Serial.output;
        startMixed();mockNow+=1001;pollMixed();assert(mixErrors==1);stop();
    } else if(scenario=="usb") {
        Serial.output.clear();feed(std::string(91,'X')+"GUARD ERASE\n");
        assert(mode==Mode::Idle && contains("ERR usb_line") && !contains("GUARD_START"));
        feed("GUARD ERASE\r\n");assert(mode==Mode::Guard);feed("STOP\n");assert(mode==Mode::Idle);
        for(const char* cmd:{"FRAMTEST ERASE -1\n","FRAMTEST ERASE 100000000\n","FRAMTEST ERASE +1\n"})feed(cmd);
        assert(SPI.writes==0);
        feed(std::string("STATUS\0GUARD ERASE\n",19));assert(mode==Mode::Idle);
        feed("STATUS\n");assert(contains("CMD STATUS"));
    } else if(scenario=="radio") {
        mockNow=0xFFFFFF00;
        pins[board::SW_CISZA]=LOW;execute("TX TEST");assert(radioState.tx==0 && contains("BLOCKED SILENCE"));
        pins[board::SW_CISZA]=HIGH;execute("TX TEST");assert(radioState.tx==1);
        execute("TX TEST");assert(radioState.tx==1 && contains("ERR cooldown"));
        mockNow+=1300;execute("TX TEST");assert(radioState.tx==2);
        radioState.packet=String("OK\0BAD",6);received=true;Serial.output.clear();pollRadio();
        assert(contains("ERR rx_payload") && !contains("RX "));
        radioState.receiveCode=-1;listen();assert(!radioOk);
    } else if(scenario=="lcd-failure") {
        assert(!lcdOk && pins[16]==LOW && SPI.lcd.empty());
        Serial.output.clear();execute("LCD 1");assert(contains("ERR lcd_timer") && !contains("LCD_DONE"));
        startMixed();assert(mode==Mode::Idle);
    } else return 2;
    assert(SPI.depth==0);
}
