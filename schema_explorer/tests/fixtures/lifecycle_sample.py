# -*- coding: utf-8 -*-
"""Sample source text for tests/test_lifecycle.py to scan - not imported,
not a real model, just representative `write({'state': ...})` / attribute-
assignment patterns for the regex-based transition guesser to find."""


def confirm(self):
    self.write({'state': 'confirmed'})


def cancel(self):
    self.write({'state': 'cancelled', 'active': False})


def reset(self):
    self.state = "draft"
