# 📷 Arenti C3 Snapshot Publisher

**Čo dokáže kamera približne za 20 €?** Na Linuxe sa dá použiť ako automatická webkamera: každých päť minút vytvorí aktuálnu fotografiu a bezpečne ju zverejní na webovom serveri. Tento projekt vznikol pri kamere **Arenti C3** pre meteorologickú stránku **Meteo Hybe**.

**Ukážka z reálnej prevádzky:** [hybe.lovcimrazov.sk/camera/latest.jpg](https://hybe.lovcimrazov.sk/camera/latest.jpg) (živá fotografia, môže byť dočasne nedostupná).

> Ide o komunitný projekt, nie oficiálny softvér značky Arenti. Overené na jednom konkrétnom zariadení Arenti C3 a Linux Mint v novembri 2026; nie je zaručená kompatibilita s každou verziou firmvéru.

## Funkcie

- **ONVIF**: automatické získanie dostupného RTSP streamu bez ručného vypisovania jeho adresy.
- **FFmpeg**: zachytenie jediného JPEG záberu z RTSP (warm-up odstraňuje počiatočné sivé snímky).
- **3 pokusy**: ak prvá fotografia nevyhovuje, zopakuje snímkovanie s dlhším rozbehom.
- **Kontrola kvality**: JPEG formát, veľkosť, rozlíšenie a minimálna variabilita jasu.
- **FTPS upload**: šifrované nahranie cez `curl`, následne premenovanie do `latest.jpg`. Výpadok alebo nekvalitná fotografia neprepíše poslednú platnú snímku.
- **systemd user timer**: pravidelná aktualizácia približne 5 minút po dokončení cyklu.
- **Logovanie**: systemd journal a rotujúci log súbor.
- **Voliteľný externý dohľad cez Make.com**: samostatná kontrola HTTP `Last-Modified` a e-mail pri výpadku/obnovení (konfigurácia v `docs/MAKE_MONITOR.md`).

## Ako to funguje

```text
Arenti C3 --ONVIF--> RTSP URI --FFmpeg--> JPEG --kontrola kvality--> FTPS --> web/latest.jpg
     Linux Mint notebook  --systemd timer (~5 min)--> Publisher
                                                  |
                                                  v
                                    Make.com HEAD Last-Modified
                                         >15 min -> upozornenie
```

## Rýchla inštalácia (Debian / Ubuntu / Linux Mint)

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg curl

# V rozbalenom priečinku projektu:
cd arenti-c3-snapshot-publisher
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp arenti_config.example.ini arenti_config.ini
chmod 600 arenti_config.ini
nano arenti_config.ini
```

Nastav `camera.host`, ONVIF prihlasovacie údaje a FTPS údaje. ONVIF musí byť zapnutý v kamere; sieť notebooku musí mať prístup ku kamere a FTP serveru. Do verejného repozitára nikdy nepridávaj `arenti_config.ini`.

### Test bez uploadu

```bash
.venv/bin/python arenti_publisher.py --dry-run
```

### Ostrý upload

```bash
.venv/bin/python arenti_publisher.py
```

Očakávané udalosti v logu: `KVALITA OK`, `UPLOAD OK`, `CYKLUS OK`. Fotografia bude na FTPS serveri v adresári `[ftp] remote_dir` pod názvom `[ftp] filename`. **FTP adresár a webový document root nie sú automaticky totožné** – over verejnú URL.

### Automatické spustenie

```bash
.venv/bin/python install_timer.py --minutes 5
systemctl --user list-timers --all arenti-publisher.timer
journalctl --user -u arenti-publisher.service -n 40 --no-pager
```

Installer používa interpreter, ktorým ho spustíš; spusti ho preto cez `.venv/bin/python`. Služba sa končí po jednom cykle a časovač naplánuje ďalší. Pre fungovanie po odhlásení z Linuxu voliteľne povoľ `sudo loginctl enable-linger "$USER"`. Notebook stále nesmie zaspať; pri zatvorení veka a pri strate napájania platia nastavenia distribúcie.

### Logy a diagnostika

```bash
journalctl --user -u arenti-publisher.service -f
systemctl --user status arenti-publisher.timer --no-pager
```

Súborový log je v `[storage] directory/logs/publisher.log` a rotuje pri približne 2 MB so štyrmi zálohami. Pri chybe sa pozri na logy, ale nikdy nezverejňuj prihlasovacie údaje ani plnú RTSP URL.

## Technické poznámky

- ONVIF na porte 8000 a RTSP na porte 8554 boli overené na konkrétnej Arenti C3; iné firmvéry môžu používať iné porty.
- Ak FTPS v Pythone hlási `425` alebo TLS EOF, nahrávanie cez `curl` môže fungovať správne aj vtedy, keď `ftplib.FTP_TLS.storbinary` zlyhá.
- Ak FTPS server odmieta premenovanie `RNTO`, program štandardne starú fotografiu nemaže. Nezapínaj `allow_nonatomic_replace` bez pochopenia dôsledkov.
- Sivé snímky sa môžu objaviť napr. pri prepnutí nočného režimu. Ochrana kvality nemusí odhaliť všetky chyby a príliš prísny prah môže odmietnuť aj platnú nočnú fotografiu.
- Pred akýmkoľvek verejným použitím kamery zváž súkromie osôb, susedov a cudzích pozemkov v zábere.

## Dokumentácia

- [HELP.md](HELP.md) – architektúra, známe problémy, prevádzka a testy.
- [docs/MAKE_MONITOR.md](docs/MAKE_MONITOR.md) – nezávislý monitoring snímky.
- [docs/SECURITY.md](docs/SECURITY.md) – bezpečné publikovanie.

## Licencia

Pozri súbor [LICENSE](LICENSE) (MIT). Nezahŕňa ochranné známky výrobcov ani prípadné práva tretích strán k externým komponentom.
