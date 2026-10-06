# SPDX-License-Identifier: GPL-3.0-or-later
"""Read and write the KiCad/CADSTAR s-expression subset used by this project."""
import json
import re


class Atom(str):
    """An unquoted s-expression token."""


def parse(text):
    """Parse a single balanced s-expression, preserving quoted strings."""
    stack = [[]]
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text):
        if token == '(':
            child = []
            stack[-1].append(child)
            stack.append(child)
        elif token == ')':
            if len(stack) == 1:
                raise ValueError('Unmatched closing bracket')
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else Atom(token))
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError('Unbalanced or multiple roots')
    return stack[0][0]


def dump(node, indent=0):
    """Serialize without changing token values."""
    if isinstance(node, Atom):
        return str(node)
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    if not isinstance(node, list):
        return str(node)
    if not any(isinstance(x, list) for x in node):
        return '(' + ' '.join(dump(x) for x in node) + ')'
    parts = []
    for x in node:
        if isinstance(x, list):
            parts.append('\n' + '  ' * (indent + 1) + dump(x, indent + 1))
        else:
            parts.append((' ' if parts else '') + dump(x))
    return '(' + ''.join(parts) + ')'


def children(node, tag):
    """Return direct children with a specified tag."""
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]


def child(node, tag):
    """Return one required direct child."""
    values = children(node, tag)
    if len(values) != 1:
        raise ValueError(f'{tag}: expected one child, found {len(values)}')
    return values[0]


def walk(node):
    """Visit every nested list."""
    if isinstance(node, list):
        yield node
        for x in node:
            yield from walk(x)
