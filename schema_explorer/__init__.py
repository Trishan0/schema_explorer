# -*- coding: utf-8 -*-
# The core pipeline (``core/``) is deliberately import-free of any Odoo
# web/http machinery so it can run under ``odoo-bin shell`` without the
# module being installed (PLAN.md, decision D1) - it is never imported here.
from . import models
