"""Optional best-effort Uptime Kuma Push heartbeat after successful FTPS publish.

Never log the secret push URL or exception messages that may contain it.
"""
import ipaddress
import json
import logging
import re
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _NoRedirect(HTTPRedirectHandler):
    """Do not forward a token-bearing URL to a redirect target."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def send_success_heartbeat(config, elapsed_seconds, logger=None):
    """Send Kuma push if enabled; any failure returns False, never raises.

    Caller must invoke this only AFTER successful remote FTP rename,
    never on a dry run. Push URL is private configuration, not a CLI arg.
    """
    log = logger or logging.getLogger('arenti')
    phase = 'config'
    started = time.monotonic()
    try:
        if not config.has_section('monitoring'):
            return False
        mon = config['monitoring']
        if not mon.getboolean('enabled', False):
            return False
        endpoint = mon.get('push_url', '').strip()
        if not endpoint:
            log.warning('HEARTBEAT SKIP: push_url nie je nastavena')
            return False
        timeout = mon.getfloat('timeout_seconds', 3.0)
        if not 0.5 <= timeout <= 10.0:
            raise ValueError('bad heartbeat timeout')
        parts = urlsplit(endpoint)
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            raise ValueError('invalid heartbeat URL')
        if parts.username or parts.password or not parts.path.startswith('/api/push/'):
            raise ValueError('invalid push URL path')
        if parts.scheme == 'http':
            if not mon.getboolean('allow_private_http', False):
                raise ValueError('HTTP not explicitly enabled for private network')
            try:
                private_ip = ipaddress.ip_address(parts.hostname)
            except ValueError as exc:
                raise ValueError('HTTP requires a private IP address') from exc
            if not private_ip.is_private:
                raise ValueError('HTTP requires a private IP address')
        if parts.fragment:
            raise ValueError('unexpected URL fragment')
        # Synology nginx can route only for Host: monitoring:3001, even when
        # addressed by a private ZeroTier IP. Never accept CRLF/header injection.
        host_header = mon.get('host_header', '').strip()
        if host_header:
            if parts.scheme != 'http' or not re.fullmatch(
                    r'[A-Za-z0-9][A-Za-z0-9.-]*(?::[0-9]{1,5})?', host_header):
                raise ValueError('invalid private HTTP Host header')
        # Preserve any Kuma-generated query, but override status parameters.
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query.update(status='up', msg='FTPS upload OK',
                     ping=str(max(0, round(elapsed_seconds * 1000))))
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ''))
        headers = {
            'User-Agent': 'arenti-publisher/heartbeat',
            'Cache-Control': 'no-store',
        }
        if host_header:
            headers['Host'] = host_header
        request = Request(url, headers=headers)
        # Direct to ZeroTier IP; do not use environment proxies or redirects.
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        phase = 'headers'
        with opener.open(request, timeout=timeout) as response:
            headers_ms = round((time.monotonic() - started) * 1000)
            if response.status != 200:
                raise ValueError('non-200 from push API')
            phase = 'body'
            body_started = time.monotonic()
            raw = response.read(4096)
            body_ms = round((time.monotonic() - body_started) * 1000)
            result = json.loads(raw.decode('utf-8'))
            if not isinstance(result, dict) or result.get('ok') is not True:
                raise ValueError('unexpected Kuma response')
        log.info('HEARTBEAT OK: Kuma Push prijal potvrdenie headers_ms=%d body_ms=%d total_ms=%d',
                 headers_ms, body_ms, round((time.monotonic() - started) * 1000))
        return True
    except Exception as exc:
        # Never include URL, token, or exception string in logs.
        log.warning('HEARTBEAT FAIL: %s phase=%s elapsed_ms=%d',
                    type(exc).__name__, phase,
                    round((time.monotonic() - started) * 1000))
        return False
