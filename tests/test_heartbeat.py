"""Tests for non-blocking Uptime Kuma heartbeat (no network or credentials)."""
import configparser
import io
import logging
import unittest
from unittest.mock import patch

from arenti_heartbeat import send_success_heartbeat, _NoRedirect


class FakeResponse:
    status = 200

    def __init__(self, content=b'{"ok":true}'):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.content[:limit]


def cfg(url='https://example.test/api/push/SECRET?status=down',
        enabled='yes', extra=''):
    result = configparser.ConfigParser(interpolation=None)
    result.read_string('[monitoring]\nenabled = ' + enabled + '\npush_url = ' + url
                       + '\ntimeout_seconds = 3\n' + extra)
    return result


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.log = logging.getLogger('test-heartbeat')

    def test_omitted_monitoring_does_nothing(self):
        with patch('arenti_heartbeat.build_opener') as op:
            self.assertFalse(send_success_heartbeat(configparser.ConfigParser(), 10.0, self.log))
            op.assert_not_called()

    def test_disabled_does_nothing(self):
        with patch('arenti_heartbeat.build_opener') as op:
            self.assertFalse(send_success_heartbeat(cfg(enabled='no'), 10.0, self.log))
            op.assert_not_called()

    def test_success_builds_up_with_duration(self):
        with patch('arenti_heartbeat.build_opener') as op:
            op.return_value.open.return_value = FakeResponse()
            self.assertTrue(send_success_heartbeat(cfg(), 10.5, self.log))
            request = op.return_value.open.call_args.args[0]
            self.assertIn('status=up', request.full_url)
            self.assertIn('ping=10500', request.full_url)
            self.assertIn('msg=FTPS+upload+OK', request.full_url)
            self.assertEqual(op.return_value.open.call_args.kwargs['timeout'], 3.0)

    def test_http_requires_private_ip_and_optin(self):
        with patch('arenti_heartbeat.build_opener') as op:
            self.assertFalse(send_success_heartbeat(cfg('http://10.42.0.2:3001/api/push/SECRET'), 7, self.log))
            self.assertFalse(send_success_heartbeat(cfg(
                'http://example.test/api/push/SECRET', extra='allow_private_http = yes\n'), 7, self.log))
            op.assert_not_called()
        with patch('arenti_heartbeat.build_opener') as op:
            op.return_value.open.return_value = FakeResponse()
            self.assertTrue(send_success_heartbeat(cfg(
                'http://10.42.0.2:3001/api/push/SECRET', extra='allow_private_http = yes\n'), 7, self.log))

    def test_private_vhost_host_header(self):
        with patch('arenti_heartbeat.build_opener') as op:
            op.return_value.open.return_value = FakeResponse()
            private = cfg(
                'http://192.168.196.150:3001/api/push/SECRET',
                extra='allow_private_http = yes\\nhost_header = monitoring:3001\\n')
            self.assertTrue(send_success_heartbeat(private, 11.2, self.log))
            request = op.return_value.open.call_args.args[0]
            self.assertEqual(request.get_header('Host'), 'monitoring:3001')
            self.assertIn('192.168.196.150', request.full_url)

    def test_reject_host_header_injection(self):
        with patch('arenti_heartbeat.build_opener') as op:
            private = cfg('http://192.168.196.150:3001/api/push/SECRET',
                          extra='allow_private_http = yes\\nhost_header = not-valid/path\\n')
            self.assertFalse(send_success_heartbeat(private, 11, self.log))
            op.assert_not_called()

    def test_no_secret_logged_on_error(self):
        with patch('arenti_heartbeat.build_opener') as op:
            op.return_value.open.side_effect = RuntimeError('https://example.test/api/push/SECRET')
            stream = io.StringIO()
            handler = logging.StreamHandler(stream)
            self.log.addHandler(handler)
            try:
                self.assertFalse(send_success_heartbeat(cfg(), 10.0, self.log))
                self.assertNotIn('SECRET', stream.getvalue())
            finally:
                self.log.removeHandler(handler)

    def test_bad_body_and_path_dont_raise(self):
        with patch('arenti_heartbeat.build_opener') as op:
            op.return_value.open.return_value = FakeResponse(b'{"ok":false}')
            self.assertFalse(send_success_heartbeat(cfg(), 10.0, self.log))
            self.assertFalse(send_success_heartbeat(cfg(
                'https://example.test/not-a-push/SECRET'), 10.0, self.log))

    def test_redirect_is_forbidden(self):
        self.assertIsNone(_NoRedirect().redirect_request(
            None, None, 302, 'Found', {}, 'https://evil.invalid'))

    def test_invalid_timeout_nonfatal(self):
        c = cfg()
        c['monitoring']['timeout_seconds'] = '999'
        self.assertFalse(send_success_heartbeat(c, 10.0, self.log))


if __name__ == '__main__':
    unittest.main()
