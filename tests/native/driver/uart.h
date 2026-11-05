#pragma once
#include "Arduino.h"
enum {UART_NUM_0=0, UART_NUM_2=2};
inline TestSerial &port(int n){return n==2?Serial2:Serial;}
inline int uart_set_rx_full_threshold(int,int){return 0;}
inline int uart_set_rx_timeout(int,int){return 0;}
inline int uart_flush_input(int u){port(u).input.clear();return 0;}
inline int uart_get_buffered_data_len(int u,size_t *n){*n=port(u).input.size();return 0;}
inline int uart_read_bytes(int u,uint8_t *p,size_t n,unsigned){
 size_t i=0;while(i<n && !port(u).input.empty())p[i++]=(uint8_t)port(u).read();return (int)i;
}
