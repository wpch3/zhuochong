#!/usr/bin/env python3
"""Guard against labeling every generated form as Teen."""
import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import make_rig  # noqa: E402


class RigIdentityTest(unittest.TestCase):
    def test_existing_teen_id_remains_stable(self):
        self.assertEqual(make_rig.rig_model_id("小寻", "teen"), "小寻_teen")

    def test_chibi_id_uses_requested_form(self):
        self.assertEqual(make_rig.rig_model_id("小寻", "chibi"), "小寻_chibi")

    def test_other_form_ids_are_not_collapsed_to_teen(self):
        for form in ("loli", "adult"):
            with self.subTest(form=form):
                self.assertEqual(make_rig.rig_model_id("小寻", form), f"小寻_{form}")
        with self.assertRaisesRegex(ValueError, "form is required"):
            make_rig.rig_model_id("小寻", None)

    def test_generator_passes_cli_form_into_builder(self):
        source = (ROOT / "tools" / "make_rig.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "build"]
        self.assertTrue(any(
            keyword.arg == "form"
            and isinstance(keyword.value, ast.Attribute)
            and keyword.value.attr == "form"
            and isinstance(keyword.value.value, ast.Name)
            and keyword.value.value.id == "args"
            for call in calls for keyword in call.keywords
        ), "main() must pass args.form to build()")


if __name__ == "__main__":
    unittest.main(verbosity=2)
