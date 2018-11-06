=============
Imap Scenario
=============

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from proteus import Model
    >>> from trytond.tests.tools import activate_modules, set_user
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.imap.tests.test_imap import create_imap_server
    >>> today = datetime.date.today()
    >>> yesterday = today.replace(day=today.day - 1)


Install imap::

    >>> config = activate_modules('imap')

Create IMAP server::
    >>> server = create_imap_server(Model)
    >>> server.state = u'done'
    >>> server.save()
    >>> server.search_mode == u'unseen'
    True
    >>> server.criterion == 'UNSEEN'
    True
    >>> server.search_mode = u'interval'
    >>> server.last_retrieve_date == None
    True
    >>> server.criterion == u'ALL'
    True
    >>> server.last_retrieve_date = today
    >>> server.offset = 0
    >>> server.criterion == '(SINCE "%s")' % today.strftime('%d-%b-%Y')
    True
    >>> server.offset = 1
    >>> server.criterion == '(SINCE "%s")' % yesterday.strftime('%d-%b-%Y')
    True
    >>> server.offset = None
    >>> server.criterion == '(SINCE "%s")' % today.strftime('%d-%b-%Y')
    True
