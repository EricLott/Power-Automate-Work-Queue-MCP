import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from prove_transaction_boundaries import RETAINED_ITEM, collection, fault_from_stdout, main, trace_evidence, validate


class TransactionBoundaryProofTests(unittest.TestCase):
    binding = {"environmentUrl": "https://synthetic.crm.dynamics.com", "organizationId": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "environmentClass": "development", "queueKeys": ["qmcp-proof-test"]}
    ledger = {"queueKey": "qmcp-proof-test", "queue": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", "team": "cccccccc-cccc-cccc-cccc-cccccccccccc", "principal": "dddddddd-dddd-dddd-dddd-dddddddddddd", "user": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "queuedItemId": RETAINED_ITEM}

    def test_validate_requires_exact_retained_item(self):
        with self.assertRaisesRegex(ValueError, "RETAINED_ITEM"):
            validate(self.binding, dict(self.ledger, queuedItemId="11111111-1111-1111-1111-111111111111"))

    def test_fault_parser_accepts_wrapped_and_exact_failure(self):
        self.assertEqual("INJECTED_PROOF_FAILURE", fault_from_stdout(json.dumps({"error": {"message": "INJECTED_PROOF_FAILURE"}})))
        wrapped = {"error": {"message": json.dumps({"error": {"message": "INJECTED_PROOF_FAILURE"}})}}
        self.assertEqual("INJECTED_PROOF_FAILURE", fault_from_stdout(json.dumps(wrapped)))
        self.assertIsNone(fault_from_stdout(json.dumps({"error": {"message": "other"}})))
        native = {"errorCode": "InternalServerError", "message": "Fail to update work queue item " + RETAINED_ITEM + " to Processing because: ACQUISITION_HANDOFF_FAILED. Fault ErrorCode: -2147220891"}
        self.assertEqual("ACQUISITION_HANDOFF_FAILED", fault_from_stdout(json.dumps({"error": {"message": json.dumps(native)}})))
        native["message"] += " unrelated"
        self.assertIsNone(fault_from_stdout(json.dumps({"error": {"message": json.dumps(native)}})))

    def test_dry_run_never_constructs_cli_or_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); b = base / "binding.json"; l = base / "ledger.json"; o = base / "proof"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            with patch("prove_transaction_boundaries._cli_command", side_effect=AssertionError("CLI")):
                main(["--binding", str(b), "--fixture-ledger", str(l), "--output-dir", str(o), "--run-id", "offline"])
            self.assertFalse(o.exists())

    def test_existing_output_is_rejected_before_cli(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); b = base / "binding.json"; l = base / "ledger.json"; o = base / "proof"; o.mkdir(); (o / "keep").write_text("x")
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            with patch("prove_transaction_boundaries._cli_command", side_effect=AssertionError("CLI")):
                with self.assertRaisesRegex(ValueError, "EVIDENCE_RUN_EXISTS"):
                    main(["--binding", str(b), "--fixture-ledger", str(l), "--output-dir", str(o), "--run-id", "offline"])
            self.assertEqual("x", (o / "keep").read_text())

    def test_evidence_collections_and_trace_fields_are_strict(self):
        for response in ({}, {"value": None}, {"value": [], "@odata.nextLink": "next"}):
            with self.subTest(response=response):
                with self.assertRaisesRegex(ValueError, "EVIDENCE_COLLECTION_INVALID"):
                    collection(response)
        with self.assertRaisesRegex(ValueError, "TRACE_TRANSACTION_INVALID"):
            trace_evidence([{"messageblock": "qmcp operation qmcp_WQ_AcceptAcquire; transaction False; depth 1"}])
        with self.assertRaisesRegex(ValueError, "TRACE_TRANSACTION_FIELDS_MISSING"):
            trace_evidence([{"messageblock": "qmcp operation qmcp_WQ_AcceptAcquire; transaction True; depth 1"}])

    def test_mocked_matrix_restores_settings_and_completes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); b = base / "binding.json"; l = base / "ledger.json"; out = base / "proof"
            b.write_text(json.dumps(self.binding)); l.write_text(json.dumps(self.ledger))
            state = {"principal": json.dumps({"production": False, "roles": ["deployment", "worker"]}), "setting": 0,
                     "native": {"workqueueitemid": RETAINED_ITEM, "statecode": 0, "statuscode": 0},
                     "context": {"ItemId": RETAINED_ITEM, "ActiveAttempt": "", "AttemptCount": 0}, "patches": [], "bad_trace": False}
            org = self.binding["organizationId"]; principal = self.ledger["principal"]; queue = self.ledger["queue"]

            def cli_request(command, origin, method, path, body=None, **kwargs):
                if method == "GET" and path == "WhoAmI": return {"OrganizationId": org, "UserId": self.ledger["user"]}
                if path.startswith("workflows("): return {"statecode": 0}
                if path.startswith("workqueueitems?"): return {"value": [dict(state["native"])]}
                if path.startswith("workqueueitems("): return dict(state["native"])
                if path.startswith("qmcp_wqdefinitions?"): return {"value": [{"qmcp_document": json.dumps({"Enabled": True, "NativeQueueId": queue})}]}
                if path.startswith("qmcp_wqprincipals("):
                    if method == "GET": return {"qmcp_document": state["principal"]}
                    state["principal"] = body["qmcp_document"]; state["patches"].append("principal"); return {}
                if path.startswith("organizations("):
                    if method == "GET": return {"plugintracelogsetting": state["setting"]}
                    state["setting"] = body["plugintracelogsetting"]; state["patches"].append("tracing"); return {}
                if path.startswith("qmcp_wqitemcontexts?"): return {"value": [{"qmcp_document": json.dumps(state["context"])}]}
                if path.startswith("qmcp_wqattempts?") or path.startswith("qmcp_wqcommands?"): return {"value": []}
                if path.startswith("plugintracelogs?"):
                    if "correlationid eq" in path:
                        correlation = path.split("correlationid eq ", 1)[1].split("&", 1)[0]
                        message = "bad trace" if state["bad_trace"] else "qmcp operation qmcp_WQ_AcceptAcquire; transaction True; depth 1\r\nqmcp failure INJECTED_PROOF_FAILURE; correlation test\r\nqmcp acquisition claim validated; transaction True; depth 1"
                        return {"value": [{"correlationid": correlation, "depth": 1, "typename": "LifecyclePlugin", "createdon": "2026-01-01", "messageblock": message}]}
                    return {"value": [{"correlationid": ("%08d-1111-1111-1111-111111111111" % (i + 1)), "messageblock": "prepare"} for i in range(6)]}
                if path == "qmcp_WQ_PrepareAcquire": return {"ResultJson": json.dumps({"Outcome": "Prepared", "Expires": "2099-01-01T00:00:00Z"})}
                if path == "qmcp_WQ_ResolveAcquire": return {"ResultJson": json.dumps({"Outcome": "Pending"})}
                if "Microsoft.Dynamics.CRM.Dequeue" in path:
                    kwargs["runner"](["dequeue"], capture_output=True, text=True, timeout=60, check=False)
                    raise ValueError("DATAVERSE_CLI_FAILED")
                raise AssertionError(path)

            from types import SimpleNamespace
            def run(*args, **kwargs):
                return SimpleNamespace(returncode=1, stdout=json.dumps({"error": {"message": "INJECTED_PROOF_FAILURE"}}))
            args = ["--binding", str(b), "--fixture-ledger", str(l), "--output-dir", str(out), "--run-id", "mock", "--execute"]
            with patch("prove_transaction_boundaries._cli_command", return_value=["cli"]), patch("prove_transaction_boundaries._cli_request", side_effect=cli_request), patch("prove_transaction_boundaries.subprocess.run", side_effect=run), patch("prove_transaction_boundaries.time.sleep"):
                main(args)
            evidence = json.loads((out / "evidence.json").read_text())
            self.assertTrue(evidence["completed"])
            self.assertEqual(set(evidence["faults"]), {"after-native-claim", "after-attempt", "after-context", "after-intent", "before-receipt", "after-receipt"})
            self.assertTrue(all(item["error"] == "INJECTED_PROOF_FAILURE" and item["acceptReceipts"] == 0 and item["attemptCount"] == 0 and item["resolve"]["Outcome"] == "Pending" for item in evidence["faults"].values()))
            self.assertEqual(0, state["setting"])
            original_profile = {"production": False, "roles": ["deployment", "worker"]}
            self.assertEqual(json.loads(state["principal"]), original_profile)
            self.assertEqual(set(state["patches"]), {"principal", "tracing"})

            # A trace-quality failure must leave a persisted incomplete run and
            # still restore both temporary tenant settings.
            state["bad_trace"] = True; state["setting"] = 0; state["patches"] = []
            failed = base / "failed-proof"
            with patch("prove_transaction_boundaries._cli_command", return_value=["cli"]), patch("prove_transaction_boundaries._cli_request", side_effect=cli_request), patch("prove_transaction_boundaries.subprocess.run", side_effect=run), patch("prove_transaction_boundaries.time.sleep"):
                with self.assertRaisesRegex(ValueError, "INJECTED_TRACE_NOT_OBSERVED"):
                    main(["--binding", str(b), "--fixture-ledger", str(l), "--output-dir", str(failed), "--run-id", "mock-failed", "--execute"])
            failed_evidence = json.loads((failed / "evidence.json").read_text())
            self.assertFalse(failed_evidence["completed"])
            self.assertEqual(0, state["setting"])
            self.assertEqual(False, json.loads(state["principal"])["production"])


if __name__ == "__main__": unittest.main()
