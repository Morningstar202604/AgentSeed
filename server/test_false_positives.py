"""Regression tests for the false-positive classes that made verify_code and
the hook unusable on real code. Each test pins a code shape that a 0.3.x
review flagged as a wrongful suspect, plus the real-hallucination catch that
must survive the fix."""

import unittest

from guard_engine import detect_undefined_symbols


class TestTypeScriptArrayDestructuring(unittest.TestCase):
    REACT = (
        'import { useState } from "react";\n'
        "export function Counter({ initial }: { initial: number }) {\n"
        "  const [count, setCount] = useState(initial);\n"
        "  const inc = () => setCount((c) => c + 1);\n"
        "  return inc();\n"
        "}\n"
    )

    def test_hook_setters_are_not_suspects(self):
        res = detect_undefined_symbols(self.REACT, "typescript")
        self.assertEqual(res["suspects"], [])

    def test_unimported_hook_call_is_still_caught(self):
        src = "function C() {\n  const [n, setN] = useState(0);\n  return setN(n);\n}\n"
        res = detect_undefined_symbols(src, "typescript")
        self.assertIn("useState", res["suspects"])

    def test_rest_and_default_elements_are_collected(self):
        # only CALL positions are checked: `list`/`pair` as initializers are
        # loads (never flagged), `run` is a bare call with no definition
        src = (
            "const [head, ...rest] = list;\n"
            "const [a = 1, b = 2] = pair;\n"
            "run(head, rest, a, b);\n"
        )
        res = detect_undefined_symbols(src, "typescript")
        self.assertEqual(res["suspects"], ["run"])


class TestRubyLocalsAndBlockParams(unittest.TestCase):
    REALISTIC = (
        "def total(items)\n"
        "  sum = 0\n"
        "  items.each { |i| sum += i }\n"
        "  average = sum / items.size\n"
        "  puts average\n"
        "end\n"
    )

    def test_locals_are_not_suspects(self):
        res = detect_undefined_symbols(self.REALISTIC, "ruby")
        self.assertEqual(res["suspects"], [])

    def test_undefined_method_call_is_still_caught(self):
        src = "def run\n  sum = 0\n  authenticate\n  sum\nend\n"
        res = detect_undefined_symbols(src, "ruby")
        self.assertEqual(res["suspects"], ["authenticate"])

    def test_augmented_and_conditional_assignment_are_collected(self):
        src = "cache ||= load_cache()\ncount += 1\nputs cache, count\n"
        res = detect_undefined_symbols(src, "ruby")
        self.assertEqual(res["suspects"], ["load_cache"])


class TestPythonStarImport(unittest.TestCase):
    def test_wildcard_import_disables_detection_honestly(self):
        src = "from os.path import *\nfrom pathlib import Path\np = join('a', 'b')\n"
        res = detect_undefined_symbols(src, "python")
        self.assertEqual(res["suspects"], [])
        self.assertIn("Wildcard import", res["note"])

    def test_no_star_import_detection_unchanged(self):
        src = "import os\ndef f():\n    return magic_unknown()\n"
        res = detect_undefined_symbols(src, "python")
        self.assertIn("magic_unknown", res["suspects"])


if __name__ == "__main__":
    unittest.main()
