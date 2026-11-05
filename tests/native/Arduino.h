// TEST-ONLY Arduino API shim: not an ESP32 SDK, firmware binary or live demo source.
#pragma once
#include <cstdint>
#include <cstring>
#include <string>
#include <deque>
class TestSerial {
 public:
  std::deque<char> input;
  std::string output;
  uint32_t baud = 0;
  int rx_pin = -1, tx_pin = -1;
  void begin(uint32_t value) {baud = value;}
  void begin(uint32_t value, uint32_t, int rx, int tx) {baud=value;rx_pin=rx;tx_pin=tx;}
  void updateBaudRate(uint32_t value) {baud = value;}
  void flush() {}
  size_t setRxBufferSize(size_t n) {return n;}
  void setDebugOutput(bool) {}
  void setTxTimeoutMs(uint32_t) {}
  size_t read(uint8_t *p, size_t n) {size_t i=0;while(i<n && !input.empty())p[i++]=(uint8_t)read();return i;}
  size_t write(const uint8_t *p, size_t n) {output.append((const char *)p,n);return n;}
  int available() { return (int)input.size(); }
  int read() { if(input.empty())return -1;char c=input.front();input.pop_front();return (unsigned char)c; }
  void print(const char *s) { output += s; }
  void println(const char *s) { output += s;output += '\n'; }
};
extern TestSerial Serial;
extern TestSerial Serial2;
static const uint32_t SERIAL_8N1=0;
inline uint32_t micros() {static uint32_t t=0;return ++t;}
inline uint32_t &testClockMs() {static uint32_t t=0;return t;}
inline uint32_t millis() {return testClockMs();}
inline void delay(unsigned value) {testClockMs()+=value;}
