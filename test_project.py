import unittest
from project import analyze


class CompatibilityTests(unittest.TestCase):
    def test_numbers_widen_but_bound_can_tighten(self):
        result = analyze({"before":{"type":"integer"},"after":{"type":"number","minimum":2}})
        self.assertEqual(result["metrics"]["Narrowing"],1)
        self.assertEqual(result["rows"][0]["Impact"],"Compatible")

    def test_closed_optional_addition(self):
        old = {"type":"object","additionalProperties":False}
        self.assertEqual(analyze({"before":old,"after":dict(old,properties={"x":{"type":"string"}})})["metrics"]["Narrowing"],0)

    def test_open_object_addition_and_escaping(self):
        result = analyze({"before":{"type":"object"},"after":{"type":"object","properties":{"a/b~c":{"type":"number"}}}})
        self.assertEqual(result["rows"][0]["Pointer"],"/properties/a~1b~0c")
        self.assertEqual(result["metrics"]["Narrowing"],1)

    def test_unknown_constraint_is_not_ignored(self):
        with self.assertRaises(ValueError):
            analyze({"before":{"type":"string","pattern":"a+"},"after":{"type":"string"}})

    def test_array_constraint_and_implicit_zero(self):
        self.assertEqual(analyze({"before":{"type":"array"},"after":{"type":"array","minItems":0}})["rows"],[])
        self.assertEqual(analyze({"before":{"type":"array"},"after":{"type":"array","items":{"type":"string"}}})["metrics"]["Narrowing"],1)
