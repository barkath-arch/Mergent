"""Mergent V1.6 — email service (Resend + clean SIMULATED fallback).

Single HTML/text layout, body rendered from a per-type recipe in Python.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
import resend  # noqa: F401

logger = logging.getLogger("services.email")
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email_templates"

# ----- recipes (subject + body_html + body_txt + cta) per template name ------
# Each recipe takes a context dict and returns the rendered parts.

def _r_email_verify(c):
    link = f"{c['base_url']}/auth/verify?token={c.get('token','')}"
    return {
        "header_tag": "Confirm your email",
        "title": "One last step",
        "intro": f"Hey {c.get('name','there')}, confirm your email to finish setting up your Mergent account.",
        "body_html": "<p>This keeps your account secure and unlocks the marketplace, AI Match, and notifications.</p>",
        "body_txt": "Confirm to unlock marketplace, AI Match, and notifications.",
        "cta_url": link, "cta_label": "Confirm email",
        "subject": "Confirm your Mergent email",
    }


def _r_password_reset(c):
    link = f"{c['base_url']}/auth/reset?token={c.get('token','')}"
    return {
        "header_tag": "Password reset",
        "title": "Reset your password",
        "intro": f"Someone (hopefully you) asked to reset the password for {c.get('email','your account')}.",
        "body_html": "<p>This link expires in 1 hour. If you didn't request this, you can ignore this message.</p>",
        "body_txt": "Reset link expires in 1 hour. Ignore if you didn't request.",
        "cta_url": link, "cta_label": "Reset password",
        "subject": "Reset your Mergent password",
    }


def _r_transaction_state_change(c):
    return {
        "header_tag": f"Transaction {c.get('next_state','update')}",
        "title": c.get("title", f"Update on {c.get('solution_title','your transaction')}"),
        "intro": f"Your transaction with {c.get('counterparty','your counterparty')} for {c.get('solution_title','a solution')} just moved to {c.get('next_state','a new state').replace('_',' ')}.",
        "body_html": f"<p style='font-size:13.5px;color:#9aa0bd;'>Amount: <strong style='color:#e6e7f0;'>${c.get('amount_usd',0):,}</strong> · Status: <strong style='color:#a78bfa;'>{c.get('next_state','—').replace('_',' ')}</strong></p>",
        "body_txt": f"Amount: ${c.get('amount_usd',0):,}. Status: {c.get('next_state','—').replace('_',' ')}.",
        "cta_url": f"{c['base_url']}/transactions/{c.get('transaction_id','')}",
        "cta_label": "View transaction",
        "subject": f"Mergent — your purchase is now {c.get('next_state','updated').replace('_',' ')}",
    }


def _r_new_message(c):
    return {
        "header_tag": "New message",
        "title": f"You have new messages from {c.get('sender_name','a teammate')}",
        "intro": "Open the conversation to reply. Future messages from this thread are batched every 5 minutes.",
        "body_html": f"<blockquote style='margin:14px 0;padding:12px 14px;background:#11142a;border-left:3px solid #8b5cf6;border-radius:8px;color:#e6e7f0;'>{c.get('message_preview','—')[:300]}</blockquote>",
        "body_txt": f"{c.get('sender_name','someone')}: {c.get('message_preview','—')[:300]}",
        "cta_url": f"{c['base_url']}/messages?c={c.get('conversation_id','')}",
        "cta_label": "Open conversation",
        "subject": f"Mergent — new message from {c.get('sender_name','a teammate')}",
    }


def _r_review_received(c):
    stars = "★" * int(c.get("rating", 5))
    return {
        "header_tag": "New review",
        "title": f"{stars} review from {c.get('buyer_name','a buyer')}",
        "intro": f"Your solution {c.get('solution_title','a solution')} received a {c.get('rating',5)}-star review.",
        "body_html": f"<p style='font-size:13.5px;color:#e6e7f0;'>\"{c.get('comment','')[:400]}\"</p>",
        "body_txt": f"{stars}: {c.get('comment','')[:400]}",
        "cta_url": f"{c['base_url']}/solutions/{c.get('solution_id','')}",
        "cta_label": "View solution",
        "subject": f"Mergent — {c.get('rating',5)}-star review on {c.get('solution_title','your solution')}",
    }


def _r_deployment_status(c):
    return {
        "header_tag": f"Deployment {c.get('state','update')}",
        "title": f"{c.get('solution_title','Your deployment')} is now {c.get('state','—').replace('_',' ')}",
        "intro": f"Version {c.get('version','—')}.",
        "body_html": "<p>Open the deployment console to see live logs, redeploy or roll back.</p>",
        "body_txt": "View live logs, redeploy or roll back from the console.",
        "cta_url": f"{c['base_url']}/deployments/{c.get('deployment_id','')}",
        "cta_label": "Open deployment",
        "subject": f"Mergent deployment — {c.get('state','update').replace('_',' ')}",
    }


def _r_match_completed(c):
    return {
        "header_tag": "AI Match completed",
        "title": "Your match is ready",
        "intro": f"We found {c.get('result_count','several')} matches in {c.get('total_execution_ms','—')}ms.",
        "body_html": f"<p style='color:#9aa0bd;'>Top result: <strong style='color:#e6e7f0;'>{c.get('top_title','—')}</strong> · score {c.get('top_score','—')}</p>",
        "body_txt": f"Top result: {c.get('top_title','—')} · score {c.get('top_score','—')}.",
        "cta_url": f"{c['base_url']}/ai-match?run={c.get('run_id','')}",
        "cta_label": "View matches",
        "subject": "Mergent — your AI match is ready",
    }


RECIPES = {
    "email_verify": _r_email_verify,
    "password_reset": _r_password_reset,
    "transaction_state_change": _r_transaction_state_change,
    "new_message": _r_new_message,
    "review_received": _r_review_received,
    "deployment_status": _r_deployment_status,
    "match_completed": _r_match_completed,
}


def _api_key() -> str:
    return (os.environ.get("RESEND_API_KEY") or "").strip()


def _from() -> str:
    return os.environ.get("EMAIL_FROM") or "Mergent <onboarding@resend.dev>"


def _base_url() -> str:
    return os.environ.get("NOTIFICATION_BASE_URL", "https://github-deploy-hub-1.preview.emergentagent.com")


def make_unsubscribe_token(user_id: str, category: str) -> str:
    return jwt.encode(
        {"sub": user_id, "category": category, "type": "unsubscribe"},
        os.environ["JWT_SECRET"], algorithm="HS256",
    )


def verify_unsubscribe_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])


def _render(parts: Dict[str, str], base_url: str, unsubscribe_token: Optional[str]) -> Dict[str, str]:
    layout = (TEMPLATES_DIR / "_layout.html").read_text()
    unsub_link = f"{base_url}/api/notifications/unsubscribe?token={unsubscribe_token}" if unsubscribe_token else ""
    unsub_html = f'<a href="{unsub_link}" style="color:#a78bfa;">Unsubscribe from this category</a>' if unsub_link else "You're receiving this because notifications are enabled."
    html = layout.format_map({
        **parts,
        "unsubscribe_html": unsub_html,
    })
    txt = (
        f"{parts['title']}\n\n"
        f"{parts['intro']}\n\n"
        f"{parts.get('body_txt','')}\n\n"
        f"{parts['cta_label']}: {parts['cta_url']}\n\n"
        f"— Mergent\n"
        f"Unsubscribe: {unsub_link or '(not applicable)'}\n"
    )
    return {"html": html, "txt": txt, "subject": parts["subject"]}


async def send_email(
    to: str,
    template_name: str,
    context: Dict[str, Any],
    subject: Optional[str] = None,
    category: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    recipe = RECIPES.get(template_name)
    if not recipe:
        return {"sent": False, "reason": f"unknown_template:{template_name}"}

    ctx = {"base_url": _base_url(), **context}
    parts = recipe(ctx)
    if subject:
        parts["subject"] = subject

    unsub = make_unsubscribe_token(user_id, category) if (user_id and category) else None
    rendered = _render(parts, ctx["base_url"], unsub)
    subj = rendered["subject"]

    api_key = _api_key()
    if not api_key:
        logger.warning(
            f"[SIMULATED] email_send (no RESEND_API_KEY) to={to} subject={subj!r} "
            f"template={template_name}"
        )
        return {"sent": True, "fallback": True, "reason": "no_resend_api_key", "preview_html_chars": len(rendered["html"])}

    try:
        resend.api_key = api_key
        params = {"from": _from(), "to": [to], "subject": subj, "html": rendered["html"], "text": rendered["txt"]}
        result = await asyncio.to_thread(resend.Emails.send, params)
        msg_id = result.get("id") if isinstance(result, dict) else None
        logger.info(f"email_sent to={to} template={template_name} provider_msg_id={msg_id}")
        return {"sent": True, "provider_msg_id": msg_id}
    except Exception as e:
        logger.warning(f"[SIMULATED] email_send_failed_falling_back to={to} template={template_name} err={str(e)[:160]}")
        return {"sent": False, "fallback": True, "reason": f"resend_error:{str(e)[:160]}"}
