#pragma once
#include <cstdint>
// Deterministic TEST fixture only. Actual firmware uses Espressif esp_random().
inline uint32_t esp_random() {static uint32_t n=0xCAFED000;return ++n;}
