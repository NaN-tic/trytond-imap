
# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

try:
    # Python >= 3.3
    from unittest.mock import MagicMock
except ImportError:
    # Python < 3.3
    from mock import MagicMock

from trytond.tests.test_tryton import ModuleTestCase, with_transaction

from trytond.pool import Pool
from imaplib import IMAP4, IMAP4_SSL


def create_imap_server(provider):
    '''
    Create an IMAPServer using trytond(Pool()) or proteus(Model)
    '''
    IMAPServer = provider.get('imap.server')
    imap_server = IMAPServer(
        name='test server',
        host='localhost',
        port=8888,
        email='test@example.com',
        user='test@example.com',
        password='testpw',
        offset=1,
        )
    return imap_server


def create_mock_mails():
    '''
    Create a list of mock mails
    '''
    test_email_from = "Sender <sender@example.com>"
    test_email_subject = "My test Email"
    test_email_body = "Reporting some issue blablabla"
    test_email_1 = "To: test@example.com\nFrom: " + test_email_from \
        + "\nMessage-ID: 1" + "\nSubject: " + test_email_subject + "\n\n" \
        + test_email_body
    test_email_2 = "To: test@example.com\nFrom: " + test_email_from \
        + "\nMessage-ID: 2" + "\nSubject: " + test_email_subject + "\n\n" \
        + test_email_body

    imap_emails = {
        "1": ("OK", (("1", test_email_1),)),
        "2": ("OK", (("2", test_email_2),)),
        }

    return imap_emails


def create_mock_imap_conn(ssl, mails):
    '''
    Create a mocked imap connection
    '''
    mail_list = ("OK", (" ".join(list(mails.keys())),))
    if ssl:
        mock_conn = MagicMock(spec=IMAP4_SSL)
    else:
        mock_conn = MagicMock(spec=IMAP4)

    mock_conn.login.return_value = ('OK', [])
    mock_conn.capability.return_value = ('OK', ["A B C"])
    mock_conn.search = MagicMock(
        return_value=mail_list)
    # we ignore the second arg as the data item/mime-part is constant (RFC822)
    mock_conn.fetch = MagicMock(
        side_effect=lambda x, _: mails[x])
    mock_conn.select = MagicMock(return_value=mail_list)

    return mock_conn


class ImapTestCase(ModuleTestCase):
    'Test Imap module'
    module = 'imap'

    @with_transaction()
    def test_connect_without_ssl(self):
        pool = Pool()
        IMAPServer = pool.get('imap.server')
        server = create_imap_server(pool)
        server.ssl = False
        server.save()
        mails = create_mock_mails()
        mock_conn = create_mock_imap_conn(ssl=server.ssl, mails=mails)
        IMAPServer.get_server = MagicMock(return_value=mock_conn)
        imapper = IMAPServer.connect(server)
        self.assertNotIsInstance(imapper, IMAP4_SSL)

    @with_transaction()
    def test_connect_with_ssl(self):
        pool = Pool()
        IMAPServer = pool.get('imap.server')
        server = create_imap_server(pool)
        server.save()
        mails = create_mock_mails()
        mock_conn = create_mock_imap_conn(ssl=server.ssl, mails=mails)
        IMAPServer.get_server = MagicMock(return_value=mock_conn)
        imapper = IMAPServer.connect(server)
        self.assertIsInstance(imapper, IMAP4_SSL)

    @with_transaction()
    def test_fetch_ids(self):
        pool = Pool()
        IMAPServer = pool.get('imap.server')
        server = create_imap_server(pool)
        server.save()
        mails = create_mock_mails()
        mock_conn = create_mock_imap_conn(ssl=server.ssl, mails=mails)
        IMAPServer.get_server = MagicMock(return_value=mock_conn)
        imapper = IMAPServer.connect(server)
        data = server.fetch_ids(imapper)
        self.assertEqual(data, list(mails.keys()))

    @with_transaction()
    def test_fetch(self):
        pool = Pool()
        IMAPServer = pool.get('imap.server')
        server = create_imap_server(pool)
        server.save()
        mails = create_mock_mails()
        mock_conn = create_mock_imap_conn(ssl=server.ssl, mails=mails)
        IMAPServer.get_server = MagicMock(return_value=mock_conn)
        imapper = IMAPServer.connect(server)
        result = server.fetch(imapper)
        expected = {}
        for k, v in mails.items():
            expected.update({k: v[1]})
        self.assertEqual(result, expected)


del ModuleTestCase
