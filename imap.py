# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import json
import logging
import socket
from imaplib import IMAP4, IMAP4_SSL

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request

from trytond.model import ModelSQL, ModelView, fields, DictSchemaMixin
from trytond.config import config
from trytond.pyson import Bool, Eval
from trytond.exceptions import UserError
from trytond.i18n import gettext

_IMAP_DATE_FORMAT = "%d-%b-%Y"

logger = logging.getLogger(__name__)
PRODUCTION_ENV = config.getboolean('database', 'production', default=False)

# Define the client secret information
GOOGLE_CLIENT_SECRETS = config.get('oauth', 'google')

# Define the scopes
GOOGLE_SCOPES_STR = config.get('oauth', 'google_scopes')
GOOGLE_SCOPES = GOOGLE_SCOPES_STR.split(',') if GOOGLE_SCOPES_STR else []
GOOGLE_SCOPES = [scope.strip() for scope in GOOGLE_SCOPES]

# Define the redirect URI
GOOGLE_REDIRECT_URI = config.get('oauth', 'google_redirect_uri')

OUTLOOK_URL = config.get('oauth', 'outlook_uri')


class IMAPServer(ModelSQL, ModelView):
    'IMAP Server'
    __name__ = 'imap.server'
    name = fields.Char('Name', required=True)
    types = fields.Selection([
            ('generic', 'Generic'),
            ('google', 'Google'),
            ('outlook', 'Outlook'),
            ], 'Type', readonly=False, required=True)
    host = fields.Char('Server',
        states={
            'readonly': (Eval('state') != 'draft'),
            'required': True,
            'invisible': Bool(Eval('types') != 'generic'),
            }, depends=['state'])
    ssl = fields.Boolean('SSL',
        states={
            'readonly': (Eval('state') != 'draft'),
            'invisible': Bool(Eval('types') != 'generic'),
            }, depends=['state'])
    port = fields.Integer('Port',
        states={
            'readonly': (Eval('state') != 'draft'),
            'invisible': Bool(Eval('types') != 'generic'),
            'required': True,
            }, depends=['state'])
    folder = fields.Char('Folder', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            },
        help='The folder name where to read from on the server.')
    timeout = fields.Integer('Time Out', required=True,
        states={
            'readonly': (Eval('state') != 'draft'),
            },
        help=('Time to wait until connection is established. '
            'In seconds.'))
    criterion = fields.Char('Criterion', required=False,
        states={
            'readonly': (Eval('state') != 'draft'),
            'invisible': Bool(Eval('search_mode') != 'custom'),
            'required': Bool(Eval('search_mode') == 'custom')
            }, depends=['state', 'search_mode'])
    criterion_used = fields.Function(fields.Char('Criterion used'),
        'get_criterion_used')
    email = fields.Char('Email',
        states={
            'readonly': (Bool(Eval('state') != 'draft'
                or Eval('types') != 'generic')),
            }, depends=['state'],
        help='Default From (if active this option) and Reply Email')
    user = fields.Char('Username',
        states={
            'readonly': (Eval('state') != 'draft'),
            'required': Bool(Eval('types') == 'generic'),
            'invisible': Bool(Eval('types') != 'generic'),
            }, depends=['state'])
    password = fields.Char('Password',
        strip=False,
        states={
            'readonly': (Eval('state') != 'draft'),
            'required': Bool(Eval('types') == 'generic'),
            'invisible': Bool(Eval('types') != 'generic'),
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
    offset = fields.Integer('Days Offset',
        domain=[('offset', '>=', 1)],
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
    session_id = fields.Char('Session ID',
        states={
            'invisible': Bool(Eval('types') == 'generic'),
        })
    oauth_credentials = fields.Dict('account.statement.origin.information',
        "Oauth Credentials", readonly=True)

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
            'test': {},
            'draft': {
                'invisible': Eval('state') == 'draft',
            },
            'done': {
                'invisible': Eval('state') == 'done',
            },
            'google': {
                'invisible': Bool(Eval('types') != 'google'),
            },
            'outlook': {
                'invisible': Bool(Eval('types') != 'outlook'),
            }
        })

    @staticmethod
    def default_types():
        return 'generic'

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

    @fields.depends('ssl', 'types')
    def on_change_with_port(self):
        if not self.types or self.types == 'generic':
            return self.ssl and 993 or 143
        else:
            return 993

    @fields.depends('types')
    def on_change_with_host(self):
        if self.types == 'google':
            return 'imap.gmail.com'
        elif self.types == 'outlook':
            return 'imap.office365.com'
        else:
            return ''

    @fields.depends('types', 'ssl')
    def on_change_with_ssl(self):
        if self.types == 'generic':
            return self.ssl
        else:
            return True

    @fields.depends('email')
    def on_change_with_user(self):
        return self.email or ""

    def get_criterion_used(self, name=None):
        if self.search_mode == 'interval':
            if not self.last_retrieve_date:
                return 'ALL'
            offset = datetime.timedelta(days=self.offset)
            date_with_offset = self.last_retrieve_date - offset
            return '(SINCE "%s")' % date_with_offset.strftime(_IMAP_DATE_FORMAT)
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

    # FIXME ConcurrencyException not handled
    @classmethod
    @ModelView.button
    def google(cls, servers):
        if not PRODUCTION_ENV:
            logger.warning('Production mode is not enabled.')
            return

        for server in servers:
            if (not GOOGLE_CLIENT_SECRETS or not GOOGLE_SCOPES
                    or not GOOGLE_REDIRECT_URI
                    or server.oauth_credentials is not None):
                return

            # Even the GOOGLE_CLIENT_SECRETS has all the information, the scope
            # and redirect_uri are rquired.
            flow = Flow.from_client_config(json.loads(GOOGLE_CLIENT_SECRETS),
                scopes=GOOGLE_SCOPES, redirect_uri=GOOGLE_REDIRECT_URI)

            authorization_url, state = flow.authorization_url(
                # Enable offline access so that you can refresh an access token
                # without re-prompting the user for permission. Recommended for
                # web server apps.
                access_type='offline',
                include_granted_scopes='true')
            server.session_id = state
            server.save()

            return {
                'type': 'ir.action.url',
                'url': f'{authorization_url}',
                }

    @classmethod
    @ModelView.button
    def outlook(cls, servers):
        if not PRODUCTION_ENV:
            logger.warning('Production mode is not enabled.')
            return

        for server in servers:
            with open('ms_credentials.json', 'r') as f:
                json.load(f)
            base_url = OUTLOOK_URL
            #auth_url = f'{base_url}?client_id={credentials['CLIENT_ID']}&response_type=code&redirect_uri={credentials['REDIRECT_URI']}&response_mode=query&scope={credentials['SCOPE']}'
            server.session_id = 'microsoft-oauth'  # Temporal identifier FIXME Probable bug -> Si sale de la ventana de auth, que pasa?
            server.save()
            return {
                'type': 'ir.action.url',
                'url': f'{base_url}',
                }

    def google_refresh_token(self, credentials=None):
        if not credentials and not self.oauth_credentials:
            return
        creds = (Credentials(**self.oauth_credentials)
            if not credentials else credentials)
        if not creds or not creds.refresh_token:
            return
        creds.refresh(Request())
        # Even only change the token value, the other values are
        # uncommon changed, it's possible that Google chate them,
        # special the refresh_token. So save all again.
        self.oauth_credentials = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            }
        self.save()

    @classmethod
    def connect(cls, server, ssl_context=None, debug=0):
        if not PRODUCTION_ENV:
            logger.warning('Production mode is not enabled.')
            return

        imapper = cls.get_server(server.host, server.port, server.ssl,
            ssl_context, debug, server.timeout)
        user = None
        password = None
        auth = False
        if server.types == 'google':
            if server.oauth_credentials is None:
                raise UserError(gettext('imap.msg_oauth_missing'))
            else:
                # Check if credentials has expired and refresh and refresh if it's
                # necessary
                creds = Credentials(**server.oauth_credentials)
                # This is True if the credentials have a token and the token
                # is not expired.
                if not creds.valid:
                    server.google_refresh_token(creds)
                user = 'XOAUTH2'
                password = 'user={}\x01auth=Bearer {}\x01\x01'.format(
                    server.email, server.oauth_credentials['token'])
                auth = True
        elif server.types == 'outlook':
            pass
        else:
            user =  server.user
            password =  server.password

        if user and password:
            return cls.login(server, imapper, user, password, auth)
        return

    @classmethod
    def get_server(cls, host, port, ssl=False, ssl_context=None, debug=0,
            timeout=120):
        '''
        Obtain an IMAP opened connection
        '''
        server = None
        try:
            if ssl:
                server = IMAP4_SSL(host=str(host), port=int(port),
                    ssl_context=ssl_context, timeout=timeout)
            else:
                server = IMAP4(host=str(host), port=int(port), timeout=timeout)
            server.debug = debug

        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            raise UserError(gettext('imap.general_error', msg=e))

        return server

    @classmethod
    def login(cls, server, imapper, user, password, auth=False):
        '''
        Authenticates an imap connection
        '''
        try:
            if not auth:
                status, data = imapper.login(user, password)
            else:
                status, data = imapper.authenticate(user, lambda x: password)
        except IMAP4.error as e:
            status = 'KO'
            data = str(e)
            # For some reason the credentials return a True in 'valid' field,
            # but it's not true.
            if ('AUTHENTICATIONFAILED' in data
                    and server.types == 'google'):
                server.google_refresh_token()
                user = 'XOAUTH2'
                password = 'user={}\x01auth=Bearer {}\x01\x01'.format(
                    server.email, server.oauth_credentials['token'])
                try:
                    status, data = imapper.authenticate(user,
                        lambda x: password)
                except (IMAP4.error, IMAP4.abort, IMAP4.readonly,
                        socket.error) as e:
                    status = 'KO'
                    data = str(e)
        except (IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'KO'
            data = str(e)
        if status != 'OK':
            cls.logout(imapper)
            raise UserError(gettext('imap.login_error', user=user, msg=data))
        return imapper

    @classmethod
    def logout(cls, imapper):
        try:
            imapper.close()  # which also expunges the mailbox
            imapper.logout()
        except:
            pass

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
            self.logout(imapper)
            raise UserError(
                gettext('imap.select_error', folder=self.folder, msg=data))

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
            self.logout(imapper)
            raise UserError(
                gettext('imap.search_error',
                        criteria=self.criterion_used,
                        msg=data))
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
            self.logout(imapper)
            raise UserError(gettext('imap.fetch_error', email=emailid,
                                    msg=data))
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
            self.logout(imapper)
            raise UserError(gettext('imap.fetch_error', email=emailid,
                                    msg=data))

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
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            self.logout(imapper)
            raise UserError(gettext('imap.fetch_error', email=emailid,
                                    msg=data))

    def delete_email(self, imapper, emailid):
        '''
        Delete the email from the main folder deffined in the configuration
        server.
        '''
        try:
            status, data = imapper.store(emailid, '+FLAGS', '\\Deleted')
        except (IMAP4.error, IMAP4.abort, IMAP4.readonly, socket.error) as e:
            status = 'KO'
            data = e
        if status != 'OK':
            self.logout(imapper)
            raise UserError(gettext('imap.fetch_error', email=emailid,
                                    msg=data))

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


class OauthCredentials(DictSchemaMixin, ModelSQL, ModelView):
    "Oauth Credentials"
    __name__ = 'imap.server.oauth.credentials'
