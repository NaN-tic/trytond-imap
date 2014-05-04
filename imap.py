# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool
from trytond.pyson import Eval

import imaplib

__all__ = ['IMAPServer']


class IMAPServer(ModelSQL, ModelView):
    'IMAP Server'
    __name__ = 'imap.server'
    name = fields.Char('Name', required=True)
    host = fields.Char('Server', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    port = fields.Integer('Port', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    ssl = fields.Boolean('SSL',
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    username = fields.Char('Username', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    password = fields.Char('Password', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    email = fields.Char('Email', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'],
        help='Default From (if active this option) and Reply Email')
    state = fields.Selection([
            ('draft', 'Draft'),
            ('done', 'Done'),
            ], 'State', readonly=True, required=True)

    @classmethod
    def __setup__(cls):
        super(IMAPServer, cls).__setup__()
        cls._error_messages.update({
                'connection_successful': ('Successful IMAP test connection '
                    'using account "%s".'),
                'test_details': 'IMAP test connection Details:\n%s',
                'connection_error': 'IMAP connection test failed.',
                })
        cls._buttons.update({
            'test': {},
            'draft': {
                'invisible': Eval('state') == 'draft',
                },
            'done': {
                'invisible': Eval('state') == 'done',
                },
            })

    @staticmethod
    def default_ssl():
        return True

    @staticmethod
    def default_port():
        return 993

    @staticmethod
    def default_state():
        return 'draft'

    @classmethod
    @ModelView.button
    def draft(cls, servers):
        draft = []
        for server in servers:
            draft.append(server)
        cls.write(draft, {
            'state': 'draft',
            })

    @classmethod
    @ModelView.button
    def done(cls, servers):
        done = []
        for server in servers:
            done.append(server)
        cls.write(done, {
            'state': 'done',
            })

    @classmethod
    @ModelView.button
    def test(cls, servers):
        "Checks IMAP credentials and confirms if connection works"
        for server in servers:
            try:
                cls.get_imap_server(server)
            except Exception, message:
                cls.raise_user_error('test_details', message)
            except:
                cls.raise_user_error('connection_error')
            cls.raise_user_error('connection_successful', server.rec_name)

    @staticmethod
    def get_imap_server(server):
        """
        Instantiate, configure and return a IMAP4 or IMAP4_SSL instance from
        imaplib.
        """
        if server.ssl:
            imap = imaplib.IMAP4_SSL(server.host, server.port)
        else:
            imap = imaplib.IMAP4(server.host, server.port)

        imap.login(server.username.encode('UTF-8'),
            server.password.encode('UTF-8'))
        return imap
