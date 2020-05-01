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
    >>> yesterday = today - relativedelta(days=1)

Install imap::

    >>> config = activate_modules('imap')

Create IMAP server::
    >>> server = create_imap_server(Model)
    >>> server.state = u'done'
    >>> server.save()
    >>> server.search_mode == u'unseen'
    True
    >>> server.criterion_used == 'UNSEEN'
    True
    >>> server.search_mode = u'interval'
    >>> server.save()
    >>> server.last_retrieve_date == None
    True
    >>> server.criterion_used == u'ALL'
    True
    >>> server.last_retrieve_date = today
    >>> server.offset = 1
    >>> server.save()
    >>> server.criterion_used == '(SINCE "%s")' % yesterday.strftime('%d-%b-%Y')
    True
    >>> server.offset = None
    >>> server.save() # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    trytond.model.modelstorage.DomainValidationError: ...
    >>> server.offset = 0
    >>> server.save() # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    trytond.model.modelstorage.DomainValidationError: ...
