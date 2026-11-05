#pragma once
// REQUIRED: set 1..5 using tools/configure_firmware.py or edit this value.
#ifndef PB_BOARD_PROFILE
#define PB_BOARD_PROFILE 0
#endif
// 0=mixed outliers (original), 1=quiet/zero movement, 2=positive trend, 3=alternating shocks.
#ifndef PB_SCENARIO
#define PB_SCENARIO 0
#endif
#if PB_SCENARIO < 0 || PB_SCENARIO > 3
#error "PB_SCENARIO must be 0..3"
#endif
