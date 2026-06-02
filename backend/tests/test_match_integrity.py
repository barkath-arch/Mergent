"""V1 MATCH INTEGRITY RULE — must remain green throughout V1.

Rule: if a buyer initiates checkout claiming it originates from a match run,
the solution_id MUST equal the RankingAgent's top-1 of that run.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

API = os.environ.get("REACT_APP_BACKEND_URL") or os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2").read().strip()
DEMO = {"email": "rohit@mergent.demo", "password": "Demo!Pass123"}


class _Sess(requests.Session):
    """Requests session that preserves Authorization across same-eTLD+1 redirects
    (the preview→internal.preview ingress rewrite). Browsers do this natively;
    requests-the-library is stricter per RFC 7235, so we override `rebuild_auth`.
    """
    def rebuild_auth(self, prepared_request, response):  # noqa: D401, ARG002
        return  # keep headers as-is, including Authorization


def _login() -> tuple[_Sess, str]:
    s = _Sess()
    r = s.post(f"{API}/api/auth/login", json=DEMO, timeout=15)
    r.raise_for_status()
    tok = r.json()["access_token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, tok


def _run_match(s: _Sess, text: str) -> str:
    r = s.post(f"{API}/api/match", json={"requirement_text": text}, timeout=15)
    r.raise_for_status()
    return r.json()["run_id"]


def _wait_run(s: _Sess, run_id: str, timeout: int = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = s.get(f"{API}/api/match/{run_id}", timeout=15)
        if r.status_code == 200 and r.json().get("status") in ("completed", "failed"):
            return r.json()
        time.sleep(1.5)
    raise TimeoutError(f"run {run_id} did not complete")


class TestMatchIntegrity:
    """If checkout asserts an origin run_id, the solution MUST be ranked #1.

    Otherwise: 409 match_integrity_violation. Without run_id, checkout proceeds.
    """

    def test_top1_passes(self):
        s, _ = _login()
        rid = _run_match(s, "textile manufacturer Surat ERP inventory fabric SKUs batch dyeing supplier POs multi-tenant")
        run = _wait_run(s, rid)
        assert run["status"] == "completed"
        top1 = run["result"][0]["solutionId"]
        r = s.post(
            f"{API}/api/checkout/session",
            json={"solution_id": top1, "run_id": rid},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"expected 201 got {r.status_code} body={r.text}"
        body = r.json()
        assert "transaction_id" in body
        tx = s.get(f"{API}/api/transactions/{body['transaction_id']}", timeout=10).json()
        assert tx["match_integrity"] == "verified_top1"
        assert tx["origin_run_id"] == rid

    def test_not_top1_blocked_with_409(self):
        s, _ = _login()
        rid = _run_match(s, "textile manufacturer Surat ERP inventory fabric SKUs batch dyeing supplier POs")
        run = _wait_run(s, rid)
        assert run["status"] == "completed"
        not_top = run["result"][-1]["solutionId"]
        assert not_top != run["result"][0]["solutionId"]
        r = s.post(
            f"{API}/api/checkout/session",
            json={"solution_id": not_top, "run_id": rid},
            timeout=15,
        )
        assert r.status_code == 409, f"expected 409 violation got {r.status_code} body={r.text}"
        detail = r.json().get("detail", {})
        assert detail.get("error") == "match_integrity_violation"
        assert detail.get("ranked_top") == run["result"][0]["solutionId"]
        assert detail.get("requested") == not_top

    def test_no_run_id_proceeds(self):
        s, _ = _login()
        sols = s.get(f"{API}/api/marketplace/search?limit=1", timeout=10).json()
        sid = sols["items"][0]["id"]
        r = s.post(
            f"{API}/api/checkout/session",
            json={"solution_id": sid},
            timeout=20,
        )
        assert r.status_code in (200, 201), f"expected ok got {r.status_code} body={r.text}"
        assert r.json().get("transaction_id")
