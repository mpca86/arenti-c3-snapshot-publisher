# HELP – Arenti C3 Snapshot Publisher (handoff)

**Verzia aplikácie:** v0.8.2 (zdroj z funkčného patchu 2026-11-03).  **Distribučný balíček:** GitHub-ready 1.0.

## Účel a architektúra

ONVIF (media profiles, GetStreamUri) → FFmpeg RTSP (warm-up) → JPEG validácia (Pillow) → opakovanie max. 3× → lokálny latest.jpg → `curl` explicit FTPS → dočasný názov → FTPS rename na latest.jpg. Chyba kvality alebo FTP ponechá doterajšiu verejnú snímku.

## Súbory

- `arenti_publisher.py`: cyklus, kontrola kvality, FTPS odoslanie, logovanie, lock
- `arenti_onvif.py`: ONVIF WS-Security komunikácia
- `install_timer.py`: systemd user service/timer
- `migrate_config.py`: migrácia zo starej ONVIF konfigurácie (voliteľné)
- `arenti_config.example.ini`: bezpečný vzor; skutočný súbor `arenti_config.ini` je lokálny a ignorovaný Gitom
- `data/latest.jpg`, `data/logs/publisher.log`: runtime dáta (nezverejňovať)

## Prevádzka

`python3 arenti_publisher.py --dry-run` preverí JPEG bez FTPS. `python3 arenti_publisher.py` publikuje. `systemctl --user list-timers arenti-publisher.timer` ukáže plánované spustenia. `journalctl --user -u arenti-publisher.service -n 50 --no-pager` je diagnostika.

## Overené testy (3. 11. 2026)

- ONVIF GetProfiles/GetStreamUri: PASS; 2560×1440 a 640×360 profily.
- Sivá počiatočná snímka pri RTSP: vyriešené warm-up a kontrolou jasového rozptylu.
- FTPS server: TLS certifikát vyžadoval správny hostname; `curl` STOR fungoval.
- Python `ftplib.FTP_TLS` dátový prenos: niektoré prenosy zlyhali; produkčné nahratie cez `curl`, rename cez FTP_TLS.
- Public HTTPS `latest.jpg`: dostupné; fotografia sa aktualizovala.
- 3-pokusové zachytávanie: PASS v reálnych logoch.
- systemd timer: PASS, cykly automaticky nahrávali; linger zapnutý.
- Make HTTP HEAD + Last-Modified: PASS, simulácia výpadku/obnovenia prešla; stav sa ukladá do Data Store.

## Známe obmedzenia

- Závisí od dostupnosti notebooku, siete, kamery a hostingu.
- Nezabezpečuje automatický reboot ani ochranu pred vybitím batérie.
- Ak vypadne pripojenie v okamihu FTPS rename, na serveri môže zostať dočasný súbor.
- Neexistuje zabalený prenosný Make blueprint; konfiguruj podľa dokumentácie.
- Testovanie v tomto GitHub-ready balíčku je statická kontrola a miestne testy; reálna kompatibilita s iným modelom/firmvérom nie je garantovaná.

## Ďalšie kroky

Voliteľne: integračné testy s mock ONVIF, retry FTPS 530 s limitmi, metriky času staroby JPEG, watchdog na webovej strane, rozšírenie dokumentácie pre ďalšie kamery.
