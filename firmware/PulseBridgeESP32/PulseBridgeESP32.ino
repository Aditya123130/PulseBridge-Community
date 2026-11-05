/* PulseBridge 7 / wire protocol 3. ONE sketch for USB cable operation.
 * No GPIO data wires. All movements are SYNTHETIC test data.
 * REQUIRED before compile: select the actual board profile below AND the
 * matching Arduino Tools > Board. See docs/USB_SETUP.md. No target is guessed.
 * 1 classic ESP32 + onboard USB-UART; 2 S3 + USB-UART; 3 C3 + USB-UART;
 * 4 S3 native Hardware CDC/JTAG; 5 C3 native Hardware CDC/JTAG.
 * UART0: 115200 boot/ASCII; negotiate binary 460800 or 921600 (experimental).
 * Native CDC: same protocol; baud is a logical profile, NOT USB wire speed.
 */
#include "board_config.h"
#include <Arduino.h>
#include <esp_system.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if PB_BOARD_PROFILE == 0
#error "Choose PB_BOARD_PROFILE 1..5 after verifying the chip and USB connector; read docs/USB_SETUP.md"
#elif PB_BOARD_PROFILE == 1
#if !defined(CONFIG_IDF_TARGET_ESP32)
#error "Profile 1 requires classic ESP32 / Tools > ESP32 Dev Module"
#endif
#elif PB_BOARD_PROFILE == 2 || PB_BOARD_PROFILE == 4
#if !defined(CONFIG_IDF_TARGET_ESP32S3)
#error "This profile requires ESP32-S3 / select the exact S3 board"
#endif
#elif PB_BOARD_PROFILE == 3 || PB_BOARD_PROFILE == 5
#if !defined(CONFIG_IDF_TARGET_ESP32C3)
#error "This profile requires ESP32-C3 / select the exact C3 board"
#endif
#else
#error "Unsupported PB_BOARD_PROFILE"
#endif
#define PB_NATIVE_CDC (PB_BOARD_PROFILE == 4 || PB_BOARD_PROFILE == 5)
#if PB_NATIVE_CDC
#if !ARDUINO_USB_CDC_ON_BOOT || !ARDUINO_USB_MODE
#error "Native profiles require USB CDC On Boot Enabled and Hardware CDC and JTAG mode"
#endif
#else
#if ARDUINO_USB_CDC_ON_BOOT
#error "USB-UART profiles require USB CDC On Boot Disabled; Serial must be UART0"
#endif
#include <driver/uart.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#endif

static const uint8_t PROTOCOL_VERSION = 3;
static const uint32_t BASE_BAUD = 115200, LINK_IDLE_MS = 2000;
static const size_t REQUEST_BYTES = 14, RESPONSE_BYTES = 34;
static uint32_t bootId, sequence = 0, rngState, symbolCounts[6] = {0};
static uint32_t activeBaud = BASE_BAUD, activeNonce = 0, lastValidMs = 0;
static bool binaryMode = false, sessionActive = false, haveCache = false, discardLine = false;
static uint32_t cachedRequest = 0;
static uint8_t binaryInput[REQUEST_BYTES], binaryOutput[RESPONSE_BYTES];
static size_t ringHead = 0, ringLength = 0, textLength = 0;
static char textInput[96], asciiOutput[160];
static uint32_t crcErrors=0, framingErrors=0, rejectedRequests=0, duplicateRequests=0;
static uint32_t protocolResets=0, acceptedRequests=0, txErrors=0;
static_assert(sizeof(binaryInput)==14 && sizeof(binaryOutput)==34, "Wire lengths changed");

static uint16_t crc16(const uint8_t *bytes, size_t length) {
  uint16_t crc=0xFFFF;
  for (size_t i=0;i<length;++i) {
    crc ^= (uint16_t)bytes[i] << 8;
    for (uint8_t b=0;b<8;++b)
      crc=(crc&0x8000)?(uint16_t)((crc<<1)^0x1021):(uint16_t)(crc<<1);
  }
  return crc; // CCITT-FALSE: "123456789" -> 0x29B1
}
static uint32_t get32(const uint8_t *p) {
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p,uint32_t n) {
  for(uint8_t i=0;i<4;++i)p[i]=(uint8_t)(n>>(8*i));
}
static bool number(const char *s,uint32_t &out,int base) {
  if(!s || !*s || strlen(s)>(base==16?8U:10U))return false;
  for(const char *p=s;*p;++p)
    if(!((*p>='0'&&*p<='9') || (base==16 && ((*p>='a'&&*p<='f')||(*p>='A'&&*p<='F')))))return false;
  uint64_t n=strtoull(s,NULL,base);if(n>UINT32_MAX)return false;out=(uint32_t)n;return true;
}
static void writeWire(const uint8_t *p,size_t n) {
  if(Serial.write(p,n)!=n)++txErrors;
}
static void textReply(const char *body) {
  char wire[192];
  int n=snprintf(wire,sizeof(wire),"%s*%04X\n",body,crc16((const uint8_t*)body,strlen(body)));
  if(n>0 && (size_t)n<sizeof(wire))writeWire((const uint8_t*)wire,n);
}
static void setBaud(uint32_t baud) {
#if !PB_NATIVE_CDC
  Serial.flush(); // Control plane only; no per-packet flush.
  Serial.updateBaudRate(baud);
  uart_set_rx_full_threshold(UART_NUM_0,14);
  uart_set_rx_timeout(UART_NUM_0,1); // 1 UART symbol, NOT 1 millisecond.
#endif
  activeBaud=baud;
}
static void resetParser() {ringHead=ringLength=textLength=0;discardLine=false;}
static void resetLink() {
  setBaud(BASE_BAUD);
#if !PB_NATIVE_CDC
  uart_flush_input(UART_NUM_0);
#endif
  binaryMode=sessionActive=haveCache=false;activeNonce=0;resetParser();++protocolResets;
}
static uint32_t nextRandom() {
  rngState^=rngState<<13;rngState^=rngState>>17;rngState^=rngState<<5;return rngState;
}
static void emitSignal(uint32_t nonce,uint32_t request) {
  if(!sessionActive || nonce!=activeNonce){++rejectedRequests;return;}
  if(haveCache && request==cachedRequest) {
    ++duplicateRequests;lastValidMs=millis();
  } else {
    uint32_t distance=request-cachedRequest;
    if(haveCache && (distance==0 || distance>=0x80000000UL)){++rejectedRequests;return;}
    uint32_t stamp=micros(); // uint32 wrap at ~71.6 min; metadata, never Pi latency.
    uint8_t symbol=sequence%6;++sequence;
    uint32_t ordinal=++symbolCounts[symbol];
    int32_t movement=(int32_t)(nextRandom()%10001)-5000;
    movement+=(int32_t)(nextRandom()%10001)-5000;
    if(ordinal%17==0){movement=24000+(int32_t)(nextRandom()%10001);if((ordinal/17)%2==0)movement=-movement;}
    if(PB_SCENARIO==1)movement=0;
    else if(PB_SCENARIO==2)movement=100+(int32_t)(nextRandom()%901);
    else if(PB_SCENARIO==3)movement=(ordinal%2?30000:-30000);
    binaryOutput[0]='P';binaryOutput[1]='B';binaryOutput[2]=PROTOCOL_VERSION;binaryOutput[3]=2;
    put32(binaryOutput+4,nonce);put32(binaryOutput+8,request);put32(binaryOutput+12,bootId);
    put32(binaryOutput+16,sequence);put32(binaryOutput+20,stamp);put32(binaryOutput+24,(uint32_t)movement);
    binaryOutput[28]=symbol;binaryOutput[29]=1;binaryOutput[30]=binaryOutput[31]=0;
    uint16_t crc=crc16(binaryOutput,32);binaryOutput[32]=(uint8_t)crc;binaryOutput[33]=(uint8_t)(crc>>8);
    if(!binaryMode) {
      char body[136];
      int n=snprintf(body,sizeof(body),"D,3,%08lX,%lu,%08lX,%lu,%lu,%u,%ld,1,0",
        (unsigned long)nonce,(unsigned long)request,(unsigned long)bootId,(unsigned long)sequence,
        (unsigned long)stamp,(unsigned)symbol,(long)movement);
      if(n<=0 || (size_t)n>=sizeof(body)){++txErrors;return;}
      snprintf(asciiOutput,sizeof(asciiOutput),"%s*%04X\n",body,crc16((const uint8_t*)body,n));
    }
    cachedRequest=request;haveCache=true;lastValidMs=millis();++acceptedRequests;
  }
  if(binaryMode)writeWire(binaryOutput,sizeof(binaryOutput));
  else writeWire((const uint8_t*)asciiOutput,strlen(asciiOutput));
}
static void handleText(char *line) {
  if(strcmp(line,"INFO")==0) {
    Serial.println("# PulseBridge firmware 7.1.0 protocol 3 | SYNTHETIC | boot 115200 | H handshake required");return;
  }
  if(strcmp(line,"STATS")==0) {
    char body[176];
    snprintf(body,sizeof(body),"S,3,%08lX,%lu,%lu,%lu,%lu,%lu,%lu,%lu",
      (unsigned long)bootId,(unsigned long)crcErrors,(unsigned long)framingErrors,
      (unsigned long)rejectedRequests,(unsigned long)duplicateRequests,(unsigned long)protocolResets,
      (unsigned long)acceptedRequests,(unsigned long)txErrors);textReply(body);return;
  }
  char *star=strchr(line,'*');uint32_t received;
  if(!star || strlen(star+1)!=4 || !number(star+1,received,16)){++framingErrors;return;}
  if(received!=crc16((const uint8_t*)line,star-line)){++crcErrors;return;}
  *star='\0';char *fields[6];size_t count=1;fields[0]=line;
  for(char *p=line;*p;++p)if(*p==','){*p='\0';if(count==6){++framingErrors;return;}fields[count++]=p+1;}
  uint32_t nonce,value;
  if(count<4 || strcmp(fields[1],"3") || strlen(fields[2])!=8 || !number(fields[2],nonce,16)) {
    ++framingErrors;return;
  }
  if(strcmp(fields[0],"P")==0 && count==4 && number(fields[3],value,10)) {emitSignal(nonce,value);return;}
  uint32_t seed;
  if(strcmp(fields[0],"H") || count!=6 || !number(fields[4],value,10) || !number(fields[5],seed,10) ||
     !((strcmp(fields[3],"A")==0 && value==BASE_BAUD) ||
       (strcmp(fields[3],"B")==0 && (value==460800 || value==921600)))) {++rejectedRequests;return;}
  // Existing active sessions cannot be replaced/replayed without link idle reset.
  if(sessionActive){++rejectedRequests;return;}
  char body[96];
  snprintf(body,sizeof(body),"A,3,%08lX,%s,%lu,%08lX,%u",(unsigned long)nonce,fields[3],
           (unsigned long)value,(unsigned long)bootId,(unsigned)PB_BOARD_PROFILE);
  textReply(body);Serial.flush();
  binaryMode=strcmp(fields[3],"B")==0;
  if(binaryMode){delay(30);setBaud(value);} // Negotiation only.
  activeNonce=nonce;sessionActive=true;haveCache=false;resetParser();lastValidMs=millis();
  if(seed){rngState=seed;sequence=0;memset(symbolCounts,0,sizeof(symbolCounts));}
}
static void consume(uint8_t byte) {
  if(binaryMode) {
    binaryInput[(ringHead+ringLength)%REQUEST_BYTES]=byte;++ringLength;
    while(ringLength>=2 && (binaryInput[ringHead]!='P' || binaryInput[(ringHead+1)%REQUEST_BYTES]!='B')) {
      ringHead=(ringHead+1)%REQUEST_BYTES;--ringLength;++framingErrors;
    }
    if(ringLength<REQUEST_BYTES)return;
    uint8_t packet[REQUEST_BYTES];for(size_t i=0;i<REQUEST_BYTES;++i)packet[i]=binaryInput[(ringHead+i)%REQUEST_BYTES];
    uint16_t received=(uint16_t)packet[12]|((uint16_t)packet[13]<<8);
    if(received!=crc16(packet,12)){++crcErrors;ringHead=(ringHead+1)%REQUEST_BYTES;--ringLength;return;}
    ringHead=ringLength=0;
    if(packet[2]!=PROTOCOL_VERSION || packet[3]!=1){++framingErrors;return;}
    emitSignal(get32(packet+4),get32(packet+8));return;
  }
  if(byte=='\r')return;
  if(byte=='\n') {
    if(!discardLine && textLength){textInput[textLength]='\0';handleText(textInput);}
    textLength=0;discardLine=false;
  } else if(!discardLine) {
    if(byte<32 || byte>126 || textLength>=sizeof(textInput)-1){discardLine=true;++framingErrors;}
    else textInput[textLength++]=(char)byte;
  }
}
void setup() {
  Serial.setRxBufferSize(512); // Setup allocation only, no packet-path heap use.
  Serial.begin(BASE_BAUD);
#if PB_NATIVE_CDC
  Serial.setTxTimeoutMs(50);
#else
  Serial.setDebugOutput(false);
  uart_set_rx_full_threshold(UART_NUM_0,14);uart_set_rx_timeout(UART_NUM_0,1);
#endif
  bootId=esp_random();rngState=esp_random()^bootId;if(!rngState)rngState=0xA53C91E7;
}
void loop() {
  if(sessionActive && (uint32_t)(millis()-lastValidMs)>=LINK_IDLE_MS)resetLink();
  uint8_t bytes[64];int count=0;
#if PB_NATIVE_CDC
  int available=Serial.available();
  if(available>0)count=(int)Serial.read(bytes,(size_t)available>sizeof(bytes)?sizeof(bytes):(size_t)available);
  else {delay(1);return;} // USB tasks/watchdog remain schedulable; measured on target later.
#else
  // Wait for ONE byte; then drain only already-buffered bytes, bounded to 64.
  count=uart_read_bytes(UART_NUM_0,bytes,1,pdMS_TO_TICKS(20));if(count<=0)return;
  size_t available=0;uart_get_buffered_data_len(UART_NUM_0,&available);
  if(available){if(available>sizeof(bytes)-1)available=sizeof(bytes)-1;
    int extra=uart_read_bytes(UART_NUM_0,bytes+1,available,0);if(extra>0)count+=extra;}
#endif
  for(int i=0;i<count;++i)consume(bytes[i]);
  static uint32_t lastYield=0;
  if((uint32_t)(millis()-lastYield)>=10){delay(1);lastYield=millis();} // Bounded fairness even under noise flood.
}
