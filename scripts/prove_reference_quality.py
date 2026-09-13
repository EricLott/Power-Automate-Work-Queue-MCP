"""Opt-in quality proof for installed synthetic reference flows.

Default mode validates inputs without network calls. ``--execute`` starts one
test run and persists its ID; ``--observe`` reads that run later. The script
never calls AdvanceTestRun or changes flow activation.
"""
import argparse
import hashlib
import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from bootstrap_tenant import _cli_command, _cli_request
from probe_tenant_metadata import _validate_binding


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def intent_matches(fields, body):
    quote = fields.get("intentEvidence")
    if not isinstance(quote, str) or not 1 <= len(quote) <= 500 or quote.strip() not in body:
        return False
    normalized = quote.strip().lower()
    if fields.get("intentSignal") == "explicit-request" and fields.get("category") == "service":
        return normalized.startswith(("please ", "i request ", "we request ", "i need ", "we need ", "can you ", "could you ", "would you "))
    return fields.get("intentSignal") == "explicit-question" and fields.get("category") == "question" and normalized.endswith("?") and normalized.startswith(tuple(word + " " for word in ("what", "when", "where", "why", "how", "which", "who", "is", "are", "do", "does", "can", "could")))


def validate(binding, ledger, cases):
    origin, organization = _validate_binding(binding)
    queue = ledger.get("queueKey")
    if not isinstance(queue, str) or not queue.startswith("qmcp-proof-"):
        raise ValueError("SYNTHETIC_QUEUE_REQUIRED")
    if queue not in binding.get("queueKeys", []):
        raise ValueError("SYNTHETIC_QUEUE_NOT_BOUND")
    if not isinstance(cases, list) or not cases or len(cases) > 20:
        raise ValueError("FIXTURE_CASES_INVALID")
    ids = [case.get("Id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(set(ids)) != len(ids) or any(not isinstance(i, str) or not i for i in ids):
        raise ValueError("FIXTURE_CASE_IDS_INVALID")
    if any(case.get("Repetitions", 1) != 1 for case in cases):
        raise ValueError("FIXTURE_REPETITIONS_UNSUPPORTED")
    for case in cases:
        envelope = case.get("Input", {})
        if not isinstance(envelope, dict) or envelope.get("source", {}).get("kind") != "synthetic":
            raise ValueError("SYNTHETIC_INPUT_REQUIRED")
        if case.get("ExpectedOutcome", "Processed") not in {"Processed", "Exception"}:
            raise ValueError("EXPECTED_OUTCOME_INVALID")
    try:
        queue_id = str(uuid.UUID(ledger["queue"]))
    except (KeyError, ValueError, TypeError):
        raise ValueError("NATIVE_QUEUE_ID_REQUIRED")
    return origin, organization, queue, queue_id


def load_cases(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return value.get("cases") if isinstance(value, dict) else value


def write(path, evidence):
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")


def observe(call, evidence, cases, run_id, queue, queue_id):
    evidence["complete"] = False
    evidence["observedAtUtc"] = datetime.now(timezone.utc).isoformat()
    response = call("POST", "qmcp_WQ_GetTestRun", {"QueueKey": queue, "ItemId": run_id, "RequestId": str(uuid.uuid4()), "DataJson": "{}"})
    run = json.loads(response.get("ResultJson", "{}"))
    results = run.get("Results")
    if not isinstance(results, list):
        raise ValueError("RUN_RESULTS_INVALID")
    by_case = {case["Id"]: case for case in cases}
    if len(results) != len(cases) or {r.get("CaseId") for r in results} != set(by_case):
        raise ValueError("RUN_CASE_SET_MISMATCH")
    evidence["run"] = {"state": run.get("State"), "resultCount": len(results)}
    checks = []
    evidence["checks"] = checks
    for result in results:
        case = by_case[result["CaseId"]]
        native_id = result.get("ItemId")
        if not isinstance(native_id, str) or not native_id:
            raise ValueError("NATIVE_ITEM_ID_MISSING")
        native = call("GET", "workqueueitems(" + native_id + ")?$select=workqueueitemid,uniqueidbyqueue,_workqueueid_value,statecode,statuscode,input")
        try:
            envelope = json.loads(native["input"])
            payload = envelope["payload"]
            dedup = digest(run_id + "|" + case["Id"] + "|0")
            native_key = digest(queue + "|" + dedup)
            content_hash = digest(canonical({"contract": envelope["contract"], "source": envelope["source"], "payload": payload}))
            expected_envelope = json.loads(json.dumps(case["Input"]))
            expected_envelope["deduplicationKey"] = dedup
            if envelope != expected_envelope:
                raise ValueError("NATIVE_INPUT_MISMATCH")
        except (KeyError, TypeError, ValueError):
            raise ValueError("NATIVE_INPUT_INVALID")
        expected_state = 2 if case.get("ExpectedOutcome", "Processed") == "Processed" else 4
        check = {"caseId": case["Id"], "itemId": native_id, "nativeUniqueId": native.get("uniqueidbyqueue"), "nativeState": native.get("statecode"), "resultState": result.get("State"), "assertionEvidence": result.get("Evidence", {}), "errorCodeMatch": not case.get("ExpectedErrorCode") or result.get("Evidence", {}).get("errorCode") == case["ExpectedErrorCode"], "nativeQueueMatch": str(native.get("_workqueueid_value", "")).lower() == queue_id.lower(), "nativeKeyMatch": native.get("uniqueidbyqueue") == native_key, "nativeOutcomeMatch": native.get("statecode") == expected_state}
        rows = call("GET", "qmcp_emailrequests?$select=qmcp_emailrequestid,qmcp_key,qmcp_queuekey,qmcp_document&$filter=qmcp_key eq '" + native_key + "'&$top=2").get("value")
        if not isinstance(rows, list):
            raise ValueError("BUSINESS_QUERY_INVALID")
        if case.get("ExpectedOutcome", "Processed") == "Exception":
            check["businessAbsent"] = len(rows) == 0
            check["businessRecordCount"] = len(rows)
            check["unexpectedBusinessRecordIds"] = [row.get("qmcp_emailrequestid") for row in rows]
        else:
            if run.get("State") not in {"Passed", "Failed", "Inconclusive", "Cancelled"} and result.get("State") == "Pending" and len(rows) == 0:
                check["businessPending"] = True
                checks.append(check)
                continue
            check["businessRecordCount"] = len(rows)
            if len(rows) != 1:
                check["businessEvidenceValid"] = False
                checks.append(check)
                continue
            row = rows[0]
            if row.get("qmcp_queuekey") != queue:
                raise ValueError("BUSINESS_QUEUE_MISMATCH")
            try:
                document = json.loads(row["qmcp_document"])
                fields = document["fields"]
            except (KeyError, TypeError, ValueError):
                raise ValueError("BUSINESS_DOCUMENT_INVALID")
            check.update({"businessRecordId": row.get("qmcp_emailrequestid"), "fields": fields, "promptVersion": document.get("promptVersion"), "modelVersion": document.get("modelVersion"), "predictionId": document.get("predictionId"), "promptModelId": document.get("promptModelId"), "runMatch": document.get("testRun") == run_id, "contentHashMatch": document.get("contentHash") == content_hash, "sourceKeyMatch": document.get("sourceKey") == digest(dedup), "expectedFieldsMatch": all(fields.get(k) == v for k, v in case.get("Expected", {}).items()), "promptProvenancePresent": bool(document.get("promptVersion") == evidence.get("promptVersion", "mail-extraction-v1.1") and document.get("promptModelId")), "intentEvidenceMatch": evidence.get("promptVersion", "mail-extraction-v1.1") in {"mail-extraction-v1", "mail-extraction-v1.1"} or intent_matches(fields, payload["bodyText"]), "summaryReviewRequired": True})
        checks.append(check)
    evidence["checks"] = checks
    evidence["terminal"] = run.get("State") in {"Passed", "Failed", "Inconclusive", "Cancelled"}
    evidence["complete"] = run.get("State") == "Passed" and all(c.get("resultState") == "Passed" and c.get("errorCodeMatch") and c.get("nativeQueueMatch") and c.get("nativeKeyMatch") and c.get("nativeOutcomeMatch") and (c.get("businessAbsent") is True if by_case[c["caseId"]].get("ExpectedOutcome") == "Exception" else c.get("runMatch") and c.get("contentHashMatch") and c.get("sourceKeyMatch") and c.get("expectedFieldsMatch") and c.get("intentEvidenceMatch") and c.get("promptProvenancePresent")) for c in checks)
    return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True)
    parser.add_argument("--fixture-ledger", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--observe", action="store_true")
    args = parser.parse_args(argv)
    binding = json.loads(Path(args.binding).read_text(encoding="utf-8-sig"))
    ledger = json.loads(Path(args.fixture_ledger).read_text(encoding="utf-8-sig"))
    cases = load_cases(args.cases)
    manifest = json.loads(Path(args.cases).read_text(encoding="utf-8-sig"))
    prompt_version = manifest.get("promptVersion", "mail-extraction-v1.1") if isinstance(manifest, dict) else "mail-extraction-v1.1"
    origin, organization, queue, queue_id = validate(binding, ledger, cases)
    fixture_hash = digest(canonical(cases))
    output = Path(args.output)
    if not args.execute and not args.observe:
        print(json.dumps({"ready": True, "writes": False, "tenantCalls": False, "queueKey": queue}))
        return
    if args.observe:
        if not output.is_file():
            raise ValueError("OBSERVATION_EVIDENCE_REQUIRED")
        evidence = json.loads(output.read_text(encoding="utf-8"))
        if evidence.get("organizationId") != organization or evidence.get("queueKey") != queue or evidence.get("promptVersion") != prompt_version or evidence.get("fixtureHash") != fixture_hash or not evidence.get("runId"):
            raise ValueError("OBSERVATION_BINDING_MISMATCH")
    else:
        if output.exists():
            raise ValueError("EVIDENCE_EXISTS")
        proof = str(uuid.uuid4())
        evidence = {"classification": "synthetic-reference-quality", "organizationId": organization, "queueKey": queue, "fixtureHash": fixture_hash, "promptVersion": prompt_version, "proofId": proof, "startRequestId": str(uuid.uuid5(uuid.UUID(proof), "StartTestRun")), "complete": False, "tenantCalls": True}
        write(output, evidence)
    command = _cli_command()
    def call(method, relative, body=None):
        return _cli_request(command, origin, method, relative, body, runner=subprocess.run)
    evidence["complete"] = False
    write(output, evidence)
    who = call("GET", "WhoAmI")
    if str(who.get("OrganizationId", "")).lower() != organization.lower():
        raise ValueError("ENVIRONMENT_MISMATCH")
    if not args.observe:
        response = call("POST", "qmcp_WQ_StartTestRun", {"QueueKey": queue, "RequestId": evidence["startRequestId"], "DataJson": json.dumps({"cases": cases}, separators=(",", ":"))})
        evidence["runId"] = json.loads(response.get("ResultJson", "{}"))["RunId"]
        write(output, evidence)
    try:
        observe(call, evidence, cases, evidence["runId"], queue, queue_id)
    finally:
        write(output, evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    if not evidence.get("complete"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, KeyError, TypeError, ValueError) as error:
        code = str(error) if re.fullmatch(r"[A-Z_]+", str(error)) else "PROOF_INCONCLUSIVE"
        raise SystemExit(code)
