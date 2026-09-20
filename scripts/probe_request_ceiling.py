"""Bounded read-only probe of the native custom-API request boundary.

The probe calls only GetQueueHealth on an explicitly allowlisted synthetic
queue. It varies the DataJson string size, records accepted/rejected
observations without retaining payloads, and never mutates Dataverse state.
The result is a single-tenant observation, not a general service limit.
"""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


DEFAULT_SIZES = (65536, 131072, 262144, 524288, 1048576)


def _write(path, report):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _data_json(size):
    if size < 32:
        raise ValueError("SIZE_TOO_SMALL")
    padding = "x" * max(0, size - len('{"padding":""}'))
    value = json.dumps({"padding": padding}, separators=(",", ":"))
    # Keep the recorded size exact even when the requested value is not a
    # boundary for the JSON wrapper.
    if len(value.encode("utf-8")) != size:
        padding += "x" * (size - len(value.encode("utf-8")))
        value = json.dumps({"padding": padding}, separators=(",", ":"))
    if len(value.encode("utf-8")) != size:
        raise ValueError("SIZE_CONSTRUCTION_FAILED")
    return value


def probe(binding, output_path, queue_key=None, sizes=DEFAULT_SIZES, runner=None):
    origin, expected = _validate_binding(binding)
    allowlist = binding.get("queueKeys")
    if not isinstance(allowlist, list) or not allowlist:
        raise ValueError("QUEUE_ALLOWLIST_REQUIRED")
    queue = queue_key or allowlist[0]
    if queue not in allowlist:
        raise ValueError("QUEUE_NOT_BOUND")
    if any(not isinstance(size, int) or size < 32 or size > 1048576 for size in sizes):
        raise ValueError("SIZE_RANGE_INVALID")

    command = _cli_command()
    run = runner or subprocess.run
    who = _cli_request(command, origin, "GET", "WhoAmI", runner=run)
    actual = str(uuid.UUID(str(who["OrganizationId"]))).lower()
    if actual != expected:
        raise ValueError("ENVIRONMENT_MISMATCH")

    observations = []
    for size in sizes:
        data = _data_json(size)
        body = {
            "QueueKey": queue,
            "RequestId": str(uuid.uuid4()),
            "DataJson": data,
        }
        try:
            result = _cli_request(command, origin, "POST", "qmcp_WQ_GetQueueHealth",
                                  body, solution="WQCore", runner=run)
            observations.append({
                "dataJsonBytes": size,
                "classification": "accepted",
                "outcome": result.get("Outcome"),
                "healthShapePresent": isinstance(result, dict) and "Outcome" in result,
            })
        except ValueError as error:
            observations.append({
                "dataJsonBytes": size,
                "classification": "rejected",
                "errorClass": str(error),
            })

    accepted = [row["dataJsonBytes"] for row in observations
                if row["classification"] == "accepted"]
    rejected = [row["dataJsonBytes"] for row in observations
                if row["classification"] == "rejected"]
    report = {
        "classification": "read-only-native-custom-api-request-ceiling-probe",
        "organizationId": expected,
        "environmentUrl": origin,
        "queueKey": queue,
        "observations": observations,
        "maxAcceptedDataJsonBytes": max(accepted) if accepted else None,
        "firstRejectedDataJsonBytes": min(rejected) if rejected else None,
        "writesPerformed": False,
        "limitations": [
            "The probe exercises only GetQueueHealth on one approved development queue.",
            "A CLI rejection is an observed boundary classification, not proof of which gateway layer enforced it.",
            "This does not establish clean-import activation timing, production compatibility, throughput, or cost.",
        ],
    }
    _write(output_path, report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--queue-key")
    parser.add_argument("--sizes", nargs="+", type=int, default=list(DEFAULT_SIZES))
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({
            "classification": "read-only-native-custom-api-request-ceiling-probe",
            "tenantCalls": False,
            "writesPerformed": False,
            "queueKey": args.queue_key,
            "sizes": args.sizes,
        }, indent=2))
        raise SystemExit(0)
    try:
        result = probe(json.loads(Path(args.binding).read_text(encoding="utf-8-sig")),
                       args.output, args.queue_key, tuple(args.sizes))
        print(json.dumps(result, indent=2))
    except (ValueError, KeyError, OSError, json.JSONDecodeError):
        raise SystemExit("NATIVE_REQUEST_CEILING_PROBE_FAILED")
