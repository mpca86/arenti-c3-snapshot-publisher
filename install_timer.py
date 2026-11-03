#!/usr/bin/env python3
"""Install a user-level systemd timer for snapshot publishing."""
import argparse
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--minutes', type=int, default=5)
    args = p.parse_args()
    if not 1 <= args.minutes <= 1440:
        p.error('--minutes musí byť 1 až 1440')
    units = Path.home() / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    svc = units / 'arenti-publisher.service'
    timer = units / 'arenti-publisher.timer'
    # Absolute paths are passed without shell expansion.
    svc.write_text('[Unit]\nDescription=Arenti C3 JPEG publisher\n\n[Service]\nType=oneshot\n'
                   f'WorkingDirectory={BASE}\nExecStart={sys.executable} {BASE / "arenti_publisher.py"}\n'
                   'TimeoutStartSec=120\n', encoding='utf-8')
    timer.write_text('[Unit]\nDescription=Arenti C3 periodic snapshot\n\n[Timer]\nOnBootSec=1min\n'
                     f'OnUnitInactiveSec={args.minutes}min\nAccuracySec=15s\nUnit=arenti-publisher.service\n\n[Install]\nWantedBy=timers.target\n', encoding='utf-8')
    for cmd in (['systemctl', '--user', 'daemon-reload'], ['systemctl', '--user', 'enable', '--now', 'arenti-publisher.timer']):
        subprocess.run(cmd, check=True)
    print(f'Timer zapnutý: každých približne {args.minutes} min po dokončení predošlého cyklu')
    print('Stav: systemctl --user list-timers arenti-publisher.timer')
    print('Pozn.: ak má bežať aj po odhlásení, vyžaduje user lingering (sudo loginctl enable-linger "$USER").')

if __name__ == '__main__':
    main()
