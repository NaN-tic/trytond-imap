# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
try:
    from trytond.modules.imap.tests.test_imap import (
        suite, create_imap_server, create_mock_imap_conn, create_mock_mails)
except ImportError:
    from .test_imap import (suite, create_imap_server, create_mock_imap_conn,
        create_mock_mails)

__all__ = ['suite', 'create_imap_server', 'create_mock_imap_conn',
    'create_mock_mails']
