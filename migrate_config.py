#!/usr/bin/env python3
"""Create publisher config from example, optionally importing only camera settings."""
import configparser
import os
from pathlib import Path
import sys

base = Path(__file__).resolve().parent
source = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
target = base / 'arenti_config.ini'
if target.exists():
    print(f'Existujúcu konfiguráciu neprepisujem: {target}')
    sys.exit(1)
cfg = configparser.ConfigParser(interpolation=None)
cfg.read(base / 'arenti_config.example.ini', encoding='utf-8')
if source:
    old = configparser.ConfigParser(interpolation=None)
    if not old.read(source, encoding='utf-8') or not old.has_section('camera'):
        print('Pôvodný konfiguračný súbor nemá sekciu [camera].')
        sys.exit(2)
    for key in ('host','port','username','password'):
        if old.has_option('camera',key):
            cfg['camera'][key] = old['camera'][key]
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd,'w',encoding='utf-8') as f:
    cfg.write(f)
print(f'Konfigurácia pripravená: {target}. Doplň FTP údaje cez nano; heslá sa nevypisujú.')
