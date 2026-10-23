"""HTTP-level tests: auth, dashboard, tenant isolation, and webhooks."""
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app import models
from app.services import onboarding
from tests.helpers import unique_number

TZ = ZoneInfo("America/Toronto")


def _slot(days=3, hour=10):
    day = date.today() + timedelta(days=days)
    while day.weekday() == 6:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, hour, tzinfo=TZ).isoformat()


def _login(client, business):
    response = client.post(
        "/api/auth/request-code", json={"phone": business.owner_phone}
    )
    code = response.json().get("demo_code")
    assert code, "demo mode should return the code"
    verify = client.post(
        "/api/auth/verify", json={"phone": business.owner_phone, "code": code}
    )
    assert verify.status_code == 200
    return verify


def test_health_reports_integrations(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["integrations"]["sms"] == "dry_run"


def test_signup_creates_tenant_and_session(client):
    response = client.post(
        "/api/auth/signup",
        json={
            "business_name": "API Lawn Co",
            "owner_name": "Dana Roy",
            "owner_phone": "(418) 555-0301",
            "trade": "lawn_care",
            "city": "Lévis",
            "province": "QC",
            "etransfer_email": "dana@example.com",
        },
    )
    assert response.status_code == 200, response.text
    business = response.json()["business"]
    assert business["owner_phone"] == "+14185550301"
    assert business["trade"] == "lawn_care"

    me = client.get("/api/me").json()
    assert me["id"] == business["id"]
    assert me["tax_profile"] == "qc_gst_qst"
    assert len(me["services"]) == 4


def test_signup_rejects_bad_phone(client):
    response = client.post(
        "/api/auth/signup",
        json={
            "business_name": "Bad Phone",
            "owner_name": "X",
            "owner_phone": "123",
            "trade": "snow_removal",
        },
    )
    assert response.status_code == 400


def test_otp_login_and_logout(client, business):
    _login(client, business)
    assert client.get("/api/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401


def test_expired_or_wrong_code_is_rejected(client, business):
    client.post("/api/auth/request-code", json={"phone": business.owner_phone})
    bad = client.post(
        "/api/auth/verify", json={"phone": business.owner_phone, "code": "000000"}
    )
    assert bad.status_code == 400


def test_dashboard_and_booking_flow_over_http(client, business):
    _login(client, business)
    created = client.post(
        "/api/jobs",
        json={
            "customer_name": "HTTP Customer",
            "customer_phone": "418-555-0322",
            "address": "100 Rue HTTP",
            "service_key": "driveway",
            "preferred_start": _slot(),
        },
    )
    assert created.status_code == 201, created.text
    job = created.json()
    assert job["status"] == "confirmed"

    dash = client.get("/api/dashboard").json()
    assert any(item["id"] == job["id"] for item in dash["upcoming"] + dash["today"])

    done = client.post(f"/api/jobs/{job['id']}/done", json={"amount_cents": 9000})
    assert done.status_code == 200
    invoice = done.json()["invoice"]
    assert invoice["total_cents"] == 10348

    paid = client.post(f"/api/invoices/{invoice['id']}/paid", json={"via": "etransfer"})
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"


def test_tenant_isolation(client, business, db):
    other = onboarding.create_business(
        db,
        name="Other Tenant",
        owner_name="Other Owner",
        owner_phone=unique_number(),
        trade="cleaning",
        province="ON",
        phone_number=unique_number(),
    )
    start = datetime.now(timezone.utc) + timedelta(days=3)
    job = models.Job(
        business_id=other.id,
        number=1,
        service_key="deep_clean",
        service_name="Deep clean",
        status="confirmed",
        scheduled_start=start,
        scheduled_end=start + timedelta(hours=2),
    )
    db.add(job)
    db.commit()

    _login(client, business)
    assert client.get(f"/api/jobs/{job.id}").status_code == 404
    assert client.get("/api/jobs").json() == []


def test_voice_tool_calls_book_a_job(client, db, business):
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "vapi-test-1",
                "phoneNumber": {"number": business.phone_number},
                "customer": {"number": "+14185550555"},
            },
            "toolCallList": [
                {
                    "id": "tc-1",
                    "function": {
                        "name": "check_availability",
                        "arguments": json.dumps({"service_key": "driveway", "days_ahead": 5}),
                    },
                }
            ],
        }
    }
    response = client.post("/webhooks/vapi", json=payload)
    assert response.status_code == 200
    results = response.json()["results"]
    assert results[0]["toolCallId"] == "tc-1"
    availability = json.loads(results[0]["result"])
    assert availability["available"] is True

    book_payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "vapi-test-1",
                "phoneNumber": {"number": business.phone_number},
                "customer": {"number": "+14185550555"},
            },
            "toolCallList": [
                {
                    "id": "tc-2",
                    "function": {
                        "name": "book_job",
                        "arguments": json.dumps(
                            {
                                "customer_name": "Voice Caller",
                                "customer_phone": "4185550555",
                                "address": "42 Voie Vocale",
                                "service_key": "driveway",
                                "preferred_start": _slot(),
                            }
                        ),
                    },
                }
            ],
        }
    }
    booked = client.post("/webhooks/vapi", json=book_payload)
    outcome = json.loads(booked.json()["results"][0]["result"])
    assert outcome["success"] is True
    assert outcome["job_number"] >= 1

    end = {
        "message": {
            "type": "end-of-call-report",
            "call": {
                "id": "vapi-test-1",
                "phoneNumber": {"number": business.phone_number},
                "customer": {"number": "+14185550555"},
                "durationSeconds": 154,
            },
            "analysis": {"summary": "Caller booked a driveway clearing."},
            "artifact": {"transcript": "AI: hello\nCaller: hi"},
        }
    }
    assert client.post("/webhooks/vapi", json=end).status_code == 200
    call = (
        db.query(models.Call)
        .filter(models.Call.provider_call_id == "vapi-test-1")
        .first()
    )
    db.refresh(call)
    assert call.status == "completed"
    assert call.summary.startswith("Caller booked")
    assert call.job_id is not None


def test_voice_escalation_texts_owner(client, db, business):
    before = db.query(models.Message).filter(
        models.Message.business_id == business.id,
        models.Message.template == "escalation_emergency",
    ).count()
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "vapi-test-2",
                "phoneNumber": {"number": business.phone_number},
                "customer": {"number": "+14185550556"},
            },
            "toolCallList": [
                {
                    "id": "tc-3",
                    "function": {
                        "name": "escalate_to_owner",
                        "arguments": json.dumps(
                            {
                                "summary": "Driveway blocked, ambulance needs access",
                                "urgency": "emergency",
                                "caller_phone": "4185550556",
                            }
                        ),
                    },
                }
            ],
        }
    }
    response = client.post("/webhooks/vapi", json=payload)
    assert response.status_code == 200
    after = db.query(models.Message).filter(
        models.Message.business_id == business.id,
        models.Message.template == "escalation_emergency",
    ).count()
    assert after == before + 1


def test_inbound_sms_owner_command_returns_twiml(client, db, business):
    response = client.post(
        "/webhooks/twilio/sms",
        data={
            "From": business.owner_phone,
            "To": business.phone_number,
            "Body": "TODAY",
            "MessageSid": "SM-test-1",
            "NumMedia": "0",
        },
    )
    assert response.status_code == 200
    assert "<Response>" in response.text
    inbound = (
        db.query(models.Message)
        .filter(models.Message.provider_sid == "SM-test-1")
        .first()
    )
    assert inbound is not None and inbound.direction == "in"


def test_inbound_sms_from_unknown_number_creates_lead(client, db, business):
    response = client.post(
        "/webhooks/twilio/sms",
        data={
            "From": "+14185550999",
            "To": business.phone_number,
            "Body": "do you do driveways in Beauceville?",
            "MessageSid": "SM-test-2",
            "NumMedia": "0",
        },
    )
    assert response.status_code == 200
    customer = (
        db.query(models.Customer)
        .filter(
            models.Customer.business_id == business.id,
            models.Customer.phone == "+14185550999",
        )
        .first()
    )
    assert customer is not None


def test_pay_page_and_demo_completion(client, db, business):
    start = datetime.now(timezone.utc) + timedelta(days=3)
    job = models.Job(
        business_id=business.id,
        number=55,
        service_key="driveway",
        service_name="Driveway clearing",
        status="done",
        scheduled_start=start,
        scheduled_end=start + timedelta(minutes=45),
    )
    db.add(job)
    db.commit()
    invoice = models.Invoice(
        business_id=business.id,
        job_id=job.id,
        number="INV-7777",
        status="sent",
        subtotal_cents=5000,
        tax_cents=749,
        total_cents=5749,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.commit()

    page = client.get(f"/pay/{invoice.id}")
    assert page.status_code == 200
    assert "INV-7777" in page.text

    done = client.post(f"/pay/{invoice.id}/complete")
    assert done.status_code == 200
    db.refresh(invoice)
    assert invoice.status == "paid"


def test_stripe_webhook_is_idempotent(client, db, business):
    customer = models.Customer(
        business_id=business.id, name="Stripe Payer", phone="+14185550777"
    )
    db.add(customer)
    db.commit()
    invoice = models.Invoice(
        business_id=business.id,
        customer_id=customer.id,
        number="INV-8888",
        status="sent",
        subtotal_cents=4000,
        tax_cents=599,
        total_cents=4599,
        issued_at=datetime.now(timezone.utc),
    )
    db.add(invoice)
    db.commit()

    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"invoice_id": invoice.id, "business_id": business.id},
                "amount_total": 4599,
            }
        },
    }
    first = client.post("/webhooks/stripe", json=event)
    second = client.post("/webhooks/stripe", json=event)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json().get("duplicate") is True
    db.refresh(invoice)
    assert invoice.status == "paid"
    receipts = (
        db.query(models.Message)
        .filter(
            models.Message.business_id == business.id,
            models.Message.template == "paid_receipt",
            models.Message.invoice_id == invoice.id,
        )
        .count()
    )
    assert receipts == 1


def test_scheduler_endpoint_requires_secret_when_configured(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cron_secret", "s3cret")
    assert client.post("/internal/run-scheduler").status_code == 401
    ok = client.post("/internal/run-scheduler", headers={"X-Cron-Secret": "s3cret"})
    assert ok.status_code == 200
    assert set(ok.json().keys()) == {"reminders", "chases", "reviews", "rebook", "trial"}


def test_agent_prompt_endpoint_renders_business_details(client, business):
    _login(client, business)
    body = client.get("/api/agent/prompt").json()
    assert "Test Snow Co" in body["system_prompt"]
    assert "disclose" in body["system_prompt"].lower() or "AI assistant" in body["system_prompt"]
    assert body["assistant_payload"]["serverUrl"].endswith("/webhooks/vapi")
    assert body["assistant_payload"]["metadata"]["business_id"] == business.id


def test_index_serves_cache_busted_assets(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "__ASSET_V__" not in response.text
    assert "/static/app.js?v=" in response.text
    assert "/static/app.css?v=" in response.text
    assert response.headers.get("cache-control") == "no-store"


def test_demo_link_signs_in_and_lands_in_the_app(client, business):
    response = client.get("/demo", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "autopilot_session" in response.headers.get("set-cookie", "")

    # The cookie from /demo is enough to use the app.
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["demo_mode"] is True


def test_demo_link_is_hidden_outside_demo_mode(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", False)
    assert client.get("/demo", follow_redirects=False).status_code == 404
    assert client.post("/api/auth/demo").status_code == 404
