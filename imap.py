# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Bool
import socket
import datetime
import logging
from trytond.i18n import gettext
from trytond.exceptions import UserError

from imaplib import IMAP4, IMAP4_SSL

__all__ = ['IMAPServer']

_IMAP_DATE_FORMAT = "%d-%b-%Y"

logger = logging.getLogger(__name__)


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
    criterion = fields.Char('Criterion', required=False,
        states={
            'readonly': (Eval('state') != 'draft'),
            'invisible': Bool(Eval('search_mode') != 'custom'),
            'required': Bool(Eval('search_mode') == 'custom')
            }, depends=['state', 'search_mode'])
    criterion_used = fields.Function(fields.Char('Criterion used'),
        'get_criterion_used')
    email = fields.Char('Email', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'],
        help='Default From (if active this option) and Reply Email')
    user = fields.Char('Username', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    password = fields.Char('Password', required=True, strip=False,
        states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    state = fields.Selection([
            ('draft', 'Draft'),
            ('done', 'Done'),
            ], 'State', readonly=True, required=True)
    search_mode = fields.Selection([
            ('unseen', 'Unseen'),
            ('interval', 'Time Interval'),
            ('custom', 'Custom')
            ], 'Search Mode',
        states={
            'readonly': (Eval('state') != 'draft'),
            }, depends=['state', 'search_mode'],
        help='The criteria to filter when download messages. By '
            'default is only take the unread mesages, but it is possible '
            'to take a time interval or a custom selection')
    last_retrieve_date = fields.Date('Last Retrieve Date',
        states={
                'invisible': Bool(Eval('search_mode') != 'interval'),
                'readonly': (Eval('state') != 'draft'),
                }, depends=['state', 'search_mode'])
    offset = fields.Integer('Days Offset', domain=[('offset', '>=', 1)],
        states={
                'invisible': Bool(Eval('search_mode') != 'interval'),
                'readonly': (Eval('state') != 'draft'),
                }, depends=['state', 'search_mode'], required=True)
    mark_seen = fields.Boolean('Mark as seen',
        help='Mark emails as seen on fetch.')
    action_after_read = fields.Selection([
            ('nothing', 'Nothing'),
            ('move', 'Move to a folder'),
            ('delete', 'Delete messages'),
            ], 'Action after read',
        states={
            'readonly': (Eval('state') != 'draft'),
            }, depends=['state'],
        help='The action to do after each email is readed.')
    destination_folder = fields.Char('Move Folder',
        states={
            'invisible': Bool(Eval('action_after_read') != 'move'),
            'required': Bool(Eval('action_after_read') == 'move'),
            'readonly': (Eval('state') != 'draft'),
            }, depends=['state', 'action_after_read'],
            help='The folder name where to move to on the server.'
            ' Absolut path')

    @classmethod
    def __setup__(cls):
        super(IMAPServer, cls).__setup__()
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
    def default_search_mode():
        return 'unseen'

    @staticmethod
    def default_offset():
        return 1

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
        return 'ALL'

    @staticmethod
    def default_ssl():
        return True

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_mark_seen():
        return True

    @staticmethod
    def default_action_after_read():
        return 'nothing'

    @fields.depends('ssl')
    def on_change_with_port(self):
        return self.ssl and 993 or 143

    @fields.depends('email')
    def on_change_with_user(self):
        return self.email or ""

    def get_criterion_used(self, name=None):
        if self.search_mode == 'interval':
            if not self.last_retrieve_date:
                return 'ALL'
            offset = datetime.timedelta(days=self.offset)
            date_with_offset = self.last_retrieve_date - offset
            return '(SINCE "%s")' % date_with_offset.strftime(
                _IMAP_DATE_FORMAT)
        elif self.search_mode == 'unseen':
            return 'UNSEEN'
        return self.criterion

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
            imapper.select()
            cls.logout(imapper)
            raise UserError(gettext('imap.connection_successful',
                account=server.rec_name))

    @classmethod
    def connect(cls, server, keyfile=None, certfile=None,
            debug=0, identifier=None):
        imapper = cls.get_server(server.host, server.port, server.ssl,
            keyfile, certfile, debug, identifier, server.timeout)
        return cls.login(imapper, server.user,
            server.password)

    @classmethod
    def get_server(cls, host, port, ssl=False, keyfile=None,
            certfile=None, debug=0, identifier=None, timeout=120):
        '''
        Obtain an IMAP opened connection
        '''
        try:
            if ssl:
                return IMAP4_SSL(host=str(host), port=int(port),
                    keyfile=keyfile, certfile=certfile, timeout=timeout)
            else:
                return IMAP4(host=str(host), port=int(port),
                    timeout=timeout)
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            raise UserError(gettext('imap.general_error', msg=e))

    @classmethod
    def login(cls, imapper, user, password):
        '''
        Authenticates an imap connection
        '''
        try:
            status, data = imapper.login(user, password)
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'NO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.login_error',
                user=user, msg=data))
        return imapper

    @classmethod
    def logout(cls, imapper):
        try:
            imapper.close()    # which also expunges the mailbox
        except:
            pass
        imapper.logout()

    def select_folder(self, imapper):
        '''
        Select the IMAP folder where to interact.
        '''
        status = None
        try:
            readonly = (True if self.action_after_read == 'nothing'
                and not self.mark_seen else False)
            status, data = imapper.select(self.folder, readonly)
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'NO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.select_error',
                folder=self.folder, msg=data))

    def fetch_ids(self, imapper):
        '''
        Obtain the next set of e-mail IDs according to the configuration
        defined on the server object.
        '''
        self.select_folder(imapper)
        status = None
        try:
            status, data = imapper.search(None, self.criterion_used)
            self.last_retrieve_date = datetime.date.today()
            self.save()
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'NO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.search_error',
                criteria=self.criterion_used, msg=data))
        return data[0].split()

    def fetch_one(self, imapper, emailid, parts='(UID RFC822)'):
        '''
        Fetch the content of a single e-mail ID obtained using fetch_ids()
        '''
        result = {}
        try:
            status, data = imapper.fetch(emailid, parts)
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.fetch_error',
                email=emailid, msg=data))
        result[emailid] = data
        return result

    def set_flag_seen(self, imapper, emailid):
        '''
        Mark email as seen if the flag is set to True
        '''
        if not imapper or not emailid:
            return
        try:
            if self.mark_seen:
                status, data = imapper.store(emailid, '+FLAGS', '\\Seen')
            else:
                status = 'OK'
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.fetch_error',
                email=emailid, msg=data))

    def fetch(self, imapper, parts='(UID RFC822)'):
        '''
        Fetch the next set of e-mails according to the configuration defined
        on the server object. It equivalent to calling fetch_ids() and calling
        fetch_one() for each e-mail ID.
        '''
        emailids = self.fetch_ids(imapper)
        result = {}
        for emailid in emailids:
            result.update(self.fetch_one(imapper, emailid, parts))
            self.set_flag_seen(imapper, emailid)
        return result

    def copy_email_to(self, imapper, emailid):
        '''
        Copy the email to the destionation folder deffined in the configuration
        server.
        '''
        try:
            status, data = imapper.copy(emailid, self.destination_folder)
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly,
                socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.fetch_error',
                email=emailid, msg=data))

    def delete_email(self, imapper, emailid):
        '''
        Delete the email from the main folder deffined in the configuration
        server.
        '''
        try:
            status, data = imapper.store(emailid, '+FLAGS', '\\Deleted')
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly,
                socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.fetch_error',
                email=emailid, msg=data))

    def action_after(self, imapper, emailids=None):
        '''
        With specific IDs or the same filter deffined for the fetch,
        do some extra actions on this emails in IMAP server.
        '''
        # select IMAP folder before act on any email of this folder
        self.select_folder(imapper)

        status = None
        if ((self.action_after_read == 'move' and self.destination_folder)
                or self.action_after_read == 'delete'):
            if not emailids:
                emailids = self.fetch_ids(imapper)
            for emailid in emailids:
                if self.action_after_read == 'move':
                    self.copy_email_to(imapper, emailid)
                self.delete_email(imapper, emailid)
            if emailids:
                imapper.expunge()
        return status
