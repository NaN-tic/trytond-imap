"""Regression tests for bounded Google requests and OAuth authentication."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from google.auth.exceptions import TransportError

from trytond.modules.imap import imap


class OAuthTestCase(unittest.TestCase):

    def test_refresh_deadline(self):
        with patch.object(imap.time, 'monotonic', side_effect=[10, 12, 40]):
            request = imap.BoundedGoogleRequest(30)
            try:
                with patch.object(imap.Request, '__call__') as send:
                    request(url='https://example.com/token')
                    self.assertEqual(send.call_args.kwargs['timeout'], 28)
                    with self.assertRaises(TransportError):
                        request(url='https://example.com/token')
                    self.assertEqual(send.call_count, 1)
            finally:
                request.session.close()

    def test_refresh_retry_limit(self):
        request = imap.BoundedGoogleRequest(30)
        try:
            with patch.object(imap.Request, '__call__') as send:
                for _ in range(3):
                    request(url='https://example.com/token')
                with self.assertRaises(TransportError):
                    request(url='https://example.com/token')
                self.assertEqual(send.call_count, 3)
        finally:
            request.session.close()

    def test_google_error_challenge(self):
        connection = MagicMock()

        def authenticate(mechanism, callback):
            self.assertEqual(mechanism, 'XOAUTH2')
            self.assertEqual(callback(b''), 'credentials')
            self.assertEqual(callback(b'{"status":"401"}'), b'')
            return 'OK', []

        connection.authenticate.side_effect = authenticate
        imap.IMAPServer.login(SimpleNamespace(types='google'), connection,
            'XOAUTH2', 'credentials', auth=True)

    def test_google_reauthorization(self):
        server = SimpleNamespace(oauth_credentials={'token': 'old'},
            save=MagicMock())
        with patch.object(imap, 'PRODUCTION_ENV', True), \
                patch.object(imap, 'GOOGLE_CLIENT_SECRETS', '{}'), \
                patch.object(imap, 'GOOGLE_SCOPES', ['mail']), \
                patch.object(imap, 'GOOGLE_REDIRECT_URI', 'https://example.com'), \
                patch.object(imap.Flow, 'from_client_config') as factory:
            flow = factory.return_value
            flow.authorization_url.return_value = ('https://google.com', 'state')
            # Exercise the button body without the database access decorator.
            result = imap.IMAPServer.google.__wrapped__(
                imap.IMAPServer, [server])
            self.assertEqual(result['type'], 'ir.action.url')
            self.assertEqual(result['url'], 'https://google.com')
            self.assertEqual(server.session_id, 'state')
            self.assertEqual(server.oauth_credentials, {'token': 'old'})
            self.assertEqual(
                flow.authorization_url.call_args.kwargs['prompt'], 'consent')
