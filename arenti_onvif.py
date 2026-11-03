#!/usr/bin/env python3
"""Arenti C3 ONVIF diagnostics and optional JPEG snapshot, stdlib only."""
import argparse
import base64
import datetime as dt
import configparser
import getpass
import hashlib
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

WSSE = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd'
WSU = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd'
MEDIA = 'http://www.onvif.org/ver10/media/wsdl'
SOAP = 'http://www.w3.org/2003/05/soap-envelope'
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, 'arenti_config.ini')

def read_config(path=CONFIG):
    cfg = configparser.ConfigParser(interpolation=None)
    if not os.path.isfile(path):
        raise RuntimeError(f'Chyba konfiguracia: {path} neexistuje. Uloz arenti_config.ini vedla skriptu.')
    cfg.read(path, encoding='utf-8')
    if 'camera' not in cfg:
        raise RuntimeError('Chyba konfiguracia: chyba sekcia [camera].')
    section = cfg['camera']
    host = section.get('host', '').strip()
    username = section.get('username', '').strip()
    password = section.get('password', '')
    if not host or not username or not password or password == 'DOPLN_SVOJE_ONVIF_HESLO':
        raise RuntimeError('Dopln host, username a password do arenti_config.ini.')
    port = section.getint('port', fallback=8000)
    if not 1 <= port <= 65535:
        raise RuntimeError('Neplatny port.')
    if os.name == 'posix' and (os.stat(path).st_mode & 0o077):
        print('UPOZORNENIE: config mozu citat ini pouzivatelia; spusti: chmod 600 ' + path)
    return host, port, username, password

def local(tag):
    return tag.rsplit('}', 1)[-1]

def children_named(node, name):
    return [x for x in node.iter() if local(x.tag) == name]

def first_text(node, name):
    for x in children_named(node, name):
        if x.text:
            return x.text.strip()
    return ''

def soap_request(url, body, username, password):
    nonce = os.urandom(16)
    created = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode()
    nonce64 = base64.b64encode(nonce).decode()
    payload = f'''<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{SOAP}" xmlns:trt="{MEDIA}" xmlns:wsse="{WSSE}" xmlns:wsu="{WSU}">
<s:Header><wsse:Security s:mustUnderstand="1"><wsse:UsernameToken>
<wsse:Username>{escape(username)}</wsse:Username>
<wsse:Password Type="{WSSE.replace('wssecurity-secext-1.0.xsd','username-token-profile-1.0#PasswordDigest')}">{digest}</wsse:Password>
<wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">{nonce64}</wsse:Nonce>
<wsu:Created>{created}</wsu:Created>
</wsse:UsernameToken></wsse:Security></s:Header>
<s:Body>{body}</s:Body></s:Envelope>'''
    request = urllib.request.Request(url, data=payload.encode('utf-8'), headers={'Content-Type': 'application/soap+xml; charset=utf-8'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status, data = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, data = exc.code, exc.read()
    print(f'HTTP: {status}')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise RuntimeError('Server nevrátil platnú SOAP XML odpoveď')
    faults = children_named(root, 'Fault')
    if faults:
        fault = faults[0]
        print('SOAP Fault:', first_text(fault, 'Text') or first_text(fault, 'Value') or ET.tostring(fault, encoding='unicode')[:500])
        return None
    if status != 200:
        print('Neočakávaný HTTP status')
        return None
    return root

def main():
    parser = argparse.ArgumentParser(description='ONVIF diagnostika Arenti C3')
    parser.add_argument('--config', default=CONFIG, help='INI subor s prihlasenim')
    parser.add_argument('--host', default=None, help='Volitelne prepisat IP z konfiguracie')
    parser.add_argument('--port', type=int, default=None, help='Volitelne prepisat port z konfiguracie')
    parser.add_argument('--save', metavar='JPG', help='Voliteľne stiahne prvú dostupnú JPEG snímku')
    args = parser.parse_args()
    host, port, username, password = read_config(args.config)
    host, port = args.host or host, args.port or port
    url = f'http://{host}:{port}/onvif/media_service'
    print('ONVIF Media:', url)
    print('ONVIF používateľ:', username, '(z konfigurácie)')
    print('\n=== GetProfiles ===')
    root = soap_request(url, '<trt:GetProfiles/>', username, password)
    if root is None:
        print('Nepodarilo sa získať profily. Skontroluj ONVIF meno/heslo a čas kamery.')
        return 1
    profiles = []
    for profile in children_named(root, 'Profiles'):
        token = profile.attrib.get('token')
        name = first_text(profile, 'Name')
        width = first_text(profile, 'Width')
        height = first_text(profile, 'Height')
        print(f'Profil: {name or "(bez názvu)"} | Token: {token or "(bez tokenu)"} | Rozlíšenie: {width or "?"}x{height or "?"}')
        if token:
            profiles.append(token)
    if not profiles:
        print('Kamera nevrátila žiadny video profil.')
        return 1
    first_uri = None
    print('\n=== GetSnapshotUri ===')
    for token in profiles:
        body = f'<trt:GetSnapshotUri><trt:ProfileToken>{escape(token)}</trt:ProfileToken></trt:GetSnapshotUri>'
        result = soap_request(url, body, username, password)
        if result is not None:
            uri = first_text(result, 'Uri')
            if uri:
                # URI may contain camera credentials; don't print sensitive URL components.
                parsed = urlsplit(uri)
                print(f'Profil {token}: URI získaná ({parsed.scheme.upper()}, host: {parsed.hostname}, port: {parsed.port or "default"})')
                if first_uri is None:
                    first_uri = uri
            else:
                print(f'Profil {token}: Kamera nevrátila URI')
    if args.save:
        if not first_uri:
            print('Nemožno uložiť JPG: kamera nevrátila Snapshot URI.')
            return 2
        print('\n=== Sťahovanie JPG ===')
        # Some cameras require Digest HTTP authentication for snapshot GET.
        manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        manager.add_password(None, first_uri, username, password)
        opener = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(manager), urllib.request.HTTPBasicAuthHandler(manager))
        try:
            with opener.open(first_uri, timeout=12) as response:
                content = response.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024 or not content.startswith(b'\xff\xd8\xff'):
                print('Odpoveď nie je platná JPEG snímka (alebo je priveľká).')
                return 3
            with open(args.save, 'wb') as output:
                output.write(content)
            print(f'Uložené: {args.save} ({len(content)} B)')
        except (urllib.error.URLError, OSError) as exc:
            print(f'Sťahovanie zlyhalo: {exc}')
            return 3
    print('\nDiagnostika dokončená.')
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, urllib.error.URLError, RuntimeError, ValueError) as exc:
        print(f'Chyba spojenia: {exc}')
        sys.exit(1)
