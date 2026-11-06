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

**Stav:** Overené na produkčnom notebooku Linux Mint pre kameru Arenti C3 (Hybe). Zmeny filtra `delogo` a pevného harmonogramu sú od synchronizácie 5. 11. 2026 zapracované aj v GitHub zdroji `arenti_publisher.py` a inštalátore `install_timer.py`. **Pozor:** presná binárna zhoda celej lokálnej produkčnej kópie a GitHub súboru ešte nebola overená. Existujúce produkčné systemd jednotky sa úpravou repozitára nemenia.

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

### Záverečné porovnanie GitHub ↔ produkcia (5. 11. 2026)

- Stiahnutý `arenti_publisher.py` z vetvy `main` a lokálny súbor `/home/mpca86/arenti-publisher/arenti_publisher.py` porovnané pomocou `cmp -s`: **PASS, identické bajty**.
- `python3 -m py_compile` pre stiahnuté `arenti_publisher.py`, `install_timer.py` a `test_timer_schedule.py`: **PASS**.
- `python3 -m unittest discover -s <dočasný adresár> -p 'test_timer_schedule.py' -v`: **8/8 PASS** (0,002 s); testy zahŕňajú default Hybe, offsety, hodinový interval, legacy režim a neplatné parametre.
- Diagnostika len čítala súbory a spúšťala testy v dočasnom priečinku; **produkčný skript a systemd jednotky zostali bez zmeny**.
- Zhodu `install_timer.py` s lokálnou (ak existuje) kópiou táto kontrola netestovala; unit testy takisto **nenahrádzajú čistú inštaláciu** na ďalšom počítači.

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
4. **GitHub implementácia a inštalátor zosúladené.** Produkčný `arenti_publisher.py` a `main` sú bitovo identické; 8/8 testov časovača a kontrola syntaxe prešli na produkčnom Linux Mint (5. 11. 2026). Pred vydaním zostáva overiť nový inštalačný postup v čistom prostredí a rozhodnúť o verziovanom vydaní.

## Prevencia uspávania a RTC wakeup – 6. 11. 2026

**Incident:** Notebook IdeaPad prešiel 6. 11. 2026 o 04:01:50 CET do `suspend` (`deep`), čím sa zastavili SSH/sieť a publikovanie snímok. O 13:24 nasledovala aktivita po prebudení, po reštarte 13:25 sa publikovanie obnovilo. Bezprostredne pred suspendom je v logoch `ACPI BIOS Error` (`TPWR`, `AE_NOT_FOUND`), ale **nebola jednoznačne potvrdená príčina** spánku (napr. zatvorené veko, prechod na batériu alebo udalosť firmvéru). Neoznačovať ACPI hlásenie za dokázanú príčinu.

### Ochrana pred uspávaním pri zatvorení veka

Používateľ `mpca86` nastavil v Cinnamon power nastaveniach `lid-close-ac-action` a `lid-close-battery-action` na `nothing`. Automatický suspend pri nečinnosti má AC aj batéria vypnutý (`sleep-inactive-*-timeout=0`); vypnutie displeja po 1800 s ostáva. Ochrana kritickej batérie zostala bez zmeny.

Záložná konfigurácia systemd-logind:

```text
/etc/systemd/logind.conf.d/90-arenti-lid.conf
```

```ini
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

Načítané signalizáciou `SIGHUP` pre `systemd-logind`; log potvrdil `Config file reloaded`, služba zostala `active`. Počas diagnostiky bol aktívny inhibitor Cinnamon `csd-power` pre `handle-lid-switch`. **Skutočný test so zatvoreným vekom zatiaľ neprebehol**, pretože správca nebol fyzicky pri notebooku.

### Systémový RTC wakeup timer (záložná poistka)

Overená diagnostika: `/dev/rtc0`, `/sys/class/rtc/rtc0/wakealarm`, `/sys/class/rtc/rtc0/device/power/wakeup=enabled`, `/sys/power/mem_sleep=s2idle [deep]`, `rtcwake -m show` hlásil pôvodne `alarm: off`. Systemd verzia `249`.

Nové systémové jednotky (na rozdiel od user timeru Publishera):

```text
/etc/systemd/system/arenti-rtc-wakeup.service
/etc/systemd/system/arenti-rtc-wakeup.timer
```

Service má `Type=oneshot` a `ExecStart=/usr/bin/logger -t arenti-rtc-wakeup RTC_WAKE_TIMER_TICK`.

```ini
[Unit]
Description=Arenti RTC wakeup every 10 minutes

[Timer]
OnCalendar=*-*-* *:00/10:00
WakeSystem=true
AccuracySec=1s
RandomizedDelaySec=0
Unit=arenti-rtc-wakeup.service

[Install]
WantedBy=timers.target
```

Aktivácia `sudo systemctl daemon-reload && sudo systemctl enable --now arenti-rtc-wakeup.timer`. Overené `active`, `enabled`, `WakeSystem=yes`.

**Reálne testy 6. 11. 2026 (PASS pri zapnutom systéme):** `RTC_WAKE_TIMER_TICK` v systémovom journale presne 14:20:00 a 14:30:00 CET. `arenti-rtc-wakeup.service`: `Result=success`, `ExecMainStatus=0`. Súbežne úspešne publikoval Arenti Publisher JPEG/FTPS o 14:14, 14:19, 14:24 a 14:29 (trvania 11,6 / 11,5 / 16,5 / 11,3 s). V týchto behoch sa nový RTC timer neprejavil ako prekážka.

**Limit:** Tieto heartbeat testy dokladajú pravidelné vykonanie timeru, **nie fyzické prebudenie zo suspendu**. Podpora RTC wake je len predpoklad; funkciu treba fyzicky overiť kontrolovaným testom `deep suspend → RTC wake` s lokálne prítomnou osobou. Pri strate napájania, úplnom vypnutí, závade firmware či zlyhaní RTC alarmu nie je automatické obnovenie garantované. RTC timer nenahrádza externý dohľad.

### Diagnostika / rollback ochrany napájania

```bash
gsettings get org.cinnamon.settings-daemon.plugins.power lid-close-ac-action
gsettings get org.cinnamon.settings-daemon.plugins.power lid-close-battery-action
systemd-analyze cat-config systemd/logind.conf | grep '^HandleLidSwitch'
systemctl list-timers --all --no-pager arenti-rtc-wakeup.timer
systemctl show arenti-rtc-wakeup.timer -p WakeSystem
journalctl -t arenti-rtc-wakeup --since '60 minutes ago' -o short-iso --no-pager
journalctl --user -u arenti-publisher.service --since '60 minutes ago' --no-pager
```

Bezpečné vypnutie záložného RTC timeru (bez zmeny Publishera):

```bash
sudo systemctl disable --now arenti-rtc-wakeup.timer
```

Návrat k pôvodnému správaniu veka len pri výslovnom rozhodnutí správcu: obnoviť pôvodné Cinnamon hodnoty (pred zmenou `lid-close-ac-action='nothing'`, `lid-close-battery-action='suspend'`), odstrániť vyššie uvedený vlastný `90-arenti-lid.conf` po kontrole jeho obsahu a znovu načítať konfiguráciu `systemd-logind` signálom HUP. **Neskrývať pri tom fakt, že návrat k `suspend` môže obnoviť riziko nočného výpadku.**

### Otvorené body po incidente

1. Bez rizika vzdialeného odpojenia vykonať lokálne asistovaný test prebudenia z režimu `deep` a zatvoreného veka.
2. Nastaviť externý monitoring dostupnosti notebooku/aktuálnosti `latest.jpg` (napr. Uptime Kuma), aby bol výpadok rozpoznaný včas.
3. Pri opakovanom uspávaní vyšetriť ACPI/BIOS udalosti a zdroj suspend požiadavky; zatiaľ nie je preukázané, čo suspend o 04:01 iniciovalo.

## M1 – externý monitoring aktuálnosti snímky (6. 11. 2026)

**Stav: M1 produkčný test PASS; M2 monitor Uptime Kuma aktívny (UP). Test notifikačného kanála a kontrolovaný DOWN → RECOVERY ešte otvorené.**

- Implementácia: `/hybe/public/camera/health.php` na HostCreators, vedľa `latest.jpg`.
- Verejná URL: `https://hybe.lovcimrazov.sk/camera/health.php`.
- Bez DB, cronu alebo prístupu k notebooku. Skript kontroluje lokálny `latest.jpg`, jeho `filemtime`, minimálnu veľkosť **20 000 B**, typ JPEG, koncové bajty JPEG a rozmery aspoň **1280 × 720**.
- Limit veku **720 sekúnd / 12 minút** pri typickom 5-minútovom nahrávaní.
- Pri platnom aktuálnom súbore HTTP **200** a `"status":"ok"`; pri chýbajúcom, poškodenom, nečitateľnom alebo zastaranom JPEG HTTP **503** a príslušný stav (`missing`, `invalid_image`, `unreadable`, `stale`, prípadne `error`/`clock_skew`).
- JSON obsahuje `checked_at`, `last_modified_at`, `age_seconds`, `max_age_seconds`, `image_bytes`, `image_width`, `image_height`. Časy sú v `Europe/Bratislava`.
- Cache zakázaná (`Cache-Control: no-store, no-cache...`). Endpoint nevracia prihlasovacie údaje ani interné absolútne serverové cesty.
- Dôležité: `last_modified_at` je súborový čas publikovania na HostCreators, **nie presný okamih `captured_at`**. Samotné HTTP 200 pre `latest.jpg` nie je dostatočná kontrola aktuálnosti.

**Overenie na produkcii (6. 11. 2026):**

- Prehliadač: `service=hybe-camera`, `status=ok`, `checked_at=2026-11-06T19:25:28+01:00`, `last_modified_at=2026-11-06T19:24:26+01:00`, `age_seconds=62`, `image_bytes=73429`, `2560 × 1440`.
- PowerShell `curl.exe -i https://hybe.lovcimrazov.sk/camera/health.php`: **HTTP/1.1 200 OK**, `Content-Type: application/json`; `checked_at=19:25:57`, `age_seconds=91`, rovnaký `last_modified_at`, správne no-cache hlavičky.
- Lokálne testy endpointu pred nasadením: platná/stará/poškodená/chýbajúca snímka (4/4 PASS podľa testov implementácie). **Produkčný test HTTP 503 simuláciou výpadku ešte neprebehol**.

**M2 – Uptime Kuma (6. 11. 2026):** Na Synology vytvorený monitor **#41 – HYBE – Arenti C3 – Aktualnost snimky** (typ `HTTP(s)`, `GET`, URL vyššie, interval 60 s, 2 opakovania, interval opakovania 30 s, timeout 10 s, akceptované kódy 200–299). Screenshot detailu potvrdzuje **Dostupné / UP**, `200 – OK`, aktuálnu odozvu 111 ms a 100 % dostupnosť od vytvorenia. Pri vytvorení bolo Signal oznámenie zapnuté a e-mailové vypnuté. Dňa 6. 11. bolo Signal REST API na Synology opravené a skúšobné odoslanie prešlo (HTTP 201 na `/v2/send`, používateľ potvrdil úspech). Stav UP a úspešný test oznámenia **zatiaľ nepreukazujú** správny prechod celého monitoru pri HTTP 503 (DOWN → RECOVERY).

**Nasledujúci test:** vytvoriť oddelený testovací endpoint/monitor a otestovať prechod DOWN → RECOVERY a príslušné Signal upozornenia bez zásahu do produkčného `latest.jpg`, produkčného `health.php` alebo Publishera. Testovacie upozornenia jednoznačne označiť.

### Obnova Signal notifikácií na Synology – 6. 11. 2026

Signal REST API poskytuje samostatný Docker Compose projekt na Synology DS220+, ktorý slúži ako notifikačný kanál Uptime Kuma.

- Projekt: `signal-api`, Compose služba `signal-cli-rest-api`, konfigurácia `/volume1/docker/signal-api/compose.yaml`.
- Dátový bind mount: `/volume1/docker/signal-api/signal-api-config` → `/home/.local/share/signal-cli`; údaje Signal účtu a kľúče nezverejňovať.
- Docker image: `bbernhard/signal-cli-rest-api:latest`; port `9922:8080`.
- Incident: existujúci kontajner mal starý `Entrypoint=["/entrypoint.sh"]`, zatiaľ čo používaný image mal `Entrypoint=["/init"]`. Projektový `compose.yaml` vlastný `entrypoint` neobsahoval. Prvé viditeľné neúspešné spustenie po predchádzajúcej prevádzke nastalo 31. 10. 2026.
- Pred opravou bola vytvorená záloha `/volume1/docker/signal-api/backup-20261106-201226` obsahujúca Compose a Signal konfiguráciu.
- Oprava: `docker compose -p signal-api -f /volume1/docker/signal-api/compose.yaml up -d --no-deps --force-recreate --pull never signal-cli-rest-api`; bez výmeny image a bez vymazania bind mountu.
- Následné testy: `Status=running`, `Health=healthy`, `Entrypoint=["/init"]`, `GET /v1/about → HTTP 200`, `GET /v1/accounts → 1 registrovaný účet`, `POST /v2/send → HTTP 201`; používateľ potvrdil úspešný skúšobný test.
- Logy obsahujú neblokujúce upozornenie na `/run` mount, no služby Signal API a JSON-RPC úspešne štartujú.
- **Zostáva:** izolovaný test prechodu Uptime Kuma monitoru DOWN → RECOVERY a doručenia oboch upozornení. Starý image `<none>` zatiaľ nemažme, kým nebude stabilita dlhšie overená.

### M3 – izolovaný test Uptime Kuma DOWN → RECOVERY (6. 11. 2026)

**Stav: PASS pre HTTP monitorovanie (200 → 503 → 200).** `health-test.php` bol nasadený na HostCreators a vytvorený testovací Uptime Kuma monitor **#42 – TEST – HYBE – DOWN RECOVERY**. Používateľ následne výslovne potvrdil, že **obe Signal oznámenia DOWN aj RECOVERY boli doručené**. Celý integračný test HTTP → Kuma → Signal je PASS.

- Umiestnenie po nasadení: `/hybe/public/camera/health-test.php` (samostatný endpoint vedľa produkčného `health.php`).
- **Normálne HTTP 200** (`status=ok`); po vytvorení `/hybe/public/camera/hybe-monitor-test-down.flag` vracia **HTTP 503** (`status=down`); po odstránení flagu znovu **HTTP 200**. Stav nemožno prepínať cez GET/POST URL a skript sa vôbec nedotýka `latest.jpg`.
- JSON vracia `service=hybe-camera-monitor-test`, `test_only=true`, `checked_at` a `reason`. Cache je zakázaná.
- Lokálne testy PHP syntaxe a simulovaného webservera **PASS: HTTP 200 → 503 → 200**.
- **Produkčný test Uptime Kuma #42:** UP o **20:36:58** (`200 – OK`) → DOWN o **20:39:58** (`Request failed with status code 503`) → UP/RECOVERY o **20:41:58** (`200 – OK`). Screenshot monitora potvrdzuje správne prepnutie stavov, finálny stav **Dostupné** a poslednú odozvu 89 ms.
- Test vykonaný cez samostatný endpoint, bez nutnosti upraviť produkčný `health.php`, `latest.jpg`, Publisher alebo monitor #41. Doručenie oboch notifikácií Signal následne používateľ potvrdil (vlastné skúsenosti, nie zo screenshotu).
- **Upratovanie:** po úspešnom teste zrušiť dočasný monitor a testovacie súbory, ak už nebudú potrebné; produkčný monitor #41 ponechať.

**Záver M2/testu:** monitor #42 má overené UP → DOWN → RECOVERY a obe Signal notifikácie; monitor #41 zostáva produkčný. Odstránenie testovacích artefaktov zatiaľ nebolo potvrdené.

### M3 – Uptime Kuma Push heartbeat Publishera (návrh implementácie 6. 11. 2026)

**Stav:** zmena implementovaná v samostatnej vetve `feat/kuma-push-heartbeat-20261106` (draft PR #2); **nie je nasadená na produkčný Linux Mint**. Spojenie IdeaPad → Synology cez ZeroTier bolo potvrdené 6. 11. 2026, samotný Push token ani nový kód ešte neboli otestované na produkcii.

- Nový modul `arenti_heartbeat.py` odosiela voliteľný HTTP(s) GET na `/api/push/<token>` až po úspešnom `ftp_upload()` (potvrdený FTP rename). Volanie je preskočené v režime `--dry-run`.
- Voliteľné nastavenia `[monitoring]` v lokálnom `arenti_config.ini` (práva 0600): `enabled`, `push_url`, `allow_private_http`, `timeout_seconds`. V repozitári iba neaktívny vzor s prázdnou URL; **skutočný token nezapisovať do GitHubu ani HELP.md**.
- Predvolený stav: vypnuté, aby ostatné inštalácie fungovali bez zmeny. HTTPS alebo explicitne povolené HTTP len na privátnu IP (napr. cez ZeroTier), bez presmerovaní; logy nesmú obsahovať URL ani token. Pridané `host_header` pre Synology nginx virtual-host (napr. `monitoring:3001`) pri súkromnom HTTP; pripojenie smeruje na privátnu IP a prostredie HTTP proxy sa ignoruje.
- Push dostáva `status=up`, `msg=FTPS upload OK`, `ping=<trvanie cyklu v ms>`. Ak FTP/RTSP zlyhá alebo systemd nevykoná Publisher, heartbeat nepríde. Chyba spojenia s Kumou **nezmení úspech FTPS cyklu na zlyhanie** (iba varovanie typu `HEARTBEAT FAIL`).
- Pripravených 8 izolovaných unit testov modulu; lokálne prešli. **Produkčný end-to-end test Push ešte neprebehol.**
- Navrhovaný nový Push monitor v Uptime Kuma: `HYBE – Arenti C3 – Publisher heartbeat`, očakávanie **420 s**, **1 opakovanie** s odstupom **60 s**, Signal DOWN/RECOVERY. Toto je samostatný monitor od HTTP checku produkčnej snímky #41.
- **Overená sieť 6. 11. 2026:** IdeaPad ZeroTier `192.168.196.12/24`; `192.168.196.150:3001` aj `192.168.2.150:3001` cez IP bez Host vracajú nginx `404`. Prístup pomocou `--resolve monitoring:3001:<IP>` a URL `http://monitoring:3001/api/entry-page` cez obe IP vrátil **HTTP 200**, JSON `{"type":"entryPage","entryPage":"dashboard"}`. Preto Push musí odosielať `Host: monitoring:3001` aj pri spojení na privátnu IP `192.168.196.150`. Konkrétny Push token nikdy neukladať do logu/repozitára.
- **Pred nasadením:** Push monitor už používateľ vytvoril v Synology (420 s, retries 1, retry delay 60 s; Signal dočasne vypnutý), treba potvrdiť smerovanie pomocou explicitného `Host` na IdeaPade, bezpečne otestovať Push token bez jeho zobrazenia v termináli alebo chate. Potom prevziať schválený kód na Mint, vytvoriť zálohu produkčných súborov, `chmod 600` config, test jedného cyklu, výsledok `HEARTBEAT OK`; kontrola `UPLOAD OK` a `CYKLUS OK`.
- **Rollback:** `enabled=no` alebo odstrániť sekciu `[monitoring]` a vrátiť predchádzajúcu verziu skriptu z vytvorenej zálohy. Systemd timer ostáva nezmenený.

## Známe obmedzenia

- Závisí od dostupnosti notebooku, siete, kamery a hostingu.
- Nezabezpečuje automatický reboot ani ochranu pred vybitím batérie.
- Ak vypadne pripojenie v okamihu FTPS rename, na serveri môže zostať dočasný súbor.
- Neexistuje zabalený prenosný Make blueprint; konfiguruj podľa dokumentácie.
- Testovanie v tomto GitHub-ready balíčku je statická kontrola a miestne testy; reálna kompatibilita s iným modelom/firmvérom nie je garantovaná.

## Ďalšie kroky

Voliteľne: integračné testy s mock ONVIF, retry FTPS 530 s limitmi, metriky času staroby JPEG, watchdog na webovej strane, rozšírenie dokumentácie pre ďalšie kamery.
