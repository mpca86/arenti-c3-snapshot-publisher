#!/usr/bin/env python3
"""Install a user-level systemd timer for snapshot publishing."""
import argparse
from pathlib import Path
import subprocess
import sys

BASE = Path(__file__).resolve().parent


def timer_schedule(minutes, schedule='calendar', minute_offset=None):
    """Return systemd Timer directives; no changes to the running system."""
    if not 1 <= minutes <= 1440:
        raise ValueError('--minutes musí byť 1 až 1440')

    if schedule == 'interval':
        if minute_offset is not None:
            raise ValueError('--minute-offset sa používa iba s --schedule calendar')
        return (f'OnBootSec=1min\nOnUnitInactiveSec={minutes}min\n'
                'AccuracySec=15s\n')

    if schedule != 'calendar':
        raise ValueError('Neplatný --schedule')
    if minutes > 60 or 60 % minutes:
        raise ValueError('Kalendárny režim vyžaduje --minutes deliace 60 '
                         '(napr. 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60). '
                         'Inak použi --schedule interval.')

    # Hybe: five-minute captures at :04, :09, :14, :19, ...
    offset = (4 if minutes == 5 else 0) if minute_offset is None else minute_offset
    if not 0 <= offset < minutes:
        raise ValueError('--minute-offset musí byť od 0 do minutes - 1')

    if minutes == 60:
        expression = f'*-*-* *:{offset:02d}:00'
    else:
        expression = f'*-*-* *:{offset:02d}/{minutes}:00'
    return (f'OnCalendar={expression}\nAccuracySec=1s\n'
            'RandomizedDelaySec=0\n')


def main():
    p = argparse.ArgumentParser(description='Nastavenie systemd user timeru')
    p.add_argument('--minutes', type=int, default=5)
    p.add_argument('--schedule', choices=('calendar', 'interval'),
                   default='calendar',
                   help='calendar: pevné hranice hodín; interval: starý režim po ukončení behu')
    p.add_argument('--minute-offset', type=int, default=None,
                   help='posun kalendárnej schémy; pri 5 min predvolene 4 (:04, :09...)')
    args = p.parse_args()
    try:
        schedule_lines = timer_schedule(args.minutes, args.schedule,
                                        args.minute_offset)
    except ValueError as exc:
        p.error(str(exc))

    units = Path.home() / '.config/systemd/user'
    units.mkdir(parents=True, exist_ok=True)
    svc = units / 'arenti-publisher.service'
    timer = units / 'arenti-publisher.timer'
    # Absolute paths are passed without shell expansion.
    svc.write_text('[Unit]\nDescription=Arenti C3 JPEG publisher\n\n[Service]\nType=oneshot\n'
                   f'WorkingDirectory={BASE}\nExecStart={sys.executable} {BASE / "arenti_publisher.py"}\n'
                   'TimeoutStartSec=120\n', encoding='utf-8')
    timer.write_text('[Unit]\nDescription=Arenti C3 periodic snapshot\n\n[Timer]\n'
                     + schedule_lines
                     + 'Unit=arenti-publisher.service\n\n[Install]\n'
                       'WantedBy=timers.target\n', encoding='utf-8')

    for cmd in (['systemctl', '--user', 'daemon-reload'],
                ['systemctl', '--user', 'enable', '--now', 'arenti-publisher.timer'],
                ['systemctl', '--user', 'restart', 'arenti-publisher.timer']):
        subprocess.run(cmd, check=True)

    if args.schedule == 'calendar':
        print(f'Timer zapnutý: kalendárny cyklus každých {args.minutes} min')
        print('Plán: ' + schedule_lines.splitlines()[0])
    else:
        print(f'Timer zapnutý: každých približne {args.minutes} min '
              'po dokončení predošlého cyklu')
    print('Stav: systemctl --user list-timers arenti-publisher.timer')
    print('Pozn.: ak má bežať aj po odhlásení, vyžaduje user lingering '
          '(sudo loginctl enable-linger "$USER").')


if __name__ == '__main__':
    main()
