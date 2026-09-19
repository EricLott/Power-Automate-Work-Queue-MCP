"""Run a bounded synthetic capacity profile against the local simulator.

This is deliberately not a Dataverse, connector, model, throttling, or cost
benchmark. It records only the local simulator's observable behavior and
labels the result so it cannot be mistaken for a tenant capacity claim.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "src" / "simulator" / "bin" / "Release" / "net8.0" / "QueueFramework.Simulator.dll"
QUEUE = "capacity"
NATIVE_QUEUE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def validate_args(items, poll_interval):
    if not isinstance(items, int) or not 1 <= items <= 100:
        raise ValueError("ITEM_COUNT_OUT_OF_RANGE")
    if not isinstance(poll_interval, (int, float)) or not 0.05 <= poll_interval <= 5:
        raise ValueError("POLL_INTERVAL_OUT_OF_RANGE")


def command(process, operation, data=None, item_id=""):
    payload = {
        "Operation": operation,
        "QueueKey": QUEUE,
        "RequestId": str(uuid.uuid4()),
        "DataJson": json.dumps(data or {}, separators=(",", ":")),
        "ItemId": item_id,
        "AttemptId": "",
        "Generation": 0,
        "ExpectedVersion": 0,
    }
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        raise RuntimeError("SIMULATOR_NO_RESPONSE")
    result = json.loads(line)
    if result.get("Error"):
        raise RuntimeError(str(result["Error"]))
    return result


def policy():
    return {
        "NativeQueueId": NATIVE_QUEUE_ID,
        "Enabled": True,
        "MaxAttempts": 3,
        "LeaseSeconds": 10,
        "DeadlineSeconds": 60,
        "RetryBaseSeconds": 2,
        "RetryMaxSeconds": 10,
        "SafeEffects": True,
        "Contracts": ["mail.v1"],
        "Grants": {"local-developer": ["producer", "worker", "reader", "watchdog", "sender"]},
        "Destinations": ["operations"],
        "Retention": {"PayloadDays": 30, "ReceiptDays": 30, "AttemptDays": 90, "EvidenceDays": 365, "ErrorDays": 90},
    }


def contract():
    return {
        "Id": "mail.v1",
        "Dialect": "http://json-schema.org/draft-07/schema#",
        "Schema": {
            "type": "object",
            "required": ["subject", "senderAddress", "bodyText"],
            "additionalProperties": False,
            "properties": {
                "subject": {"type": "string", "maxLength": 1000},
                "senderAddress": {"type": "string", "maxLength": 320},
                "bodyText": {"type": "string", "maxLength": 50000},
            },
        },
    }


def envelope(index):
    return {
        "envelopeVersion": "1.0",
        "contract": "mail.v1",
        "correlationId": f"capacity-{index}",
        "deduplicationKey": f"capacity-{index}",
        "source": {"type": "synthetic", "profile": "local-capacity"},
        "payload": {
            "subject": f"Synthetic capacity item {index}",
            "senderAddress": "synthetic@example.invalid",
            "bodyText": "Synthetic local capacity profile; no mailbox content.",
        },
    }


def field(value, name, fallback=None):
    if isinstance(value, dict):
        return value.get(name, value.get(name[:1].upper() + name[1:], fallback))
    return fallback


def summarize(state, items, setup_seconds, enqueue_seconds, drain_seconds, harness_requests, storage_before, storage_after):
    rows = list((state.get("Rows") or state.get("rows") or {}).values())
    native = list((state.get("Native") or state.get("native") or {}).values())
    queue_native = [row for row in native if field(row, "Queue", "") == QUEUE]
    receipts = [row for row in rows if field(row, "Kind", "") == "command" and field(row, "Queue", "") == QUEUE]
    operations = []
    for row in receipts:
        try:
            body = json.loads(field(row, "Body", "{}"))
            operations.append(field(body, "Operation", ""))
        except (TypeError, json.JSONDecodeError):
            continue
    pending_events = 0
    for row in rows:
        if field(row, "Kind", "") != "event" or field(row, "Queue", "") != QUEUE:
            continue
        try:
            event = json.loads(field(row, "Body", "{}"))
        except (TypeError, json.JSONDecodeError):
            continue
        if field(event, "State", "") in {"Pending", "Sending"}:
            pending_events += 1
    statuses = {}
    for row in queue_native:
        status = field(row, "Status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "classification": "local-synthetic-capacity-profile",
        "environment": "local-simulation",
        "tenantImport": "not-run",
        "profile": {"queue": QUEUE, "itemsRequested": items, "queuePageLimit": 100, "maintenancePageLimit": 50, "pollIntervalSeconds": 0.2},
        "observations": {
            "setupSeconds": round(setup_seconds, 6),
            "enqueueSeconds": round(enqueue_seconds, 6),
            "enqueueMillisecondsPerItem": round(enqueue_seconds * 1000 / items, 3),
            "drainSeconds": round(drain_seconds, 6),
            "drainItemsPerSecond": round(items / drain_seconds, 3) if drain_seconds > 0 else None,
            "nativeStatusCounts": statuses,
            "harnessRequests": harness_requests,
            "durableCommandReceipts": len(receipts),
            "retryRequests": operations.count("RequestRetry"),
            "promptCalls": 0,
            "pendingSenderEvents": pending_events,
            "storageBytesBeforeDrain": storage_before,
            "storageBytesAfterDrain": storage_after,
            "storageGrowthBytes": storage_after - storage_before,
            "throttlingObserved": False,
        },
        "limits": {
            "localProfileMaximumItems": 100,
            "serviceThrottlingMeasured": False,
            "tenantThroughputClaim": False,
            "costClaim": False,
        },
        "limitations": [
            "The simulator uses a fixture worker and makes no Dataverse, mailbox, AI, connector, or service-throttling calls.",
            "Durable command receipts and harness requests are local observables, not a tenant API-request budget.",
            "Run a separately authorized tenant baseline/burst profile before publishing capacity, cost, or throttling limits.",
        ],
    }


def run_profile(items, poll_interval):
    validate_args(items, poll_interval)
    if not SIMULATOR.exists():
        raise RuntimeError("SIMULATOR_BUILD_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="qmcp-capacity-") as directory:
        state_path = Path(directory) / "state.json"
        environment = {**os.environ, "QMCP_SIM_STATE": str(state_path)}
        process = subprocess.Popen(["dotnet", str(SIMULATOR)], cwd=ROOT, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        worker = None
        requests = 0
        try:
            started = time.perf_counter()
            command(process, "RegisterQueue", policy()); requests += 1
            command(process, "RegisterContract", contract()); requests += 1
            setup_seconds = time.perf_counter() - started
            enqueue_started = time.perf_counter()
            for index in range(items):
                command(process, "Enqueue", envelope(index)); requests += 1
            enqueue_seconds = time.perf_counter() - enqueue_started
            state_before = state_path.stat().st_size
            worker = subprocess.Popen(["dotnet", str(SIMULATOR), "--worker", QUEUE], cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            drain_started = time.perf_counter()
            deadline = drain_started + max(15, items * 2)
            while time.perf_counter() < deadline:
                health = command(process, "GetQueueHealth"); requests += 1
                statuses = [field(item, "Status", "") for item in health.get("Items", health.get("items", []))]
                if len(statuses) >= items and all(status == "Processed" for status in statuses[:items]):
                    break
                time.sleep(poll_interval)
            else:
                raise RuntimeError("LOCAL_PROFILE_DRAIN_TIMEOUT")
            drain_seconds = time.perf_counter() - drain_started
            state_after = state_path.stat().st_size
            state = json.loads(state_path.read_text(encoding="utf-8"))
            return summarize(state, items, setup_seconds, enqueue_seconds, drain_seconds, requests, state_before, state_after)
        finally:
            if worker is not None:
                worker.kill()
                worker.wait(timeout=5)
            process.terminate()
            process.wait(timeout=5)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=int, default=25)
    parser.add_argument("--poll-interval", type=float, default=0.2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_profile(args.items, args.poll_interval)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            raise RuntimeError("OUTPUT_ALREADY_EXISTS")
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
