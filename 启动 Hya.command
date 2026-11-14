#!/bin/zsh
cd "${0:A:h}"
export PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/hya-pycache"
/usr/bin/python3 app.py
