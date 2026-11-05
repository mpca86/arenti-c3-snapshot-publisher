# HELP – Arenti C3 Snapshot Publisher (handoff)

**Verzia aplikácie:** v0.8.2 (zdroj z funkčného patchu 2026-11-03).  **Distribučný balíček:** GitHub-ready 1.0.

## Účel a architektúra

ONVIF (media profiles, GetStreamUri) → FFmpeg RTSP (warm-up; v nasadení od 5. 11. 2026 aj filter `delogo`) → JPEG validácia (Pillow) → opakovanie max. 3× → lokálny latest.jpg → `curl` explicit FTPS → dočasný názov → FTPS rename na latest.jpg. Chyba kvality alebo FTP ponechá doterajšiu verejnú snímku.

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

## Nasadenie a overenie 5. 11. 2026 – presný timer a odstránenie OSD času

**Stav:** Overené na produkčnom notebooku Linux Mint pre kameru Arenti C3 (Hybe). Tieto zmeny boli vykonané na lokálnom systéme. **Pozor:** táto aktualizácia súboru `HELP.md` sama osebe nemení `arenti_publisher.py`, `install_timer.py` ani systemd jednotky v repozitári GitHub; pred nasadením na ďalší počítač treba príslušné zmeny preniesť do zdrojového kódu/installeru.

### Skutočné umiestnenia v prevádzke

- Linux účet: `mpca86` (hostname `ideapad`).
- Produkčný skript: `/home/mpca86/arenti-publisher/arenti_publisher.py`.
- Pracovný adresár služby: `/home/mpca86/arenti-publisher/`.
- Jednotky: `/home/mpca86/.config/systemd/user/arenti-publisher.service` a `/home/mpca86/.config/systemd/user/arenti-publisher.timer`.
- Service: `Type=oneshot`, `ExecStart=/usr/bin/python3 /home/mpca86/arenti-publisher/arenti_publisher.py`, `TimeoutStartSec=120`.
- Verejná snímka: https://hybe.lovcimrazov.sk/camera/latest.jpg; FTPS remote path podľa logov: `/hybe/public/camera/latest.jpg` (bez zverejnenia prihlasovacích údajov).
- Odoberateľ: APP Počasí Meteo používa uvedenú URL a spája snímku s údajmi meteostanice. Publikovanie súhrnu v nasledujúcej minúte je prevádzkový predpoklad; presný okamih jeho HTTP načítania nebol nezávisle meraný.

### Timer – pevné 5-minútové hranice

Staršie nastavenie `OnBootSec=1min` + `OnUnitInactiveSec=5min` plánovalo ďalší beh až päť minút po skončení predošlého. Pri približne 46-sekundovom spracovaní vznikal pozorovaný interval okolo 6 minút; kamera a 10-minútové meteointervaly sa preto rozchádzali.

**Aktuálne overená produkčná konfigurácia:**

```ini
[Unit]
Description=Arenti C3 periodic snapshot

[Timer]
OnCalendar=*-*-* *:04/5:00
AccuracySec=1s
RandomizedDelaySec=0
Unit=arenti-publisher.service

[Install]
WantedBy=timers.target
```

Spustenia sú plánované v minútach **04, 09, 14, 19, 24, 29, 34, 39, 44, 49, 54, 59** lokálneho času zariadenia. Pri nominálnom 10-minútovom meteointervale (napr. 20:20) je posledné plánované snímanie o 20:19. Približne 10–11 sekúnd trvajúci úspešný cyklus teda stihne upload s rezervou. **Nespúšťať na hraniciach 00/05 bez osobitného overenia času, kedy APP naozaj preberá JPEG.**

Aktivácia bola potvrdená pomocou `systemd-analyze calendar`, `systemctl --user list-timers --all`, `systemctl --user is-active` a `is-enabled`. Timer bol `active` a `enabled`. Služba `oneshot` je po úspešnom dokončení prirodzene `inactive`; to nie je porucha.

### OSD dátum/čas – odstránenie v jednom FFmpeg procese

Kamera vkladá vlastnú časovú pečiatku do ľavého horného rohu obrazu a v jej nastavení sa nepodarilo nájsť možnosť vypnutia. Aby APP nepridávala vedľa svojho meteointervalu ešte druhý čas, používa sa pri získaní JPEG obrazový filter:

```text
delogo=x=22:y=22:w=665:h=75:show=0
```

- Overené na rozlíšení **2560 × 1440**. Iné rozlíšenie/profil vyžaduje nové súradnice.
- Filter sa vykonáva cez FFmpeg priamo vo funkcii `capture()`, ako parameter `-vf` vložený pred `-frames:v 1 -q:v ...`; **nejde o druhý FFmpeg beh**.
- Následne sa uplatňuje existujúca `quality_check()` s kontrolou JPEG, rozlíšenia, veľkosti a jasového rozptylu. Ak zachytenie alebo kvalita zlyhajú, existujúce retry mechanizmy ostávajú aktívne a nepublikuje sa neplatná snímka.
- Na nočnom zábere je výsledok bez textu vizuálne overený. `delogo` len odhaduje prekryté pixely, nezískava pôvodné dáta spod OSD. **Denný test na svetlej oblohe ešte ostáva otvorený** pre možné vyhladené obdĺžnikové artefakty.
- Keďže OSD na verejne publikovanom JPEG chýba, pri potrebe presného `captured_at` treba používať čas zachytenia v aplikačných logoch alebo v budúcnosti samostatné metadáta; čas APP nemusí predstavovať presný čas fotografie.

### Testy z produkcie (PASS)

**Pred pridaním filtra, po zmene timeru:**

| Štart | Platná JPEG / `KVALITA OK` | `UPLOAD OK` | `CYKLUS OK` |
| --- | --- | --- | --- |
| 20:04:00 | 20:04:09,696 | 20:04:11,254 | 10,5 s |
| 20:09:00 | 20:09:09,691 | 20:09:11,278 | 10,5 s |
| 20:14:00 | 20:14:09,670 | 20:14:11,487 | 10,7 s |
| 20:19:00 | 20:19:09,670 | 20:19:11,347 | 10,6 s |
| 20:24:00 | 20:24:09,771 | 20:24:11,317 | 10,6 s |

Všetkých päť behov: platná snímka na **prvý z troch povolených pokusov**, bez `ValueError`. Priemerné trvanie cyklu približne **10,58 s**. Staršie behy (napr. 18:28) mali opakovanie 3/3 a približne 46 s, preto musí plánovanie ponechať rezervu na zhoršené podmienky.

**Po integrácii filtra:**

- 21:34:09,651 `KVALITA OK`; 21:34:11,229 `UPLOAD OK`; `CYKLUS OK: 10.5 s`.
- 21:39:09,814 `KVALITA OK`; 21:39:11,525 `UPLOAD OK`; `CYKLUS OK: 10.8 s`.
- Verejný `latest.jpg` zobrazený **bez pôvodného dátumu a času**: vizuálne potvrdené používateľom.
- FTPS publikovanie cez `curl` + premenovanie dočasného súboru ostalo funkčné.
- Pridaný filter nespôsobil významné spomalenie v týchto dvoch behoch.

### Zálohy, diagnostika a rollback

**Lokálna záloha skriptu pred vložením filtra:**

```text
/home/mpca86/arenti-publisher/arenti_publisher.py.bak-delogo-20261105-213659
```

**Lokálna záloha pôvodného timeru pred prechodom na OnCalendar:**

```text
/home/mpca86/.config/systemd/user/arenti-publisher.timer.bak-20261105-200029
```

Bežné kontroly (bez potreby zasahovať do konfigurácie):

```bash
systemctl --user list-timers --all --no-pager | grep arenti-publisher
journalctl --user -u arenti-publisher.service -n 50 --no-pager
systemctl --user cat arenti-publisher.service arenti-publisher.timer
```

Ak treba **vrátiť len filter** (časovač ostáva na pevnom harmonograme), na Linux Mint po overení, že práve nebeží publikačný cyklus:

```bash
cp -p /home/mpca86/arenti-publisher/arenti_publisher.py.bak-delogo-20261105-213659 /home/mpca86/arenti-publisher/arenti_publisher.py
python3 -m py_compile /home/mpca86/arenti-publisher/arenti_publisher.py
```

Ďalší timer cyklus použije pôvodný skript. Pri prípadnom návrate timeru najprv vytvoriť zálohu aktuálneho súboru, obnoviť z vyššie uvedenej `.bak`, potom `systemctl --user daemon-reload && systemctl --user restart arenti-publisher.timer`. Po akomkoľvek rollbacku overiť nové `KVALITA OK`, `UPLOAD OK`, `CYKLUS OK` a aktuálnu verejnú snímku.

### Otvorené úlohy

1. Skontrolovať `delogo` aj na **dennej** snímke (obloha pri OSD).
2. Pri väčšom počte cyklov sledovať retry/čas na upload a rezervu do načítania APP.
3. Ak je potrebné presné párovanie obrazu a meteomeraní, doplniť bezpečný záznam `captured_at` / `uploaded_at` a overiť skutočný čas HTTP načítania obrázka aplikáciou.
4. Zosúladiť implementáciu a installer v GitHub repozitári s nasadenými lokálnymi zmenami, prípadne pripraviť verziované vydanie.

## Známe obmedzenia

- Závisí od dostupnosti notebooku, siete, kamery a hostingu.
- Nezabezpečuje automatický reboot ani ochranu pred vybitím batérie.
- Ak vypadne pripojenie v okamihu FTPS rename, na serveri môže zostať dočasný súbor.
- Neexistuje zabalený prenosný Make blueprint; konfiguruj podľa dokumentácie.
- Testovanie v tomto GitHub-ready balíčku je statická kontrola a miestne testy; reálna kompatibilita s iným modelom/firmvérom nie je garantovaná.

## Ďalšie kroky

Voliteľne: integračné testy s mock ONVIF, retry FTPS 530 s limitmi, metriky času staroby JPEG, watchdog na webovej strane, rozšírenie dokumentácie pre ďalšie kamery.
