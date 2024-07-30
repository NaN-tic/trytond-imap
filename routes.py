import json
import os  # TODO Quitar para eliminar el permiso temporal de NO HTTPS

import googleapiclient.discovery
import googleapiclient.errors
import requests

from trytond.protocols.wrappers import Response, with_pool, with_transaction
from trytond.transaction import Transaction
from trytond.wsgi import app

from . import imap

@app.route('/<database_name>/oauth', methods={'GET'})
@with_pool
@with_transaction(readonly=False, context={'_skip_warnings': True})
def google(request, pool):

    Imap = pool.get('imap.server')
    record, = Imap.search([('session_id', '=', request.args['state'])])

    imap.google_oauth.fetch_token(authorization_response=request.url)

    if not record or record.session_id != request.args['state']:
        return Response('<h1>Bad Auth</h1>', 400, content_type='text/html') # FIXME: Demasiado cutre

    key = imap.google_oauth.credentials
    service = googleapiclient.discovery.build('oauth2', 'v2', credentials=key)

    try:
        user = service.userinfo().get().execute()
        email = user['email']
    except googleapiclient.errors.HttpError as e:
        return Response(f'<h1>Error obtaining info</h1><p>{e}</p>', # FIXME: Demasiado cutre
                        500,
                        content_type='text/html')

    record.email = email
    record.token = key.token
    record.token_refresh = key.refresh_token
    record.session_id = None
    record.save()

    return Response(f'<h1>Good Auth</h1>', 200, content_type='text/html') # FIXME: Demasiado cutre


@app.route('/<database_name>/oauth/outlook', methods={'GET'})
@with_pool
@with_transaction(readonly=False, context={'_skip_warnings': True})
def outlook(request, pool):

    Imap = pool.get('imap.server')
    record, = Imap.search([('session_id', '=', 'microsoft-auth')])

    if not record:
        return Response('<h1>Bad Auth</h1>', 400, content_type='text/html')
    else:
        record.session_id = None
        record.save()

    code = request.args.get('code')

    with open('ms_credentials.json', 'r') as f:
        credentials = json.load(f)

    data = {
        'CLIENT_ID': credentials['CLIENT_ID'], 'CLIENT_SECRET':
        credentials['CLIENT_SECRET'], 'GRANT_TYPE': 'AUTHORIZATION_CODE', 'CODE':
        code, 'REDIRECT_URI': credentials['REDIRECT_URI'], 'SCOPE':
        credentials['SCOPES']
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
        return Response(f'<h1>Error obtaining info</h1><p>{e}</p>',
                        500,
                        content_type='text/html')

    email = user_info.get('mail')

    record.email = email
    record.token = token
    record.save()

    return Response(f'<h1>Good Auth</h1>', 200, content_type='text/html')
