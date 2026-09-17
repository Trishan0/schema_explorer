# -*- coding: utf-8 -*-
"""Domain -> plain English, for company rules (section 8.2) and security
rules (section 8.3). Shared because both just render an ``ir.rule`` domain.

Record rule domains are stored as *source text*, not literal data - a
common one looks like ``"[('company_id', 'in', company_ids)]"`` where
``company_ids`` is a name only meaningful in Odoo's own rule-evaluation
context, not a literal. **This module never evaluates a domain** (PLAN.md,
section 8.2: "Never eval domains"). It parses the text with :mod:`ast` into
a syntax tree and only ever reads it - `ast.literal_eval` where the value
side happens to be a literal, `ast.unparse` (read-only, source text out) for
anything else - so a domain can never execute code, no matter how it was
written.

Translation is intentionally best-effort: patterns this module doesn't
recognise fall back to a literal rendering of the condition rather than
guessing. Callers always keep the raw domain text alongside the English
(PLAN.md, section 9.4 / R9): the English is a summary, never the source of
truth.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass


class DomainParseError(Exception):
    """Raised internally when the domain text isn't a well-formed domain
    list; callers should catch this and fall back to showing raw text."""


@dataclass(frozen=True)
class Condition:
    #: usually the field name, but Odoo also uses ``(1, '=', 1)`` /
    #: ``(1, '=', 0)`` as an always-true / always-false constant domain -
    #: so this can be an int too.
    field: 'str | int'
    operator: str
    value_text: str
    #: the value, only when it was a plain literal (numbers/strings/lists/
    #: booleans/None) - anything else (a name, attribute access, a call)
    #: stays ``NO_LITERAL`` and only ``value_text`` (the source) is used.
    value_literal: object
    has_literal: bool


_LOGICAL_OPS = ('&', '|', '!')

_KNOWN_VALUE_PHRASES = {
    'company_ids': 'the companies selected in the company switcher',
    'allowed_company_ids': 'the companies selected in the company switcher',
    'uid': 'the current user',
    'user.id': 'the current user',
}

_OPERATOR_PHRASES = {
    '=': 'is',
    '!=': 'is not',
    'in': 'is one of',
    'not in': 'is not one of',
    '>': 'is greater than',
    '<': 'is less than',
    '>=': 'is at least',
    '<=': 'is at most',
    'like': 'contains',
    'ilike': 'contains',
    'not like': 'does not contain',
    'not ilike': 'does not contain',
    '=like': 'matches the pattern',
    '=ilike': 'matches the pattern',
    'child_of': 'is a child of',
    'parent_of': 'is a parent of',
}


def _leaf_from_ast(node: ast.AST) -> Condition:
    """Build a :class:`Condition` from one domain leaf's AST (a 2- or
    3-element tuple/list: ``(field, operator, value)``)."""
    if not isinstance(node, (ast.Tuple, ast.List)) or len(node.elts) != 3:
        raise DomainParseError(f'not a 3-element leaf: {ast.dump(node)}')
    field_node, op_node, value_node = node.elts
    try:
        field = ast.literal_eval(field_node)
        operator = ast.literal_eval(op_node)
    except (ValueError, SyntaxError) as exc:
        raise DomainParseError('field/operator must be literals') from exc
    if not isinstance(field, (str, int)) or isinstance(field, bool) or not isinstance(operator, str):
        raise DomainParseError('field must be a string or int, operator a string')

    try:
        value_literal = ast.literal_eval(value_node)
        has_literal = True
    except (ValueError, SyntaxError, TypeError):
        value_literal = None
        has_literal = False
    value_text = ast.unparse(value_node)
    return Condition(field, operator, value_text, value_literal, has_literal)


def _flatten(list_node: ast.AST) -> list:
    if not isinstance(list_node, (ast.List, ast.Tuple)):
        raise DomainParseError('domain is not a list')
    tokens = []
    for elt in list_node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value in _LOGICAL_OPS:
            tokens.append(elt.value)
        else:
            tokens.append(_leaf_from_ast(elt))
    return tokens


def _parse_prefix(it):
    token = next(it)
    if token == '!':
        return ('not', _parse_prefix(it))
    if token in ('&', '|'):
        left = _parse_prefix(it)
        right = _parse_prefix(it)
        return (token, left, right)
    return ('leaf', token)


def _build_tree(tokens: list):
    it = iter(tokens)
    trees = []
    try:
        while True:
            trees.append(_parse_prefix(it))
    except StopIteration:
        pass
    if not trees:
        raise DomainParseError('empty domain')
    result = trees[0]
    for t in trees[1:]:
        # a bare list of leaves with no explicit operator is an implicit AND
        result = ('&', result, t)
    return result


def parse_domain(domain_text: str):
    """Parse ``domain_text`` into a boolean tree of :class:`Condition`
    leaves, or return ``None`` if it can't be parsed. Never evaluates
    anything - only ``ast.parse``/``ast.literal_eval``/``ast.unparse``."""
    if not domain_text or not domain_text.strip():
        return None
    try:
        parsed = ast.parse(domain_text.strip(), mode='eval')
        tokens = _flatten(parsed.body)
        return _build_tree(tokens)
    except (SyntaxError, DomainParseError, RecursionError, ValueError):
        return None


def _value_phrase(condition: Condition) -> str:
    text = condition.value_text
    if text in _KNOWN_VALUE_PHRASES:
        return _KNOWN_VALUE_PHRASES[text]
    if text.startswith('user.'):
        rest = text[len('user.'):]
        # crude but readable: user.company_id -> "the current user's company id"
        humanized = rest.replace('_id', '').replace('_ids', '').replace('_', ' ')
        return f"the current user's {humanized}"
    if condition.has_literal:
        if condition.value_literal is False or condition.value_literal is None:
            return 'not set'
        if condition.value_literal is True:
            return 'set'
        if isinstance(condition.value_literal, (list, tuple)):
            return '[' + ', '.join(str(v) for v in condition.value_literal) + ']'
        return str(condition.value_literal)
    return text


_COMPARISON_FUNCS = {
    '=': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
}


def _condition_english(condition: Condition) -> str:
    # Odoo's own idiom for an always-true/always-false domain leaf, e.g.
    # ``(1, '=', 1)`` or ``(1, '=', 0)``. Both sides are already-literal
    # constants here (via ast.literal_eval, never the record itself), so
    # folding them with a plain Python comparison is not an "eval" in the
    # sense PLAN.md warns against - nothing record-dependent is touched.
    if isinstance(condition.field, int) and condition.has_literal:
        fold = _COMPARISON_FUNCS.get(condition.operator)
        if fold is not None:
            try:
                return 'always true' if fold(condition.field, condition.value_literal) else 'always false'
            except TypeError:
                pass

    op_phrase = _OPERATOR_PHRASES.get(condition.operator, condition.operator)
    value_phrase = _value_phrase(condition)
    if condition.operator == '=' and condition.has_literal and condition.value_literal is False:
        return f'{condition.field} is not set'
    return f'{condition.field} {op_phrase} {value_phrase}'


def _tree_english(tree) -> str:
    kind = tree[0]
    if kind == 'leaf':
        return _condition_english(tree[1])
    if kind == 'not':
        return f'NOT ({_tree_english(tree[1])})'
    if kind == '&':
        return f'({_tree_english(tree[1])}) AND ({_tree_english(tree[2])})'
    if kind == '|':
        return f'({_tree_english(tree[1])}) OR ({_tree_english(tree[2])})'
    raise DomainParseError(f'unknown tree node kind: {kind!r}')  # pragma: no cover


def domain_to_english(domain_text: str) -> str | None:
    """Best-effort plain-English summary of a record-rule domain.

    Returns ``None`` when the domain can't be parsed at all (the caller
    should then just show ``domain_text`` raw). A domain that parses but
    contains an unrecognised value expression still renders - unfamiliar
    parts fall back to their literal source text rather than blocking the
    whole sentence.
    """
    tree = parse_domain(domain_text)
    if tree is None:
        return None
    try:
        return _tree_english(tree)
    except DomainParseError:
        return None
