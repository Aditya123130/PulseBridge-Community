// Actual v2 firmware logic with test-only UART stubs. No physical timing claims.
#include "native/Arduino.h"
#include <cassert>
#include <iostream>
TestSerial Serial;
TestSerial Serial2;
#include "../firmware/legacy/PulseBridgeESP32Fast/PulseBridgeESP32Fast.ino"
static void drain() {while(Serial.available())loop();}
static void text(const char *body) {
 char wire[120];snprintf(wire,sizeof(wire),"%s*%04X\n",body,crc16((const uint8_t*)body,strlen(body)));
 for(char c:std::string(wire))Serial.input.push_back(c);
 Serial.output.clear();drain();
}
static std::string poll(unsigned id,bool corrupt=false) {
 uint8_t p[14]={'P','B',2,1};put32(p+4,0xABCDEF01);put32(p+8,id);
 uint16_t crc=crc16(p,12);p[12]=(uint8_t)crc;p[13]=(uint8_t)(crc>>8);
 if(corrupt)p[12]^=1;
 for(uint8_t b:p)Serial.input.push_back((char)b);
 Serial.output.clear();drain();return Serial.output;
}
int main(){
 setup();assert(Serial.baud==230400);
 assert(crc16((const uint8_t*)"123456789",9)==0x29B1);
 text("B,2,ABCDEF01,921600");assert(binaryMode&&Serial.baud==921600);
 assert(Serial.output.find("A,2,ABCDEF01,921600,")==0);
 std::string first=poll(1);assert(first.size()==34);assert(first==poll(1));
 assert(poll(2,true).empty());
 std::cout.write(first.data(),first.size());
 for(unsigned i=2;i<=1600;++i){std::string frame=poll(i);assert(frame.size()==34);std::cout.write(frame.data(),frame.size());}
 testClockMs()=lastValidMs+1601;loop();assert(!binaryMode&&Serial.baud==230400);
 text("P,1,ABCDEF01,9000");assert(Serial.output.find("D,1,")==0);
 return 0;
}
