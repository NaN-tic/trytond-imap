# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool

from . import imap, routes

__all__ = ['register', 'routes']


def register():
    Pool.register(imap.IMAPServer, module='imap', type_='model')
