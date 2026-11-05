#!/usr/bin/env python3
"""Arenti C3 ONVIF -> RTSP -> validated JPEG -> FTP/FTPS website image."""
import argparse
import configparser
import ftplib
import io
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote, urlsplit, urlunsplit
from xml.sax.saxutils import escape

from PIL import Image, ImageStat, UnidentifiedImageError
from arenti_onvif import soap_request, children_named, first_text

BASE = Path(__file__).resolve().parent
LOG = logging.getLogger('arenti')


def settings(path):
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        raise ValueError(f'Konfigurácia neexistuje: {p}; skopíruj arenti_config.example.ini na arenti_config.ini')
    if os.name == 'posix' and (p.stat().st_mode & 0o077):
        raise ValueError(f'Konfigurácia nie je súkromná: chmod 600 {p}')
    c = configparser.ConfigParser(interpolation=None)
    c.read(p, encoding='utf-8')
    for section in ('camera', 'capture', 'ftp', 'storage'):
        if not c.has_section(section):
            raise ValueError(f'Chýba sekcia [{section}] v {p}')
    for section, options in {'camera': ('host', 'username', 'password'), 'ftp': ('host', 'username', 'password')}.items():
        for key in options:
            if not c[section].get(key, '').strip() or c[section][key].startswith('VYPLN_'):
                raise ValueError(f'Doplň [{section}] {key} v konfigurácii')
    return c


def configure_log(folder):
    folder.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler = RotatingFileHandler(folder / 'publisher.log', maxBytes=2_000_000, backupCount=4, encoding='utf-8')
    file_handler.setFormatter(fmt)
    stderr_handler = logging.StreamHandler(sys.stdout)
    stderr_handler.setFormatter(fmt)
    LOG.addHandler(file_handler)
    LOG.addHandler(stderr_handler)


def stream_url(c):
    cam = c['camera']
    host, port = cam['host'].strip(), cam.getint('port', 8000)
    url = f'http://{host}:{port}/onvif/media_service'
    profiles_xml = soap_request(url, '<trt:GetProfiles/>', cam['username'], cam['password'])
    if profiles_xml is None:
        raise RuntimeError('ONVIF GetProfiles zlyhalo')
    tokens = [p.attrib['token'] for p in children_named(profiles_xml, 'Profiles') if 'token' in p.attrib]
    index = c['capture'].getint('profile', 0)
    if not 0 <= index < len(tokens):
        raise ValueError(f'Neplatný index profilu {index}; dostupných: {len(tokens)}')
    body = ('<trt:GetStreamUri><trt:StreamSetup>'
            '<tt:Stream xmlns:tt="http://www.onvif.org/ver10/schema">RTP-Unicast</tt:Stream>'
            '<tt:Transport xmlns:tt="http://www.onvif.org/ver10/schema"><tt:Protocol>RTSP</tt:Protocol></tt:Transport>'
            '</trt:StreamSetup><trt:ProfileToken>' + escape(tokens[index]) + '</trt:ProfileToken></trt:GetStreamUri>')
    response = soap_request(url, body, cam['username'], cam['password'])
    if response is None:
        raise RuntimeError('ONVIF GetStreamUri zlyhalo')
    uri = first_text(response, 'Uri')
    u = urlsplit(uri)
    if u.scheme != 'rtsp' or u.hostname != host:
        raise ValueError('ONVIF vrátil neočakávanú RTSP adresu; odmietam ju otvoriť')
    if u.username is None:
        netloc = f'{quote(cam["username"], safe="")}:{quote(cam["password"], safe="")}@{host}:{u.port or 554}'
        uri = urlunsplit(('rtsp', netloc, u.path, u.query, ''))
    return uri


def capture(c, uri, output):
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('Chýba ffmpeg: sudo apt install ffmpeg')
    warmup = c['capture'].getint('warmup_seconds', 8)
    if not 1 <= warmup <= 60:
        raise ValueError('warmup_seconds musí byť 1 až 60')
    # -ss after -i means decode actual stream before the screenshot (fixes initial grey frames).
    cmd = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
           '-rtsp_transport', 'tcp', '-stimeout', '8000000', '-i', uri,
           '-ss', str(warmup), '-vf', 'delogo=x=22:y=22:w=665:h=75:show=0', '-frames:v', '1', '-q:v', str(c['capture'].getint('jpeg_quality', 2)), str(output)]
    for opt in ('-stimeout', '-timeout'):
        # FFmpeg builds disagree on timeout argument naming.
        cmd[cmd.index('-timeout') if '-timeout' in cmd else cmd.index('-stimeout')] = opt
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=warmup + 35)
        except subprocess.TimeoutExpired:
            raise RuntimeError('FFmpeg timeout')
        if proc.returncode == 0 and output.is_file():
            return
        if ('Unrecognized option' in proc.stderr or 'Option not found' in proc.stderr) and opt == '-stimeout':
            continue
        # Never log raw stderr; it could expose RTSP credentials.
        raise RuntimeError(f'FFmpeg zlyhal (exit={proc.returncode}); prever dostupnosť RTSP a ONVIF')
    raise RuntimeError('FFmpeg nepodporuje timeout parameter')


def quality_check(path, c):
    s = path.stat().st_size
    minimum = c['capture'].getint('min_bytes', 20000)
    if s < minimum:
        raise ValueError(f'Príliš malý JPG ({s} B < {minimum} B)')
    try:
        with Image.open(path) as im:
            if im.format != 'JPEG':
                raise ValueError('Výsledok nie je JPEG')
            im.verify()
        with Image.open(path) as im:
            width, height = im.size
            if width < c['capture'].getint('min_width', 1280) or height < c['capture'].getint('min_height', 720):
                raise ValueError(f'Nízke rozlíšenie {width}x{height}')
            grey = im.convert('L')
            grey.thumbnail((256, 256))
            deviation = ImageStat.Stat(grey).stddev[0]
            minimum_std = c['capture'].getfloat('min_luma_stddev', 7.0)
            if deviation < minimum_std:
                raise ValueError(f'Podozrivo rovnomerná/sivá snímka, odchýlka={deviation:.1f} < {minimum_std:.1f}')
            return width, height, s, deviation
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError('Neplatný alebo poškodený JPEG') from e


def _curl_config_quoted(value):
    """Quote a curl config value without passing credentials on argv."""
    if any(x in value for x in ("\r", "\n", "\0")):
        raise ValueError('Neplatny znak v FTPS prihlasovacich udajoch')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def ftp_upload(c, local, dry_run):
    cfg = c['ftp']
    mode = cfg.get('mode', 'ftps').lower()
    if mode not in ('ftps', 'ftp'):
        raise ValueError('ftp mode musi byt ftps alebo ftp')
    remote_name = cfg.get('filename', 'latest.jpg').strip()
    if not remote_name or '/' in remote_name or '\\' in remote_name or remote_name in ('.', '..'):
        raise ValueError('Neplatny FTP filename')
    remote_dir = cfg.get('remote_dir', '/').strip() or '/'
    if dry_run:
        LOG.info('DRY-RUN: FTP prenos vynechany; ciel=%s/%s (rezim=%s)', remote_dir.rstrip('/'), remote_name, mode)
        return
    if mode == 'ftp' and not cfg.getboolean('allow_plain_ftp', False):
        raise ValueError('Nesifrovane FTP je zakazane')
    if not shutil.which('curl'):
        raise RuntimeError('Chyba curl: sudo apt install curl')
    import uuid
    from urllib.parse import quote
    host = cfg['host'].strip()
    if any(ch in host for ch in '/\\@?#') or not host:
        raise ValueError('Neplatny FTPS hostname')
    port = cfg.getint('port', 21)
    # curl upload is done under a unique filename, then FTP RNFR/RNTO publishes it.
    temporary = f'.{remote_name}.upload-{uuid.uuid4().hex[:12]}.tmp'
    upload_path = '/'.join(quote(seg, safe='') for seg in remote_dir.strip('/').split('/') if seg)
    upload_url = f'ftp://{host}:{port}/' + (upload_path + '/' if upload_path else '') + quote(temporary, safe='')
    # Credentials are sent via curl's stdin configuration, not process argv or logs.
    credentials = cfg['username'] + ':' + cfg['password']
    config_text = 'user = ' + _curl_config_quoted(credentials) + '\n'
    command = [
        'curl', '--config', '-', '--ssl-reqd' if mode == 'ftps' else '--ftp-pasv',
        '--ftp-pasv', '--fail', '--silent', '--show-error',
        '--connect-timeout', '12', '--max-time', '65',
        '--upload-file', str(local), '--url', upload_url,
    ]
    server = None
    try:
        result = subprocess.run(command, input=config_text, text=True,
                                capture_output=True, timeout=75)
        if result.returncode != 0:
            # curl stderr can include endpoint paths or secrets in some error cases.
            raise RuntimeError(f'curl FTPS upload zlyhal (exit={result.returncode})')
        # Only after curl has confirmed upload completion do we rename via TLS control channel.
        if mode == 'ftps':
            server = ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=20)
        else:
            server = ftplib.FTP(timeout=20)
        server.connect(host, port)
        server.login(cfg['username'], cfg['password'])
        if mode == 'ftps':
            server.prot_p()
        server.cwd(remote_dir)
        try:
            server.rename(temporary, remote_name)
        except ftplib.error_perm as err:
            if not cfg.getboolean('allow_nonatomic_replace', False):
                raise RuntimeError('RNTO zamietnute; povodny latest.jpg ostava bez zmeny') from err
            server.delete(remote_name)
            server.rename(temporary, remote_name)
        LOG.info('UPLOAD OK: %s/%s (curl FTPS + FTP rename)', remote_dir.rstrip('/'), remote_name)
    except Exception:
        if server is None:
            # Best-effort cleanup when upload may have completed but control connection failed.
            try:
                server = (ftplib.FTP_TLS(context=ssl.create_default_context(), timeout=10)
                          if mode == 'ftps' else ftplib.FTP(timeout=10))
                server.connect(host, port)
                server.login(cfg['username'], cfg['password'])
                if mode == 'ftps':
                    server.prot_p()
                server.cwd(remote_dir)
            except Exception:
                server = None
        if server:
            try:
                server.delete(temporary)
            except Exception:
                pass
        raise
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                server.close()

def run(args):
    c = settings(args.config)
    storage = Path(c['storage'].get('directory', str(BASE / 'data'))).expanduser()
    if not storage.is_absolute():
        storage = BASE / storage
    storage = storage.resolve()
    configure_log(storage / 'logs')
    from fcntl import flock, LOCK_EX, LOCK_NB
    with (storage / '.publisher.lock').open('w') as lock:
        try:
            flock(lock, LOCK_EX | LOCK_NB)
        except BlockingIOError:
            LOG.warning('Iná inštancia práve beží; preskakujem')
            return 0
        start = time.monotonic()
        staging = storage / f'.candidate-{os.getpid()}.jpg'
        try:
            uri = stream_url(c)
            # Každý pokus otvorí nové RTSP spojenie. Neplatný obraz nikdy
            # neprepíše lokálnu alebo verejnú fotografiu.
            attempts = c['capture'].getint('max_attempts', 3)
            delay = c['capture'].getfloat('retry_delay_seconds', 3.0)
            warmup_step = c['capture'].getint('retry_warmup_step_seconds', 4)
            if not 1 <= attempts <= 5:
                raise ValueError('max_attempts musí byť 1 až 5')
            if not 0 <= delay <= 30:
                raise ValueError('retry_delay_seconds musí byť 0 až 30')
            if not 0 <= warmup_step <= 10:
                raise ValueError('retry_warmup_step_seconds musí byť 0 až 10')
            base_warmup = c['capture'].getint('warmup_seconds', 8)
            if base_warmup + (attempts - 1) * warmup_step > 60:
                raise ValueError('Warm-up pri poslednom pokuse nesmie prekročiť 60 s')
            last_error = None
            for attempt in range(1, attempts + 1):
                staging.unlink(missing_ok=True)
                # ConfigParser čítame do kópie, aby sa nezmenila konfigurácia.
                attempt_config = configparser.ConfigParser(interpolation=None)
                attempt_config.read_dict({sec: dict(c.items(sec)) for sec in c.sections()})
                warmup = base_warmup + (attempt - 1) * warmup_step
                attempt_config.set('capture', 'warmup_seconds', str(warmup))
                try:
                    capture(attempt_config, uri, staging)
                    width, height, size, deviation = quality_check(staging, c)
                    LOG.info('KVALITA OK: pokus %d/%d, warmup=%ds, %dx%d, %d B, luma_stddev=%.1f',
                             attempt, attempts, warmup, width, height, size, deviation)
                    break
                except (RuntimeError, ValueError, OSError) as exc:
                    last_error = exc
                    # Nezverejňujeme pôvodný text chyby, môže obsahovať dáta streamu.
                    LOG.warning('SNIMKA NEPLATNA: pokus %d/%d, warmup=%ds, typ=%s',
                                attempt, attempts, warmup, type(exc).__name__)
                    staging.unlink(missing_ok=True)
                    if attempt < attempts:
                        time.sleep(delay)
            else:
                raise RuntimeError(f'Snímku sa nepodarilo overiť ani po {attempts} pokusoch; '
                                   f'posledná chyba: {type(last_error).__name__}')
            latest = storage / 'latest.jpg'
            os.replace(staging, latest)
            ftp_upload(c, latest, args.dry_run)
            LOG.info('CYKLUS OK: %.1f s', time.monotonic() - start)
            return 0
        except Exception as e:
            # Do not log raw exception string from networking libs: may embed credentials.
            msg = str(e)
            for section in ('camera', 'ftp'):
                for secret in (c[section].get('password', ''), c[section].get('username', '')):
                    if secret:
                        msg = msg.replace(secret, '[REDACTED]')
            LOG.error('CYKLUS FAIL [%s]: %s', type(e).__name__, msg)
            return 1
        finally:
            staging.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Arenti C3 snapshot publisher FTP/FTPS')
    parser.add_argument('--config', default=str(BASE / 'arenti_config.ini'))
    parser.add_argument('--dry-run', action='store_true', help='Vytvor/over JPG, ale neodosielaj na FTP')
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as e:
        print(f'CHYBA konfigurácie/spustenia: {type(e).__name__}: {e}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())
