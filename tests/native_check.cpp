// Compile the ACTUAL sketch against small API stubs for portable protocol checks.
// This does not replace an Arduino target build or physical hardware validation.
#include "native/Arduino.h"
#include <cassert>
#include <cstdio>
#include <iostream>
TestSerial Serial;
TestSerial Serial2;
#include "../firmware/legacy/PulseBridgeESP32/PulseBridgeESP32.ino"

static std::string poll(unsigned id) {
  char body[60],wire[80];
  snprintf(body,sizeof(body),"P,1,ABCDEF01,%u",id);
  snprintf(wire,sizeof(wire),"%s*%04X\n",body,crc16(body,strlen(body)));
  for(char c:std::string(wire))Serial.input.push_back(c);
  Serial.output.clear();loop();return Serial.output;
}
int main() {
  setup();assert(crc16("123456789",9)==0x29B1);
  std::string first=poll(1);assert(!first.empty());
  assert(first==poll(1)); // Idempotent resend, no new sequence.
  Serial.output.clear();
  for(char c:std::string("P,1,ABCDEF01,2*0000\n"))Serial.input.push_back(c);
  loop();assert(Serial.output.empty()); // Bad request CRC must have no response.
  for(int i=0;i<200;++i)Serial.input.push_back('x');
  Serial.input.push_back('\n');loop();assert(Serial.output.empty());
  std::cout<<first;
  for(unsigned i=2;i<=1600;++i)std::cout<<poll(i);
  return 0;
}
