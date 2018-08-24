# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, fields, Unique
from trytond.pyson import Eval

import logging
try:
    import imaplib2
except ImportError:
    message = 'Unable to import imaplib2'
    logging.getLogger('GetmailServer').error(message)
    raise Exception(message)

__all__ = ['IMAPServer']


class IMAPServer(ModelSQL, ModelView):
    'IMAP Server'
    __name__ = 'imap.server'
    name = fields.Char('Name', required=True)
    host = fields.Char('Server', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            }, depends=['state'])
    ssl = fields.Boolean('SSL',
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    port = fields.Integer('Port', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            }, depends=['state'])

    folder = fields.Char('Folder', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            }, help='The folder name where to read from on the server.')
    timeout = fields.Integer('Time Out', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            }, help=('Time to wait until connection is established. '
                'In seconds.'))
    criterion = fields.Char('Criterion', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            }, help=('The criteria to filter when dowload messages. By '
                'default is only take the unread mesages, but it is possible '
                'to take "ALL"'))
    email = fields.Char('Email', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'],
        help='Default From (if active this option) and Reply Email')
    user = fields.Char('Username', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    password = fields.Char('Password', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    state = fields.Selection([
            ('draft', 'Draft'),
            ('done', 'Done'),
            ], 'State', readonly=True, required=True)

    @classmethod
    def __setup__(cls):
        super(IMAPServer, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('account_uniq', Unique(t, t.user),
                'The email account must be unique!'),
            ]
        cls._error_messages.update({
                'connection_successful': ('Successful IMAP test connection '
                    'using account "%s".'),
                'test_details': 'IMAP test connection Details:\n%s',
                'connection_error': 'IMAP connection test failed.',
                'general_error': 'Error IMAP Server:\n%s',
                'login_error': ('Error IMAP Server:\nLogin with user "%s" '
                    'could not be possible.\n\n%s'),
                'select_error': ('Error IMAP Server:\nCould not select "%s" '
                    'mailbox.\n\n%s'),
                'search_error': ('Error IMAP Server:\nCould not search "%s" '
                    'messages.\n\n%s'),
                'fetch_error': ('Error IMAP Server:\nCould not get id "%s" '
                    'messages.\n\n%s'),
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
    def default_port():
        return 993

    @staticmethod
    def default_folder():
        return 'INBOX'

    @staticmethod
    def default_timeout():
        return 30

    @staticmethod
    def default_criterion():
        return 'UNSEEN'

    @staticmethod
    def default_ssl():
        return True

    @staticmethod
    def default_state():
        return 'draft'

    @fields.depends('ssl')
    def on_change_with_port(self):
        return self.ssl and 993 or 143

    @fields.depends('email')
    def on_change_with_user(self):
        return self.email or ""

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
            imapper = cls.connect(server)
            imapper.logout()
            cls.raise_user_error('connection_successful', server.rec_name)

    @classmethod
    def connect(cls, server, keyfile=None, certfile=None, ca_certs=None,
        cert_verify_cb=None, debug=0, debug_file=None, identifier=None,
        debug_buf_lvl=None):
        imapper = cls.get_server(server.host, server.port, server.ssl,
            keyfile, certfile, ca_certs, cert_verify_cb, debug, debug_file,
            identifier, server.timeout, debug_buf_lvl)
        return cls.login(imapper, server.user.encode('UTF-8'),
            server.password.encode('UTF-8'))

    @classmethod
    def get_server(cls, host, port, ssl=False, keyfile=None,
        certfile=None, ca_certs=None, cert_verify_cb=None, debug=0,
        debug_file=None, identifier=None, timeout=120, debug_buf_lvl=None):
        try:
            if ssl:
                return imaplib2.IMAP4_SSL(host=str(host), port=int(port),
                    keyfile=keyfile, certfile=certfile, ca_certs=ca_certs,
                    cert_verify_cb=cert_verify_cb, debug=debug,
                    debug_file=debug_file, identifier=identifier,
                    timeout=timeout, debug_buf_lvl=debug_buf_lvl)
            else:
                return imaplib2.IMAP4(host=str(host), port=int(port),
                    debug=debug, debug_file=debug_file, identifier=identifier,
                    timeout=timeout, debug_buf_lvl=debug_buf_lvl)
        except Exception as e:
            cls.raise_user_error('general_error', e)

    @classmethod
    def login(cls, imapper, user, password):
        try:
            status, data = imapper.login(user, password)
        except Exception as e:
            imapper.logout()
            status = 'NO'
            data = e
        finally:
            if status != 'OK':
                imapper.logout()
                cls.raise_user_error('login_error', (user, data))
        return imapper

    @classmethod
    def fetch(cls, imapper, server, readonly=False, charset=None,
        parts='(UID RFC822)'):
        emailids = cls.search_mails(imapper, server.folder, readonly, charset,
            server.criterion)
        result = {}
        for emailid in emailids:
            result.update(cls.fetch_mail(imapper, emailid, parts))
        imapper.close()
        imapper.logout()
        return result

    @classmethod
    def search_mails(cls, imapper, mailbox='INBOX',
        readonly=False, charset=None, criterion='ALL'):
        try:
            status, data = imapper.select(mailbox, readonly)
        except Exception as e:
            imapper.logout()
            status = 'NO'
            data = e
        finally:
            if status != 'OK':
                imapper.logout()
                cls.raise_user_error('select_error', (mailbox, data))
        try:
            status, data = imapper.search(charset, criterion)
        except Exception as e:
            imapper.logout()
            status = 'NO'
            data = e
        finally:
            if status != 'OK':
                imapper.logout()
                cls.raise_user_error('search_error', (criterion, data))
        return data[0].split()

    @classmethod
    def fetch_mail(cls, imapper, emailid, parts='(UID RFC822)'):
        result = {}
        try:
            status, data = imapper.fetch(emailid, parts)
        except Exception as e:
            imapper.logout()
            status = 'NO'
            data = e
        finally:
            if status != 'OK':
                imapper.logout()
                cls.raise_user_error('fetch_error', (emailid, data))
        result[emailid] = data
        return result
