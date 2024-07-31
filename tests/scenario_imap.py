import unittest

test = unittest.TestCase()
import datetime

from dateutil.relativedelta import relativedelta
from proteus import Model
from trytond.modules.imap.tests.test_module import create_imap_server
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        today = datetime.date.today()
        yesterday = today - relativedelta(days=1)

        # Install imap
        activate_modules('imap')

        # Create IMAP server
        server = create_imap_server(Model)
        server.state = 'done'
        server.save()
        test.assertEqual(server.search_mode, 'unseen', True)
        test.assertEqual(server.criterion_used, 'UNSEEN', True)
        server.search_mode = 'interval'
        server.save()
        test.assertEqual(server.last_retrieve_date, None, True)
        test.assertEqual(server.criterion_used, 'ALL', True)
        server.last_retrieve_date = today
        server.save()
        test.assertEqual(
            server.criterion_used == '(SINCE "%s")' %
            yesterday.strftime('%d-%b-%Y'), True)
