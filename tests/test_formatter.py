"""The formatter's whole job is to change nothing except whitespace."""

import json

from django.test import SimpleTestCase

from django_extensions_admin.jsonwidget.formatter import JSONFormatError, pretty_json_text


class LosslessFormattingTests(SimpleTestCase):
    def assert_same_tokens(self, source, formatted):
        """Formatted text differs from the source only in whitespace between tokens."""
        from django_extensions_admin.jsonwidget.formatter import tokenize

        self.assertEqual(
            [(t.kind, t.text) for t in tokenize(source)],
            [(t.kind, t.text) for t in tokenize(formatted)],
        )

    def test_indents_compact_json(self):
        self.assertEqual(
            pretty_json_text('{"model": "abc", "tools": ["search"]}'),
            '{\n  "model": "abc",\n  "tools": [\n    "search"\n  ]\n}',
        )

    def test_large_integer_is_not_rounded(self):
        source = '{"id": 123456789012345678901234567890}'
        formatted = pretty_json_text(source)
        self.assertIn("123456789012345678901234567890", formatted)
        # json.loads/json.dumps would keep this one too, but JavaScript would not; the
        # point is that neither side ever re-serialises the literal.
        self.assert_same_tokens(source, formatted)

    def test_number_notation_survives(self):
        for literal in ("1.0E2", "-0.0", "1e-7", "0.30000000000000004", "1.000000000000000000001"):
            with self.subTest(literal=literal):
                formatted = pretty_json_text('{"n": ' + literal + "}")
                self.assertIn(literal, formatted)

    def test_duplicate_keys_are_kept(self):
        formatted = pretty_json_text('{"a": 1, "a": 2}')
        self.assertEqual(formatted.count('"a"'), 2)

    def test_key_order_is_kept(self):
        formatted = pretty_json_text('{"z": 1, "a": 2, "m": 3}')
        self.assertLess(formatted.index('"z"'), formatted.index('"a"'))
        self.assertLess(formatted.index('"a"'), formatted.index('"m"'))

    def test_unicode_is_left_exactly_as_it_arrives(self):
        self.assertIn("Персона", pretty_json_text('{"name": "Персона"}'))
        # An escaped sequence stays escaped rather than being silently rewritten.
        self.assertIn("\\u0041", pretty_json_text('{"name": "\\u0041"}'))

    def test_escapes_and_html_are_untouched(self):
        source = '{"html": "<script>alert(\\"x\\")</script>", "path": "a\\\\b"}'
        formatted = pretty_json_text(source)
        self.assert_same_tokens(source, formatted)
        self.assertEqual(json.loads(source), json.loads(formatted))

    def test_empty_containers(self):
        self.assertEqual(pretty_json_text('{"a": {}, "b": []}'), '{\n  "a": {},\n  "b": []\n}')

    def test_scalars(self):
        self.assertEqual(pretty_json_text("[1,2]"), "[\n  1,\n  2\n]")
        self.assertEqual(pretty_json_text('"plain"'), '"plain"')
        self.assertEqual(pretty_json_text("null"), "null")

    def test_nested_indent_setting(self):
        self.assertEqual(
            pretty_json_text('{"a":[1]}', indent=4), '{\n    "a": [\n        1\n    ]\n}'
        )

    def test_already_formatted_text_is_stable(self):
        once = pretty_json_text('{"a": [1, {"b": 2}]}')
        self.assertEqual(pretty_json_text(once), once)

    def test_refuses_invalid_json(self):
        for bad in ('{"a":}', "{a:1}", '{"a":1},', "NaN", "Infinity", "", "  ", "{'a': 1}", "[1,]"):
            with self.subTest(bad=bad), self.assertRaises(JSONFormatError):
                pretty_json_text(bad)

    def test_refuses_unterminated_string(self):
        with self.assertRaises(JSONFormatError):
            pretty_json_text('{"a": "unterminated}')

    def test_deeply_nested_input_does_not_hang(self):
        source = "[" * 200 + "1" + "]" * 200
        self.assertEqual(json.loads(pretty_json_text(source)), json.loads(source))
