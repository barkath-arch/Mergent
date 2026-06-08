"""Transactions / Escrow / Reviews — Stripe checkout + SIMULATED escrow state machine.

SIMULATED: real state machine, simulated infra
  - Stripe checkout for funding is real (test mode via emergentintegrations)
  - Escrow advance (in_progress → delivered → released) is buyer-driven manually here
  - Builder payout via Stripe Connect is NOT wired; release simply credits builder_profiles.earnings_usd.

States: initiated → funded → in_progress → delivered → released → reviewed
       (any → disputed/refunded by admin)
MATCH INTEGRITY RULE (codified in tests/test_match_integrity.py):
  the recommended solution_id propagated to the transaction must equal the
  RankingAgent's top-1 of the originating run.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user, require_role
from db import get_db
from services.notifications import notify
from services.trust_agent import persist_trust

router = APIRouter(prefix="/api", tags=["transactions"])

VALID_STATES = ["initiated", "funded", "in_progress", "delivered", "released", "reviewed", "disputed", "refunded"]


class CheckoutIn(BaseModel):
    solution_id: str
    run_id: Optional[str] = None  # for MATCH INTEGRITY enforcement
    origin_url: str = Field(default="https://github-deploy-hub-1.preview.emergentagent.com")


class AdvanceIn(BaseModel):
    next_state: str = Field(pattern="^(in_progress|delivered|released|disputed|refunded)$")
    note: Optional[str] = Field(None, max_length=500)


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(min_length=4, max_length=2000)


def _serialize_tx(t: Dict[str, Any]) -> Dict[str, Any]:
    out = {**t}
    out["id"] = out.pop("_id")
    return out


# ============== Stripe via emergentintegrations ==============
def _stripe():
    """Lazy import + construct so module import never fails on missing key."""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    api_key = os.environ.get("STRIPE_API_KEY", "")
    return StripeCheckout(api_key=api_key, webhook_url="")


@router.post("/checkout/session", status_code=201)
async def create_checkout(req: Request, body: CheckoutIn, user: Dict[str, Any] = Depends(require_role("buyer", "admin"))) -> Dict[str, Any]:
    db = get_db()
    solution = await db.solutions.find_one({"_id": body.solution_id})
    if not solution:
        raise HTTPException(404, detail={"error": "solution_not_found"})

    # MATCH INTEGRITY: if buyer claims this came from a match run, the solution must
    # be the top-1 of that run's ranking.
    integrity_status = "n/a"
    if body.run_id:
        run = await db.match_runs.find_one({"_id": body.run_id})
        if not run:
            raise HTTPException(404, detail={"error": "run_not_found", "run_id": body.run_id})
        top = ((run.get("result") or [{}])[:1] or [{}])[0]
        if top.get("solutionId") != body.solution_id:
            raise HTTPException(409, detail={
                "error": "match_integrity_violation",
                "ranked_top": top.get("solutionId"),
                "requested": body.solution_id,
            })
        integrity_status = "verified_top1"

    tx_id = str(uuid.uuid4())
    amount = float(solution["price_usd"])
    now = datetime.now(timezone.utc)
    tx_doc = {
        "_id": tx_id,
        "buyer_id": user["id"],
        "buyer_name": user.get("name"),
        "builder_id": solution["builder_id"],
        "builder_name": solution.get("builder_name"),
        "solution_id": body.solution_id,
        "solution_title": solution.get("title"),
        "amount_usd": amount,
        "currency": "usd",
        "status": "initiated",
        "state_history": [{"state": "initiated", "at": now, "by": user["id"]}],
        "match_integrity": integrity_status,
        "origin_run_id": body.run_id,
        "stripe_session_id": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.transactions.insert_one(tx_doc)

    success_url = f"{body.origin_url}/transactions/{tx_id}?status=success&sid={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{body.origin_url}/transactions/{tx_id}?status=cancel"
    try:
        from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest
        stripe = _stripe()
        req_obj = CheckoutSessionRequest(
            amount=amount, currency="usd",
            success_url=success_url, cancel_url=cancel_url,
            metadata={"transaction_id": tx_id, "solution_id": body.solution_id, "buyer_id": user["id"]},
        )
        session = await stripe.create_checkout_session(req_obj)
        await db.transactions.update_one(
            {"_id": tx_id},
            {"$set": {"stripe_session_id": session.session_id, "stripe_session_url": session.url, "updated_at": datetime.now(timezone.utc)}},
        )
        return {"transaction_id": tx_id, "checkout_url": session.url, "session_id": session.session_id}
    except Exception as e:
        # SIMULATED fallback: emergent integrations may not be reachable in preview pods.
        # Mark as funded immediately so the demo flow works end-to-end.
        sim_session_id = f"sim_{tx_id[:18]}"
        now2 = datetime.now(timezone.utc)
        await db.transactions.update_one(
            {"_id": tx_id},
            {"$set": {
                "stripe_session_id": sim_session_id,
                "status": "funded",
                "updated_at": now2,
                "simulated_checkout": True,
                "simulated_reason": str(e)[:200],
            }, "$push": {"state_history": {"state": "funded", "at": now2, "by": "stripe:simulated"}}},
        )
        return {
            "transaction_id": tx_id,
            "checkout_url": f"{body.origin_url}/transactions/{tx_id}?status=success&sid={sim_session_id}&sim=1",
            "session_id": sim_session_id,
            "simulated": True,
        }


@router.get("/checkout/status/{session_id}")
async def checkout_status(session_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    tx = await db.transactions.find_one({"stripe_session_id": session_id})
    if not tx:
        raise HTTPException(404, detail={"error": "session_not_found"})
    if tx.get("simulated_checkout"):
        return {"status": "funded", "transaction": _serialize_tx(tx), "simulated": True}
    try:
        stripe = _stripe()
        res = await stripe.get_checkout_status(session_id)
        if res.payment_status in ("paid", "succeeded") and tx["status"] == "initiated":
            now = datetime.now(timezone.utc)
            await db.transactions.update_one(
                {"_id": tx["_id"]},
                {"$set": {"status": "funded", "updated_at": now},
                 "$push": {"state_history": {"state": "funded", "at": now, "by": "stripe"}}},
            )
            tx = await db.transactions.find_one({"_id": tx["_id"]})
        return {"status": res.payment_status, "transaction": _serialize_tx(tx)}
    except Exception as e:
        return {"status": tx["status"], "transaction": _serialize_tx(tx), "error": str(e)[:200]}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> Dict[str, Any]:
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        stripe = _stripe()
        event = await stripe.handle_webhook(body, sig)
    except Exception:
        return {"received": False}
    db = get_db()
    if event.event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        tx_id = event.metadata.get("transaction_id") if event.metadata else None
        if tx_id:
            now = datetime.now(timezone.utc)
            await db.transactions.update_one(
                {"_id": tx_id, "status": "initiated"},
                {"$set": {"status": "funded", "updated_at": now},
                 "$push": {"state_history": {"state": "funded", "at": now, "by": "stripe.webhook"}}},
            )
    return {"received": True}


@router.post("/transactions/{tx_id}/advance")
async def advance_tx(tx_id: str, body: AdvanceIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    tx = await db.transactions.find_one({"_id": tx_id})
    if not tx:
        raise HTTPException(404, detail={"error": "transaction_not_found"})
    if user["id"] not in (tx["buyer_id"], tx["builder_id"]) and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_a_party"})

    legal: Dict[str, List[str]] = {
        "funded": ["in_progress", "refunded"],
        "in_progress": ["delivered", "disputed"],
        "delivered": ["released", "disputed"],
        "released": [],
        "reviewed": [],
        "initiated": ["refunded"],
        "disputed": ["released", "refunded"],
    }
    cur = tx["status"]
    if body.next_state not in legal.get(cur, []):
        raise HTTPException(409, detail={"error": "illegal_transition", "from": cur, "to": body.next_state})

    # Builder advances in_progress→delivered; Buyer advances funded→in_progress and delivered→released.
    if body.next_state == "delivered" and user["id"] != tx["builder_id"] and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "only_builder_can_deliver"})
    if body.next_state == "released" and user["id"] != tx["buyer_id"] and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "only_buyer_can_release"})

    now = datetime.now(timezone.utc)
    update: Dict[str, Any] = {"status": body.next_state, "updated_at": now}
    if body.next_state == "released":
        # SIMULATED escrow release: credit builder ledger.
        await db.builder_profiles.update_one(
            {"_id": tx["builder_id"]},
            {"$inc": {"earnings_usd": float(tx["amount_usd"])}},
        )
    if body.next_state in ("released", "delivered"):
        await db.solutions.update_one({"_id": tx["solution_id"]}, {"$inc": {"clients_count": 1 if body.next_state == "released" else 0}})

    await db.transactions.update_one(
        {"_id": tx_id},
        {"$set": update,
         "$push": {"state_history": {"state": body.next_state, "at": now, "by": user["id"], "note": body.note}}},
    )

    # ---------- Notifications + Trust hook (Phase 6 + 7) ----------
    fresh_tx = await db.transactions.find_one({"_id": tx_id})
    other_id = fresh_tx["buyer_id"] if user["id"] != fresh_tx["buyer_id"] else fresh_tx["builder_id"]
    try:
        await notify(
            other_id,
            type="transaction_state_change",
            category="transactions",
            title=f"Purchase {body.next_state.replace('_', ' ')}",
            body=f"{fresh_tx.get('solution_title','Your transaction')} moved to {body.next_state.replace('_',' ')}.",
            link=f"/transactions/{tx_id}",
            email_template="transaction_state_change",
            email_context={
                "transaction_id": tx_id,
                "solution_title": fresh_tx.get("solution_title"),
                "amount_usd": fresh_tx.get("amount_usd", 0),
                "next_state": body.next_state,
                "counterparty": (fresh_tx.get("buyer_name") if other_id == fresh_tx["builder_id"] else fresh_tx.get("builder_name")),
            },
            debounce_key=f"tx:{tx_id}:{body.next_state}",
        )
    except Exception as e:
        print(f"[mergent.tx] notify_failed: {e}")
    # Recompute trust on released (event-driven, non-blocking guarded).
    if body.next_state == "released":
        try:
            await persist_trust(fresh_tx["builder_id"])
        except Exception as e:
            print(f"[mergent.tx] trust_recompute_failed: {e}")
    return _serialize_tx(fresh_tx)


@router.get("/transactions/me")
async def my_transactions(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    q = {"$or": [{"buyer_id": user["id"]}, {"builder_id": user["id"]}]}
    items = [_serialize_tx(t) async for t in db.transactions.find(q).sort("created_at", -1).limit(50)]
    return {"items": items, "count": len(items)}


@router.get("/transactions/{tx_id}")
async def get_tx(tx_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    tx = await db.transactions.find_one({"_id": tx_id})
    if not tx:
        raise HTTPException(404, detail={"error": "transaction_not_found"})
    if user["id"] not in (tx["buyer_id"], tx["builder_id"]) and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "not_a_party"})
    return _serialize_tx(tx)


# ============== Reviews (gated on released) ==============
@router.post("/transactions/{tx_id}/review", status_code=201)
async def post_review(tx_id: str, body: ReviewIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    db = get_db()
    tx = await db.transactions.find_one({"_id": tx_id})
    if not tx:
        raise HTTPException(404, detail={"error": "transaction_not_found"})
    if tx["buyer_id"] != user["id"] and user.get("role") != "admin":
        raise HTTPException(403, detail={"error": "only_buyer_can_review"})
    if tx["status"] not in ("released", "reviewed"):
        raise HTTPException(409, detail={"error": "review_locked_until_released", "current_status": tx["status"]})
    existing = await db.reviews.find_one({"transaction_id": tx_id})
    if existing:
        raise HTTPException(409, detail={"error": "already_reviewed"})

    rid = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    review = {
        "_id": rid,
        "transaction_id": tx_id,
        "solution_id": tx["solution_id"],
        "builder_id": tx["builder_id"],
        "buyer_id": user["id"],
        "buyer_name": user.get("name"),
        "rating": int(body.rating),
        "comment": body.comment.strip(),
        "created_at": now,
    }
    await db.reviews.insert_one(review)
    # Recompute builder rating
    pipeline = [{"$match": {"builder_id": tx["builder_id"]}},
                {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}}]
    avg = 0.0; n = 0
    async for row in db.reviews.aggregate(pipeline):
        avg = float(row.get("avg") or 0.0); n = int(row.get("n") or 0)
    await db.builder_profiles.update_one(
        {"_id": tx["builder_id"]}, {"$set": {"rating": round(avg, 2), "review_count": n}}
    )
    await db.transactions.update_one({"_id": tx_id}, {"$set": {"status": "reviewed", "updated_at": now}})
    # Notify builder + trust recompute (Phase 6 + 7).
    try:
        await notify(
            tx["builder_id"],
            type="review_received",
            category="reviews",
            title=f"{int(body.rating)}-star review on {tx.get('solution_title','your solution')}",
            body=body.comment.strip()[:280],
            link=f"/solutions/{tx['solution_id']}",
            email_template="review_received",
            email_context={
                "buyer_name": user.get("name"),
                "rating": int(body.rating),
                "comment": body.comment.strip(),
                "solution_id": tx["solution_id"],
                "solution_title": tx.get("solution_title"),
            },
            debounce_key=f"review:{rid}",
        )
    except Exception as e:
        print(f"[mergent.review] notify_failed: {e}")
    try:
        await persist_trust(tx["builder_id"])
    except Exception as e:
        print(f"[mergent.review] trust_recompute_failed: {e}")
    return {**review, "id": rid}


@router.get("/solutions/{solution_id}/reviews")
async def solution_reviews(solution_id: str) -> Dict[str, Any]:
    db = get_db()
    items = [{**r, "id": r.pop("_id")} async for r in db.reviews.find({"solution_id": solution_id}).sort("created_at", -1).limit(50)]
    return {"items": items, "count": len(items)}
