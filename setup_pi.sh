#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if [[ ! -x .venv/bin/python ]]; then
  if ! python3 -m venv .venv; then
    echo 'Install venv support: sudo apt-get update && sudo apt-get install python3-venv'
    exit 1
  fi
fi
.venv/bin/python -m pip install -r requirements.txt
if ! id -nG | tr ' ' '\n' | grep -qx dialout; then
  sudo usermod -aG dialout "$(id -un)"
  echo 'Log out of SSH and log in again to activate dialout membership.'
fi
.venv/bin/python pi/app.py --list-ports
echo 'One firmware: firmware/PulseBridgeESP32/PulseBridgeESP32.ino. Read START_HERE.md.'
