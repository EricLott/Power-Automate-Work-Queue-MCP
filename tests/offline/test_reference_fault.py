import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from generate_reference_fault import CASES, CLASSIFICATION, FIXED_OUTPUT, generate


class ReferenceFaultGeneratorTests(unittest.TestCase):
    def test_candidate_changes_only_normalize_inputs_and_quote_is_absent(self):
        with tempfile.TemporaryDirectory() as temp:
            out = generate(Path(temp) / "candidate", ROOT / "templates" / "flows" / "ProcessOne.json")
            candidate = json.loads((out / "ProcessOne-intent-fault.json").read_text())
            source = json.loads((ROOT / "templates" / "flows" / "ProcessOne.json").read_text())
            actions = candidate["properties"]["definition"]["actions"]["HasWork"]["actions"]["Business"]["actions"]["CreateIfAbsent"]["actions"]
            self.assertEqual(json.loads(actions["NormalizeExtraction"]["inputs"]), FIXED_OUTPUT)
            self.assertEqual(FIXED_OUTPUT["contact"], "guard@example.invalid")
            self.assertNotIn(FIXED_OUTPUT["intentEvidence"], CASES["cases"][0]["Input"]["payload"]["bodyText"])
            changed = []
            def walk(a, b, path=""):
                if isinstance(a, dict) and isinstance(b, dict):
                    for key in set(a) | set(b): walk(a.get(key), b.get(key), path + "/" + key)
                elif a != b: changed.append(path)
            walk(source, candidate)
            self.assertEqual([p for p in changed if p != "/properties/definition/actions/HasWork/actions/Business/actions/CreateIfAbsent/actions/NormalizeExtraction/inputs"], [])
            self.assertEqual(CLASSIFICATION, CASES["classification"])

    def test_existing_output_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "candidate"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("keep")
            with self.assertRaisesRegex(ValueError, "OUTPUT_DIRECTORY_EXISTS"):
                generate(output, ROOT / "templates" / "flows" / "ProcessOne.json")
            self.assertEqual("keep", sentinel.read_text())


if __name__ == "__main__":
    unittest.main()
