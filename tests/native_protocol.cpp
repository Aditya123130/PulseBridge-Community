// SOFTWARE TEST SHIM ONLY. Compiles the actual sketch logic, not an Espressif target.
#include "native/Arduino.h"
#include <cassert>
#include <iostream>
#include <sstream>
#include <iomanip>
TestSerial Serial;
TestSerial Serial2;
#include "../firmware/PulseBridgeESP32/PulseBridgeESP32.ino"
int main() {
  setup();
  assert(BASE_BAUD==115200 && Serial.baud==115200);
  assert(crc16((const uint8_t*)"123456789",9)==0x29B1);
  std::string line;
  while(std::getline(std::cin,line)) {
    Serial.output.clear();
    if(!line.empty() && line[0]=='@') {testClockMs()+=(uint32_t)std::stoul(line.substr(1));loop();}
    else {
      assert(line.size()%2==0);
      for(size_t i=0;i<line.size();i+=2)Serial.input.push_back((char)std::stoul(line.substr(i,2),nullptr,16));
      while(Serial.available())loop();
    }
    std::ostringstream hex;
    for(unsigned char b:Serial.output)hex<<std::hex<<std::setfill('0')<<std::setw(2)<<(unsigned)b;
    std::cout<<"{\"hex\":\""<<hex.str()<<"\",\"baud\":"<<activeBaud
      <<",\"session\":"<<sessionActive<<",\"binary\":"<<binaryMode<<",\"sequence\":"<<sequence
      <<",\"crc\":"<<crcErrors<<",\"framing\":"<<framingErrors<<",\"rejected\":"<<rejectedRequests
      <<",\"duplicates\":"<<duplicateRequests<<",\"resets\":"<<protocolResets
      <<",\"accepted\":"<<acceptedRequests<<",\"ring_length\":"<<ringLength<<"}"<<std::endl;
  }
}
