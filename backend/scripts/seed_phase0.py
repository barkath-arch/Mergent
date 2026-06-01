"""Seed the Phase 0 catalogue with 10 realistic solutions.

Idempotent: solutions are upserted by `title` (unique index in db.py).
After insert, kicks Celery to embed each solution and polls until all are
embedded (or a timeout). Then rebuilds the in-process VectorIndex.

Run:
    cd /app/backend
    python -m scripts.seed_phase0
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

SEED_DATA: List[Dict[str, Any]] = [
    {
        "title": "TextileFlow ERP",
        "tagline": "End-to-end ERP for textile mills with multi-location inventory and vendor portal",
        "description": (
            "TextileFlow ERP is a production-grade inventory and ERP suite purpose-built for textile "
            "manufacturers. It tracks raw material (yarn, dyes, fabric rolls) across multiple warehouses, "
            "supports lot/batch traceability, and includes a vendor portal for spinners and weavers to "
            "submit POs, dispatch updates, and quality reports. Production planning, BOM management, "
            "and shopfloor data capture are built-in. Multi-currency, GST/VAT-ready, with role-based "
            "access and audit trails."
        ),
        "category": "Inventory Management",
        "tech_stack": ["React", "Node.js", "PostgreSQL", "Redis", "Docker"],
        "tags": ["textile", "inventory", "multi-location", "vendor portal", "erp", "manufacturing", "BOM", "lot tracking"],
        "price_usd": 18000,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "WeaveStack Systems",
        "builder_rating": 4.8,
        "uptime_pct": 99.95,
        "clients_count": 47,
    },
    {
        "title": "WeaveTrack Pro",
        "tagline": "Loom-floor tracking and inventory for weaving units",
        "description": (
            "WeaveTrack Pro digitises the loom floor — capturing real-time per-loom production, "
            "downtime, defect logs, and pick counts. The inventory module handles warp/weft yarn stock "
            "by lot, beam allocation, and grey fabric movement to warehouse. A lightweight vendor "
            "ledger lets you reconcile jobwork supplier balances. Targets small-to-mid weaving units "
            "with up to 200 looms."
        ),
        "category": "Inventory Management",
        "tech_stack": ["React", "FastAPI", "MongoDB", "MQTT"],
        "tags": ["textile", "weaving", "loom tracking", "inventory", "jobwork", "manufacturing"],
        "price_usd": 6500,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "Loomly Labs",
        "builder_rating": 4.6,
        "uptime_pct": 99.7,
        "clients_count": 22,
    },
    {
        "title": "StockMaster Plus",
        "tagline": "Multi-location stock and order management for SMBs",
        "description": (
            "StockMaster Plus is a flexible inventory and order management platform supporting multiple "
            "warehouses, transfer orders, barcode/QR scanning, low-stock alerts, and a supplier portal "
            "for replenishment. Industries served include apparel, hardware, and FMCG distribution. "
            "Includes a basic vendor PO workflow and reorder-point automation."
        ),
        "category": "Inventory Management",
        "tech_stack": ["Vue", "Django", "PostgreSQL", "Celery"],
        "tags": ["inventory", "multi-location", "barcode", "vendor portal", "stock", "warehouse"],
        "price_usd": 4800,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "BoxLogic",
        "builder_rating": 4.4,
        "uptime_pct": 99.5,
        "clients_count": 130,
    },
    {
        "title": "FabricPulse Inventory",
        "tagline": "SaaS inventory for fabric wholesalers and traders",
        "description": (
            "FabricPulse is a cloud-native inventory system for fabric traders and wholesalers. It "
            "supports roll-level stock tracking, GSM/width/colour attributes, multi-location godowns, "
            "and a buyer-facing catalogue. Integrated invoicing and a vendor purchase-tracking module "
            "round out a complete trader workflow."
        ),
        "category": "Inventory Management",
        "tech_stack": ["Next.js", "Node.js", "MongoDB"],
        "tags": ["textile", "fabric", "wholesale", "inventory", "multi-location", "catalogue"],
        "price_usd": 3600,
        "license_model": "saas_monthly",
        "deployment_maturity": "production-grade",
        "builder_name": "BoltCloth Software",
        "builder_rating": 4.3,
        "uptime_pct": 99.8,
        "clients_count": 64,
    },
    {
        "title": "PeoplePilot HR",
        "tagline": "Modern HRIS with payroll, leave, and onboarding",
        "description": (
            "PeoplePilot HR is a unified HRIS covering employee records, leave and attendance, payroll "
            "with statutory compliance for IN/US/UK, onboarding workflows, and a self-service portal. "
            "Includes performance review cycles, OKR tracking, and exportable analytics dashboards."
        ),
        "category": "HR System",
        "tech_stack": ["React", "Ruby on Rails", "PostgreSQL"],
        "tags": ["hr", "payroll", "leave", "onboarding", "compliance", "self-service"],
        "price_usd": 9500,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "OrbitHR",
        "builder_rating": 4.7,
        "uptime_pct": 99.9,
        "clients_count": 210,
    },
    {
        "title": "HireBoard ATS",
        "tagline": "Applicant tracking + onboarding for growing teams",
        "description": (
            "HireBoard ATS streamlines recruiting with kanban pipelines, structured interview scorecards, "
            "calendar integrations, offer letter automation, and a built-in onboarding checklist that "
            "hands off to your HRIS. Includes referral tracking and DEI hiring analytics."
        ),
        "category": "HR System",
        "tech_stack": ["React", "Node.js", "PostgreSQL", "Redis"],
        "tags": ["ats", "recruiting", "interviews", "onboarding", "hr"],
        "price_usd": 4200,
        "license_model": "saas_monthly",
        "deployment_maturity": "production-grade",
        "builder_name": "TalentHub Labs",
        "builder_rating": 4.5,
        "uptime_pct": 99.7,
        "clients_count": 88,
    },
    {
        "title": "Helio CRM",
        "tagline": "Sales pipeline + customer 360 for B2B teams",
        "description": (
            "Helio CRM unifies leads, contacts, accounts, deals, and tickets in one place. It offers "
            "kanban pipelines, email + WhatsApp sync, lead scoring, custom fields, and a no-code "
            "automation builder for reminders and follow-ups. Open API for integration with marketing "
            "and finance tools."
        ),
        "category": "CRM",
        "tech_stack": ["React", "Node.js", "PostgreSQL", "ElasticSearch"],
        "tags": ["crm", "sales", "pipeline", "automation", "b2b", "email sync"],
        "price_usd": 7800,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "Helio Software",
        "builder_rating": 4.6,
        "uptime_pct": 99.9,
        "clients_count": 312,
    },
    {
        "title": "ClientSphere CRM",
        "tagline": "Lightweight CRM for service businesses",
        "description": (
            "ClientSphere is a streamlined CRM for service businesses (agencies, consultancies, salons). "
            "It manages contacts, projects, recurring engagements, invoicing, and basic email "
            "campaigns. Mobile-first design with a built-in scheduler."
        ),
        "category": "CRM",
        "tech_stack": ["Vue", "Laravel", "MySQL"],
        "tags": ["crm", "services", "invoicing", "scheduling", "agencies"],
        "price_usd": 2400,
        "license_model": "saas_monthly",
        "deployment_maturity": "production-grade",
        "builder_name": "Sphere Apps",
        "builder_rating": 4.2,
        "uptime_pct": 99.5,
        "clients_count": 540,
    },
    {
        "title": "FlowDesk PM",
        "tagline": "Project management with sprints, gantt, and time tracking",
        "description": (
            "FlowDesk is a modern project management suite combining boards, sprints, gantt charts, "
            "issue tracking, time logs, and resource planning. Integrates with GitHub, Slack, and "
            "Figma. Supports both agile and waterfall workflows with custom fields and report builders."
        ),
        "category": "Project Management",
        "tech_stack": ["React", "Go", "PostgreSQL", "Redis"],
        "tags": ["project management", "sprints", "gantt", "time tracking", "agile", "kanban"],
        "price_usd": 6900,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "FlowDesk Inc.",
        "builder_rating": 4.7,
        "uptime_pct": 99.9,
        "clients_count": 480,
    },
    {
        "title": "ShopCart E-Commerce",
        "tagline": "Headless e-commerce platform with omnichannel inventory",
        "description": (
            "ShopCart is a headless e-commerce platform with a storefront builder, omnichannel "
            "inventory sync (warehouses + retail outlets), order orchestration, integrated payments "
            "(Stripe/Razorpay), and a marketplace plugin for multi-vendor sellers. Includes built-in "
            "SEO, reviews, and abandoned-cart workflows."
        ),
        "category": "E-commerce",
        "tech_stack": ["Next.js", "Node.js", "PostgreSQL", "Redis", "Stripe"],
        "tags": ["ecommerce", "headless", "inventory", "payments", "marketplace", "omnichannel"],
        "price_usd": 14500,
        "license_model": "annual_subscription",
        "deployment_maturity": "production-grade",
        "builder_name": "BlueCart Studio",
        "builder_rating": 4.6,
        "uptime_pct": 99.95,
        "clients_count": 175,
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed() -> Dict[str, Any]:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    db = client[os.environ["DB_NAME"]]

    # Ensure indexes (idempotent).
    await db.solutions.create_index("title", unique=True, name="solutions_title_unique")
    await db.solutions.create_index(
        [("title", "text"), ("description", "text"), ("tags", "text")],
        name="solutions_text_idx",
        default_language="english",
    )
    await db.solutions.create_index("category", name="solutions_category_idx")

    inserted_ids: List[str] = []
    for item in SEED_DATA:
        now = _now_iso()
        existing = await db.solutions.find_one({"title": item["title"]}, {"_id": 1})
        if existing:
            sid = existing["_id"]
            await db.solutions.update_one(
                {"_id": sid},
                {"$set": {**item, "updated_at": now}},
            )
            inserted_ids.append(sid)
            print(f"[seed] upserted: {item['title']} ({sid})")
        else:
            sid = str(uuid.uuid4())
            doc = {**item, "_id": sid, "embedding": [], "embedding_updated_at": None,
                   "created_at": now, "updated_at": now}
            await db.solutions.insert_one(doc)
            inserted_ids.append(sid)
            print(f"[seed] inserted: {item['title']} ({sid})")

    # Enqueue embedding for all 10 via Celery.
    from tasks import try_enqueue_embed
    queued: List[str] = []
    for sid in inserted_ids:
        # Force a re-embed even if a lock exists from a previous run.
        try:
            from tasks import _redis
            _redis().delete(f"embed:lock:{sid}")
        except Exception:
            pass
        res = try_enqueue_embed(sid)
        if res.get("queued"):
            queued.append(sid)
            print(f"[seed] queued embed for {sid}: {res}")
        else:
            print(f"[seed] skipped enqueue for {sid}: {res}")

    # Poll until all docs have embeddings.
    deadline = time.time() + 180
    while time.time() < deadline:
        with_emb = await db.solutions.count_documents({"embedding": {"$ne": []}})
        total = await db.solutions.count_documents({"_id": {"$in": inserted_ids}})
        print(f"[seed] embedded {with_emb}/{total} ...")
        if with_emb >= total:
            break
        await asyncio.sleep(2)
    else:
        print("[seed] WARN: timed out waiting for embeddings")

    # Trigger the running server to refresh the in-process vector index.
    try:
        import httpx
        backend = os.environ.get("APP_URL") or "http://localhost:8001"
        async with httpx.AsyncClient(timeout=5) as h:
            r = await h.get(f"{backend.rstrip('/')}/api/health")
            print(f"[seed] health after seed: {r.status_code}")
    except Exception as exc:
        print(f"[seed] note: could not ping health endpoint: {exc}")

    # Now print final state.
    final_count = await db.solutions.count_documents({"embedding": {"$ne": []}})
    print(f"[seed] DONE. {final_count} solutions in catalogue with embeddings.")
    client.close()
    return {"inserted": inserted_ids, "queued": queued, "final_count": final_count}


if __name__ == "__main__":
    res = asyncio.run(seed())
    print(res)
