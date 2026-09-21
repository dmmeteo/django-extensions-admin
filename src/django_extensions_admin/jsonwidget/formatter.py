"""Lossless JSON re-indentation.

The point of this module is what it does *not* do: it never turns JSON text into
Python objects and back. ``json.loads``/``json.dumps`` round-trips silently rewrite
number literals (``1.0E2`` -> ``100.0``), drop duplicate keys and can lose precision
for values that do not fit a float. Admin users edit *text*, so the editor re-indents
text: strings and numbers are copied byte for byte and only whitespace between tokens
is rewritten.

Scope of that guarantee: it covers what the widget renders and redisplays. It says
nothing about saving - a save goes through ``forms.JSONField`` and the database, whose
own ``json.loads``/``json.dumps`` semantics apply unchanged (see README).
"""

from __future__ import annotations

import re
from typing import NamedTuple

__all__ = ["JSONFormatError", "Token", "pretty_json_text", "tokenize"]

WHITESPACE = " \t\n\r"

# Strict RFC 8259 number. Anything else (NaN, Infinity, leading +, hex) is refused, and
# the caller falls back to leaving the text exactly as it is.
NUMBER_RE = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
LITERAL_RE = re.compile(r"true|false|null")

STRING = "string"
NUMBER = "number"
LITERAL = "literal"
PUNCT = "punct"


class JSONFormatError(ValueError):
    """The text is not JSON this module is willing to rewrite."""


class Token(NamedTuple):
    kind: str
    start: int
    end: int
    text: str


def tokenize(text: str) -> list[Token]:
    """Split JSON text into tokens, ignoring whitespace. Raises JSONFormatError."""
    tokens: list[Token] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in WHITESPACE:
            index += 1
            continue
        if char == '"':
            end = _scan_string(text, index)
            tokens.append(Token(STRING, index, end, text[index:end]))
            index = end
            continue
        if char in "{}[],:":
            tokens.append(Token(PUNCT, index, index + 1, char))
            index += 1
            continue
        match = NUMBER_RE.match(text, index)
        if match and match.end() > index:
            tokens.append(Token(NUMBER, index, match.end(), match.group()))
            index = match.end()
            continue
        match = LITERAL_RE.match(text, index)
        if match:
            tokens.append(Token(LITERAL, index, match.end(), match.group()))
            index = match.end()
            continue
        raise JSONFormatError(f"Unexpected character {char!r} at position {index}")
    return tokens


def _scan_string(text: str, start: int) -> int:
    index = start + 1
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == '"':
            return index + 1
        index += 1
    raise JSONFormatError(f"Unterminated string starting at position {start}")


class _Printer:
    def __init__(self, tokens: list[Token], indent: int) -> None:
        self.tokens = tokens
        self.indent = indent
        self.position = 0
        self.out: list[str] = []

    def peek(self) -> Token | None:
        return self.tokens[self.position] if self.position < len(self.tokens) else None

    def take(self) -> Token:
        token = self.peek()
        if token is None:
            raise JSONFormatError("Unexpected end of JSON input")
        self.position += 1
        return token

    def expect(self, literal: str) -> Token:
        token = self.take()
        if token.kind != PUNCT or token.text != literal:
            raise JSONFormatError(f"Expected {literal!r} at position {token.start}")
        return token

    def render(self) -> str:
        self.value(0)
        if self.peek() is not None:
            raise JSONFormatError(f"Trailing data at position {self.peek().start}")
        return "".join(self.out)

    def value(self, depth: int) -> None:
        token = self.take()
        if token.kind in (STRING, NUMBER, LITERAL):
            # Copied verbatim: this is the whole point of the module.
            self.out.append(token.text)
            return
        if token.text == "{":
            self.container(depth, "}", self.member)
            return
        if token.text == "[":
            self.container(depth, "]", self.value)
            return
        raise JSONFormatError(f"Unexpected {token.text!r} at position {token.start}")

    def container(self, depth: int, closing: str, item) -> None:
        opening = "{" if closing == "}" else "["
        nxt = self.peek()
        if nxt is not None and nxt.kind == PUNCT and nxt.text == closing:
            self.take()
            self.out.append(opening + closing)
            return
        self.out.append(opening + "\n")
        pad = " " * (self.indent * (depth + 1))
        while True:
            self.out.append(pad)
            item(depth + 1)
            nxt = self.take()
            if nxt.kind != PUNCT:
                raise JSONFormatError(f"Expected ',' or {closing!r} at position {nxt.start}")
            if nxt.text == ",":
                self.out.append(",\n")
                continue
            if nxt.text == closing:
                self.out.append("\n" + " " * (self.indent * depth) + closing)
                return
            raise JSONFormatError(f"Expected ',' or {closing!r} at position {nxt.start}")

    def member(self, depth: int) -> None:
        key = self.take()
        if key.kind != STRING:
            raise JSONFormatError(f"Object keys must be strings (position {key.start})")
        self.out.append(key.text)
        self.expect(":")
        self.out.append(": ")
        self.value(depth)


def pretty_json_text(text: str, indent: int = 2) -> str:
    """Re-indent JSON *text* without touching any string or number literal.

    Raises JSONFormatError when the text is not valid JSON.
    """
    tokens = tokenize(text)
    if not tokens:
        raise JSONFormatError("Empty JSON input")
    return _Printer(tokens, indent).render()
