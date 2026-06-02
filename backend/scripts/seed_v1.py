"""MERGENT V1 seed — builders, solutions, requirements, reviews, demo accounts.

Idempotent: re-running clears mergent V1 collections and reseeds.
Phase 0 catalogue (10 solutions) is preserved by re-seeding via seed_phase0 first.
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from db import get_db, ensure_indexes  # noqa: E402
from auth import hash_password  # noqa: E402


# -------- Builders (10) --------
BUILDERS = [
    {"name": "Aman Sharma", "email": "aman@mergent.demo", "headline": "Full-stack ERP & inventory systems", "skills": ["Python", "FastAPI", "React", "PostgreSQL"], "industry": "ERP"},
    {"name": "Priya Iyer", "email": "priya@mergent.demo", "headline": "CRM & sales automation specialist", "skills": ["Node.js", "React", "MongoDB", "Stripe"], "industry": "CRM"},
    {"name": "Rahul Verma", "email": "rahul@mergent.demo", "headline": "HR + payroll micro-SaaS", "skills": ["Django", "Vue", "Postgres", "Tailwind"], "industry": "HR"},
    {"name": "Sneha Gupta", "email": "sneha@mergent.demo", "headline": "E-commerce platforms for D2C brands", "skills": ["Next.js", "Shopify", "Stripe", "Algolia"], "industry": "E-commerce"},
    {"name": "Vikram Singh", "email": "vikram@mergent.demo", "headline": "Project ops & internal tooling", "skills": ["FastAPI", "React", "Redis", "Celery"], "industry": "Project Management"},
    {"name": "Anita Reddy", "email": "anita@mergent.demo", "headline": "Marketing automation & funnels", "skills": ["Node.js", "React", "Mailchimp", "Postgres"], "industry": "Marketing"},
    {"name": "Karthik Menon", "email": "karthik@mergent.demo", "headline": "Finance & accounting tools", "skills": ["Python", "Django", "React", "Stripe"], "industry": "Finance"},
    {"name": "Divya Patel", "email": "divya@mergent.demo", "headline": "Analytics dashboards & BI", "skills": ["Python", "Pandas", "Plotly", "React"], "industry": "Analytics"},
    {"name": "Rohan Joshi", "email": "rohan@mergent.demo", "headline": "Healthcare workflow tools", "skills": ["Node.js", "React", "HL7", "Postgres"], "industry": "Healthcare"},
    {"name": "Meera Nair", "email": "meera@mergent.demo", "headline": "Logistics & supply chain micro-apps", "skills": ["Python", "FastAPI", "React", "Google Maps"], "industry": "Logistics"},
]

# -------- Buyer demo + admin --------
BUYER = {"name": "Rohit Khanna", "email": "rohit@mergent.demo", "company": "Khanna Textiles Pvt Ltd", "industry": "Manufacturing"}
ADMIN = {"name": "Mergent Admin", "email": "admin@mergent.demo"}

DEMO_PASSWORD = "Demo!Pass123"
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "AdminPass123")

# -------- Solutions (40 total: 4 anchor + 36 procedural) --------
ANCHOR_SOLUTIONS = [
    {"title": "TextileFlow ERP",     "tagline": "End-to-end ERP for textile manufacturing",     "category": "Inventory Management", "price_usd": 12000, "builder_email": "aman@mergent.demo"},
    {"title": "FabricPulse Inventory","tagline": "Real-time fabric SKU + batch dyeing inventory","category": "Inventory Management", "price_usd": 6500,  "builder_email": "aman@mergent.demo"},
    {"title": "PeopleSync HR",       "tagline": "Modern HRIS for mid-size teams",               "category": "HR System",            "price_usd": 4500,  "builder_email": "rahul@mergent.demo"},
    {"title": "DealForge CRM",       "tagline": "Pipeline + revops CRM for B2B sales",          "category": "CRM",                  "price_usd": 8800,  "builder_email": "priya@mergent.demo"},
]

CATEGORIES = [
    "Inventory Management", "CRM", "HR System", "Project Management",
    "E-commerce", "Finance", "Analytics", "Marketing", "Operations",
]
TECHSTACKS = [["Python","FastAPI","React","Postgres"], ["Node.js","React","MongoDB"], ["Django","Vue","Postgres"], ["Next.js","Stripe","Tailwind"], ["FastAPI","Redis","Celery","React"]]
TAGLINES = [
    "Built for {industry} teams that need speed",
    "Open-source ready {category} for growing startups",
    "Enterprise-grade {category}, SMB pricing",
    "Modern, opinionated {category} with sane defaults",
    "Drop-in {category} with first-class integrations",
]
DESCRIPTIONS = [
    "Production-ready {category} platform with multi-tenant isolation, role-based access controls, exhaustive audit logging, and a clean REST/GraphQL surface. Tested at 200K daily writes; horizontally scalable; one-click deploy to AWS/GCP/Render. Includes admin dashboards, fine-grained permissions, real-time webhooks, and a developer SDK in Python, JS, and Go. Designed to replace bloated legacy stacks while preserving the workflows your team already knows.",
    "Lightweight yet powerful {category} solution focused on time-to-value. Set up in under an hour, integrate with your existing stack via OpenAPI, and operate at sub-100ms p95. Includes background workers, retry-safe pipelines, idempotent webhooks, and structured logs streamed to your APM of choice. Battle-tested in two YC-backed startups handling >$2M GMV/month.",
    "Modular {category} suite with first-class extensibility. Bring your own auth, swap out the persistence layer, plug in your billing provider — every layer has clean seams. Ships with sane defaults: bcrypt + JWT, Postgres + Redis, FastAPI + React. Production-monitored: structured logs, traces, metrics, p95 dashboards out of the box.",
]


def _builder_id_by_email(builders_map, email): return builders_map[email]["_id"]


async def main():
    db = get_db()
    await ensure_indexes()
    print("[seed_v1] resetting V1 collections (users/profiles/solutions/requirements/reviews/transactions/conversations/messages/deployments)")
    for c in ["users","builder_profiles","buyer_profiles","requirements","reviews","transactions",
              "conversations","messages","deployments","email_verification_tokens","password_reset_tokens","login_attempts"]:
        await db[c].delete_many({})
    # Drop ALL existing solutions; V1 owns the catalogue (Phase 0 invariant
    # is preserved by keeping TextileFlow ERP + FabricPulse as anchor entries).
    await db.solutions.delete_many({})

    now = datetime.now(timezone.utc)
    builders_map = {}

    # ----- Admin -----
    admin_id = "admin_" + uuid.uuid4().hex[:16]
    await db.users.insert_one({
        "_id": admin_id, "email": ADMIN["email"], "password_hash": hash_password(ADMIN_PASSWORD),
        "name": ADMIN["name"], "role": "admin", "avatar_url": None, "email_verified": True,
        "created_at": now, "updated_at": now,
    })

    # ----- Buyer (Rohit) -----
    buyer_id = "buyer_" + uuid.uuid4().hex[:16]
    await db.users.insert_one({
        "_id": buyer_id, "email": BUYER["email"], "password_hash": hash_password(DEMO_PASSWORD),
        "name": BUYER["name"], "role": "buyer", "avatar_url": None, "email_verified": True,
        "created_at": now, "updated_at": now,
    })
    await db.buyer_profiles.insert_one({
        "_id": buyer_id, "user_id": buyer_id, "company": BUYER["company"], "industry": BUYER["industry"],
        "purchases_count": 0, "spend_usd": 0.0, "joined_at": now,
    })

    # ----- Builders (10) -----
    for b in BUILDERS:
        bid = "builder_" + uuid.uuid4().hex[:16]
        await db.users.insert_one({
            "_id": bid, "email": b["email"], "password_hash": hash_password(DEMO_PASSWORD),
            "name": b["name"], "role": "builder", "avatar_url": None, "email_verified": True,
            "created_at": now, "updated_at": now,
        })
        await db.builder_profiles.insert_one({
            "_id": bid, "user_id": bid, "headline": b["headline"], "bio": f"{b['name']} — {b['headline']}.",
            "skills": b["skills"], "rating": round(4.2 + random.random() * 0.7, 2),
            "review_count": 0, "solutions_count": 0, "deployments_count": 0,
            "earnings_usd": 0.0, "verified": random.random() > 0.3, "joined_at": now,
        })
        builders_map[b["email"]] = {"_id": bid, "name": b["name"]}
    print(f"[seed_v1] seeded {len(BUILDERS)} builders + 1 buyer + 1 admin")

    # ----- Anchor solutions (4) -----
    solutions = []
    for a in ANCHOR_SOLUTIONS:
        sid = "sol_" + uuid.uuid4().hex[:16]
        b = builders_map[a["builder_email"]]
        sol = {
            "_id": sid, "title": a["title"], "tagline": a["tagline"],
            "description": (f"{a['title']} — {a['tagline']}. " + DESCRIPTIONS[0].format(category=a["category"]))[:1500],
            "category": a["category"], "tech_stack": random.choice(TECHSTACKS), "tags": [a["category"].lower(), "production"],
            "price_usd": a["price_usd"], "license_model": "subscription", "deployment_maturity": "production",
            "demo_url": None, "repo_url": None, "screenshots": [],
            "builder_id": b["_id"], "builder_name": b["name"],
            "builder_rating": 4.8, "uptime_pct": 99.7,
            "clients_count": random.randint(8, 32), "trust_score": round(75 + random.random() * 22, 2),
            "v1_seed": True, "created_at": now - timedelta(days=random.randint(20, 200)), "updated_at": now,
        }
        solutions.append(sol)

    # ----- Procedural solutions (36) -----
    builder_emails = list(builders_map.keys())
    for i in range(36):
        category = random.choice(CATEGORIES)
        b_email = random.choice(builder_emails)
        b = builders_map[b_email]
        sid = "sol_" + uuid.uuid4().hex[:16]
        sol = {
            "_id": sid,
            "title": f"{category.split()[0]}{random.choice(['Forge','Pulse','Stream','Flow','Stack','Core','Hub','Pilot'])} {random.choice(['Pro','Cloud','One','Edge','OS'])} #{i+1:02d}",
            "tagline": random.choice(TAGLINES).format(industry=category, category=category),
            "description": random.choice(DESCRIPTIONS).format(category=category)[:1500],
            "category": category, "tech_stack": random.choice(TECHSTACKS), "tags": [category.lower(), random.choice(["multi-tenant","scalable","real-time","compliance","extensible"])],
            "price_usd": random.choice([900, 1800, 2500, 3500, 5400, 7800, 11500, 18000, 28000]),
            "license_model": random.choice(["subscription","perpetual","usage-based"]),
            "deployment_maturity": random.choice(["beta","production","enterprise"]),
            "demo_url": None, "repo_url": None, "screenshots": [],
            "builder_id": b["_id"], "builder_name": b["name"],
            "builder_rating": round(3.8 + random.random() * 1.2, 2),
            "uptime_pct": round(98.5 + random.random() * 1.4, 2),
            "clients_count": random.randint(0, 24),
            "trust_score": round(50 + random.random() * 47, 2),
            "v1_seed": True,
            "created_at": now - timedelta(days=random.randint(2, 365)), "updated_at": now,
        }
        solutions.append(sol)
    if solutions:
        await db.solutions.insert_many(solutions)
    # update builder solutions_count
    for sol in solutions:
        await db.builder_profiles.update_one({"_id": sol["builder_id"]}, {"$inc": {"solutions_count": 1}})
    print(f"[seed_v1] seeded {len(solutions)} solutions (4 anchor + {len(solutions)-4} procedural)")

    # ----- Requirements (15) -----
    sample_reqs = [
        ("Looking for a multi-tenant inventory system for our textile factory", "We run a textile mill in Surat handling fabric SKUs across 12 categories. Need real-time stock visibility, batch dyeing workflows, and supplier PO management. Budget flexible if the product is mature.", "Inventory Management", 15000, ["multi-tenant", "textile", "batch-dyeing"]),
        ("Need a CRM with strong revops automation", "B2B SaaS, ~50 reps. Want pipeline, sequences, revops dashboards, and good Stripe integration. Salesforce is too heavy.", "CRM", 9000, ["revops", "b2b", "automation"]),
        ("Replace our Excel-based HR system", "200-person team. Need leave, payroll, time-off, performance reviews. Indian compliance a plus.", "HR System", 5500, ["hris","payroll","compliance"]),
        ("Project management tool for distributed engineering team", "30-person remote eng team. Want Linear-like speed with Jira-grade reporting.", "Project Management", 7000, ["engineering","remote","reporting"]),
        ("E-commerce platform with subscription support", "D2C cosmetics brand. Need subscriptions, custom checkout, abandoned cart, and influencer affiliate workflows.", "E-commerce", 22000, ["d2c","subscription","affiliate"]),
        ("Finance suite for invoicing + AR/AP", "Services agency. Want invoicing, AR aging, AP automation, and clean QuickBooks export.", "Finance", 4200, ["invoicing","ar-ap"]),
        ("Analytics dashboard for our growth team", "We want to drop 5 BI tools and use one cohort/funnel/retention dashboard.", "Analytics", 6800, ["cohort","funnel","retention"]),
        ("Marketing automation for SaaS", "Lifecycle emails, in-app messaging, simple segmentation. Replace HubSpot.", "Marketing", 8500, ["lifecycle","email","segmentation"]),
        ("Internal ops dashboard for fintech compliance", "Need a back-office app for KYC + AML workflows with audit trail and role-based actions.", "Operations", 18000, ["kyc","aml","audit-log"]),
        ("Inventory + POS combo for a chain of cafés", "8-store café chain. Need real-time inventory + POS integration + low-stock alerts.", "Inventory Management", 8200, ["pos","retail","alerts"]),
        ("CRM tailored for real estate agencies", "Pipeline by property + buyer profiles + matchmaking. Mumbai market.", "CRM", 6300, ["realestate","pipeline"]),
        ("HR + payroll for a 70-person construction firm", "Field + office staff. Indian PF/ESI compliance + biometric attendance.", "HR System", 7400, ["construction","biometric"]),
        ("Project portfolio dashboard for a digital agency", "Track 40+ client projects with utilization, profitability, and forecast.", "Project Management", 12500, ["agency","profitability"]),
        ("Marketplace for handmade goods", "Looking to launch a vertical marketplace for Indian artisans with regional language support.", "E-commerce", 26000, ["marketplace","regional"]),
        ("Spend analytics across 5 departments", "Finance team wants vendor consolidation and AP anomaly detection.", "Finance", 10800, ["spend","vendor-mgmt"]),
    ]
    req_docs = []
    for title, desc, cat, budget, tags in sample_reqs:
        req_docs.append({
            "_id": str(uuid.uuid4()),
            "buyer_id": buyer_id, "buyer_name": BUYER["name"],
            "title": title, "description": desc, "category": cat,
            "budget_usd": float(budget), "timeline": random.choice(["urgent (4 weeks)", "Q1 2026", "next quarter", "flexible"]),
            "tags": tags, "match_count": random.randint(2, 18), "status": random.choice(["open","open","open","matched"]),
            "created_at": now - timedelta(days=random.randint(0, 14)), "updated_at": now,
        })
    if req_docs:
        await db.requirements.insert_many(req_docs)
    print(f"[seed_v1] seeded {len(req_docs)} requirements")

    # ----- Reviews (~80) -----
    review_phrases = [
        "Excellent integration, shipped in days.", "Builder was responsive and the docs were spot on.",
        "Saved us 4 months of engineering work.", "Pricing was fair for what we got.",
        "Some rough edges but overall worth it.", "Production-ready out of the box.",
        "Solid foundation, easy to extend.", "Support team responded within the hour.",
    ]
    review_docs = []
    n_target = 80
    while len(review_docs) < n_target:
        sol = random.choice(solutions)
        rating = random.choices([3,4,4,5,5,5], k=1)[0]
        review_docs.append({
            "_id": str(uuid.uuid4()),
            "transaction_id": None,  # historical reviews; not tied to a tx
            "solution_id": sol["_id"], "builder_id": sol["builder_id"],
            "buyer_id": buyer_id, "buyer_name": BUYER["name"],
            "rating": rating, "comment": random.choice(review_phrases),
            "created_at": now - timedelta(days=random.randint(1, 200)),
        })
    if review_docs:
        await db.reviews.insert_many(review_docs)
    # recompute builder ratings/review_counts
    pipeline = [
        {"$group": {"_id": "$builder_id", "avg": {"$avg": "$rating"}, "n": {"$sum": 1}}}
    ]
    async for row in db.reviews.aggregate(pipeline):
        await db.builder_profiles.update_one({"_id": row["_id"]}, {"$set": {
            "rating": round(float(row["avg"]), 2), "review_count": int(row["n"]),
        }})
        await db.solutions.update_many({"builder_id": row["_id"]}, {"$set": {"builder_rating": round(float(row["avg"]), 2)}})
    print(f"[seed_v1] seeded {len(review_docs)} reviews + recomputed builder ratings")

    # ----- 3 in-progress transactions -----
    aman_id = builders_map["aman@mergent.demo"]["_id"]
    priya_id = builders_map["priya@mergent.demo"]["_id"]
    rahul_id = builders_map["rahul@mergent.demo"]["_id"]
    txns = []
    for sid_title, b_id in [(solutions[0]["_id"], aman_id), (solutions[1]["_id"], aman_id), (solutions[3]["_id"], priya_id)]:
        sol = next(s for s in solutions if s["_id"] == sid_title)
        tid = str(uuid.uuid4())
        state = random.choice(["funded", "in_progress", "delivered"])
        txns.append({
            "_id": tid, "buyer_id": buyer_id, "buyer_name": BUYER["name"],
            "builder_id": b_id, "builder_name": next(b["name"] for e,b in builders_map.items() if b["_id"]==b_id),
            "solution_id": sol["_id"], "solution_title": sol["title"],
            "amount_usd": sol["price_usd"], "currency": "usd",
            "status": state, "state_history": [
                {"state": "initiated", "at": now - timedelta(days=7), "by": buyer_id},
                {"state": "funded", "at": now - timedelta(days=6), "by": "stripe:simulated"},
                {"state": "in_progress" if state != "funded" else "funded", "at": now - timedelta(days=3), "by": b_id},
            ],
            "match_integrity": "n/a", "origin_run_id": None,
            "stripe_session_id": f"sim_{tid[:18]}", "simulated_checkout": True,
            "created_at": now - timedelta(days=7), "updated_at": now,
        })
    # 2 released for review-base
    for sid_pick, b_id in [(solutions[0]["_id"], aman_id), (solutions[2]["_id"], rahul_id)]:
        sol = next(s for s in solutions if s["_id"] == sid_pick)
        tid = str(uuid.uuid4())
        txns.append({
            "_id": tid, "buyer_id": buyer_id, "buyer_name": BUYER["name"],
            "builder_id": b_id, "builder_name": next(b["name"] for e,b in builders_map.items() if b["_id"]==b_id),
            "solution_id": sol["_id"], "solution_title": sol["title"],
            "amount_usd": sol["price_usd"], "currency": "usd",
            "status": "released",
            "state_history": [{"state":"initiated","at": now - timedelta(days=30), "by": buyer_id},
                              {"state":"funded","at": now - timedelta(days=29), "by": "stripe:simulated"},
                              {"state":"in_progress","at": now - timedelta(days=25), "by": b_id},
                              {"state":"delivered","at": now - timedelta(days=15), "by": b_id},
                              {"state":"released","at": now - timedelta(days=10), "by": buyer_id}],
            "match_integrity": "n/a", "origin_run_id": None,
            "stripe_session_id": f"sim_{tid[:18]}", "simulated_checkout": True,
            "created_at": now - timedelta(days=30), "updated_at": now - timedelta(days=10),
        })
    await db.transactions.insert_many(txns)
    print(f"[seed_v1] seeded {len(txns)} transactions (3 in-progress + 2 released)")

    # ----- 2 deployments -----
    for sol in (solutions[0], solutions[1]):
        did = str(uuid.uuid4())
        ver = f"v{int((now - timedelta(days=3)).timestamp())}"
        await db.deployments.insert_one({
            "_id": did, "solution_id": sol["_id"], "solution_title": sol["title"],
            "builder_id": sol["builder_id"], "owner_id": buyer_id, "transaction_id": None,
            "environment": "production", "current_version": ver,
            "versions": [{"version": ver, "deployed_at": now - timedelta(days=3), "state": "live"}],
            "status": "live",
            "logs": [{"ts": (now - timedelta(days=3)).isoformat(), "level": "ok", "msg": f"Deployment live at https://app-{did[:8]}.mergent.preview"}],
            "state_history": [{"state": "created","at": now-timedelta(days=3)}, {"state":"live","at": now-timedelta(days=3)}],
            "simulated_infra": True, "created_at": now - timedelta(days=3), "updated_at": now - timedelta(days=3),
        })
    print("[seed_v1] seeded 2 live deployments")

    print("[seed_v1] DONE")
    print(f"[seed_v1] BUYER  login: {BUYER['email']} / {DEMO_PASSWORD}")
    print(f"[seed_v1] BUILDER login: {BUILDERS[0]['email']} / {DEMO_PASSWORD}")
    print(f"[seed_v1] ADMIN  login: {ADMIN['email']} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
