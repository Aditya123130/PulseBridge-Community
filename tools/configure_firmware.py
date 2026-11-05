#!/usr/bin/env python3
"""Write an explicit local firmware profile; does not compile or flash hardware."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--board-profile',type=int,choices=range(1,6),required=True)
p.add_argument('--scenario',choices=['mixed','quiet','trend','shocks'],default='mixed')
a=p.parse_args()
file=Path(__file__).resolve().parents[1]/'firmware/PulseBridgeESP32/board_config.h'
file.write_text('#pragma once\n#ifndef PB_BOARD_PROFILE\n#define PB_BOARD_PROFILE '+str(a.board_profile)+'\n#endif\n#ifndef PB_SCENARIO\n#define PB_SCENARIO '+str(['mixed','quiet','trend','shocks'].index(a.scenario))+'\n#endif\n#if PB_SCENARIO < 0 || PB_SCENARIO > 3\n#error "PB_SCENARIO must be 0..3"\n#endif\n')
print('Configured',file,'profile',a.board_profile,'scenario',a.scenario,'; select the matching Arduino board before compiling.')
