import json
import logging
import requests

from trytond.protocols.wrappers import Response, with_pool, with_transaction
from trytond.wsgi import app

from .imap import (Flow, GOOGLE_CLIENT_SECRETS, GOOGLE_SCOPES,
    GOOGLE_REDIRECT_URI)

logger = logging.getLogger(__name__)


@app.route('/<database_name>/googleoauth', methods={'GET'})
@with_pool
@with_transaction(readonly=False, context={'_skip_warnings': True})
def google(request, pool):
    Imap = pool.get('imap.server')

    if not request or not request.args.get('state'):
        # TODO: Improve the return.
        return Response('<h1>Bad Auth</h1>', 400, content_type='text/html')
    state = request.args['state']
    imaps = Imap.search([
            ('session_id', '=', state),
            ], limit=1)
    if not imaps:
        # TODO: Improve the return.
        return Response('<h1>Error obtaining IMAP server from session</h1>',
            500, content_type='text/html')
    imap, = imaps

    flow = Flow.from_client_config(json.loads(GOOGLE_CLIENT_SECRETS),
        scopes=GOOGLE_SCOPES, state=state, redirect_uri=GOOGLE_REDIRECT_URI)
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    imap.oauth_credentials = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes,
        }
    imap.session_id = None
    imap.save()

    # TODO: Improve the return.
    return Response('<h1>Good Auth</h1>'
        '<h3>Now, you can close this windows</h3>', 200,
        content_type='text/html')


@app.route('/<database_name>/outlookoauth', methods={'GET'})
@with_pool
@with_transaction(readonly=False, context={'_skip_warnings': True})
def outlook(request, pool):
    Imap = pool.get('imap.server')

    imaps = Imap.search([
            ('session_id', '=', 'microsoft-oauth')
            ], limit=1)
    if not imaps:
        # TODO: Improve the return.
        return Response('<h1>Error obtaining IMAP server from session</h1>',
            500, content_type='text/html')
    imap, = imaps
    imap.session_id = None
    imap.save()

    code = request.args.get('code')

    with open('ms_credentials.json', 'r') as f:
        credentials = json.load(f)

    data = {
        'CLIENT_ID': credentials['CLIENT_ID'],
        'CLIENT_SECRET': credentials['CLIENT_SECRET'],
        'GRANT_TYPE': 'AUTHORIZATION_CODE',
        'CODE': code,
        'REDIRECT_URI': credentials['REDIRECT_URI'],
        'SCOPE': credentials['SCOPES']
        }

    response = requests.post(credentials['TOKEN_URL'], data=data)
    token = response.json()
    token = token['access_token']

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
        }
    response = requests.get('https://graph.microsoft.com/v1.0/me/messages',
        headers=headers)

    if response.status_code == 200:
        user_info = response.json()
    else:
        logger.error(f'Error {response.status_code} obtaining info:\n'
            '{response.content}')
        return Response('<h1>Error obtaining info</h1>', 500,
            content_type='text/html')

    email = user_info.get('mail')

    imap.email = email
    imap.token = token
    imap.save()

    # TODO: Improve the return.
    return Response('<h1>Good Auth</h1>'
        '<h3>Now, you can close this windows</h3>', 200,
        content_type='text/html')
