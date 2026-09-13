"""Generate a local ProcessOne intent-validator fault-injection candidate.

This performs no tenant/API calls, credentials lookup, deployment, or flow
activation. The candidate remains a local artifact for an explicitly reviewed
installed-validator experiment; it is not AI-quality evidence.
"""
import argparse
import copy
import json
from pathlib import Path


CLASSIFICATION = "installed-validator-fault-injection-not-ai-quality"
FIXED_OUTPUT = {
    "contact": "guard@example.invalid",
    "category": "service",
    "summary": "Synthetic deliberately fabricated extraction for validator testing.",
    "intentEvidence": "Please repair the spaceship.",
    "intentSignal": "explicit-request",
}
CASES = {
    "promptVersion": "mail-extraction-v1.2",
    "classification": CLASSIFICATION,
    "cases": [{
        "Id": "fabricated-intent-quote",
        "Input": {"envelopeVersion": "1.0", "contract": "mail.v1", "correlationId": "intent-guard-fault", "deduplicationKey": "intent-guard-fault", "source": {"kind": "synthetic"}, "payload": {"subject": "Printer service", "senderAddress": "guard@example.invalid", "bodyText": "Please restore the office printer."}},
        "Expected": {}, "ExpectedOutcome": "Exception", "ExpectedAttemptCount": 1, "ExpectedErrorCode": "VALIDATEINTENT_FAILED",
    }],
}


def generate(output_dir, source):
    output = Path(output_dir)
    if output.exists():
        raise ValueError("OUTPUT_DIRECTORY_EXISTS")
    original = json.loads(Path(source).read_text(encoding="utf-8"))
    candidate = copy.deepcopy(original)
    actions = candidate["properties"]["definition"]["actions"]["HasWork"]["actions"]["Business"]["actions"]["CreateIfAbsent"]["actions"]
    actions["NormalizeExtraction"]["inputs"] = json.dumps(FIXED_OUTPUT)
    output.mkdir(parents=True)
    (output / "ProcessOne-intent-fault.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    (output / "intent-fault-cases.json").write_text(json.dumps(CASES, indent=2), encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1] / "templates" / "flows" / "ProcessOne.json"))
    args = parser.parse_args(argv)
    print(json.dumps({"output": str(generate(args.output_dir, args.source)), "classification": CLASSIFICATION}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(str(error))
