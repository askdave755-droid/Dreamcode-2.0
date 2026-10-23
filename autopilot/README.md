# Autopilot for Small Trades

Admin autopilot for one-van Canadian trade businesses. The phone gets answered, the job gets booked, the invoice goes out, the money gets chased, the review gets asked for, and the customer gets a rebooking text — while the owner is on a roof, behind a snowblower, or holding a dog.

One generic core. Each business plugs in a profile, and its own assistant is generated from that profile.

```
Caller ──phone──▶ Vapi assistant ──tool webhooks──▶ FastAPI ──▶ Postgres
                        ▲                              │
                        └── prompt rendered from       ├──▶ Twilio SMS (owner + customer)
                            the business profile       ├──▶ Stripe payment links
                                                       └──▶ scheduler (reminders, chasers,
                                                            reviews, rebooking)
Owner ──texts cell──▶ Twilio ──webhook──▶ FastAPI (commands: TODAY, DONE 3, PAID INV-1004)
Owner ──browser────▶ phone-first web app at /
```

## What is actually built

| Plan step | Status | Where |
|---|---|---|
| 1. Data model, tenant ID on every row | ✅ | `app/models.py` |
| 2. Business profile setup (< 5 min) | ✅ Web wizard + guided text onboarding | `app/services/onboarding.py`, `app/routers/auth.py` |
| 3. Master prompt with business placeholders | ✅ | `app/prompt.py` |
| 4. Voice agent + webhooks (book / availability / escalate) | ✅ Vapi, with a Bland adapter | `app/routers/voice.py`, `app/services/voice_agent.py` |
| 5. Dedicated number per business + forwarding guidance | ✅ field + docs | `docs/GO_LIVE.md` |
| 6. Jobs, availability rules, owner + customer texts | ✅ | `app/availability.py`, `app/services/jobs.py` |
| 7. Invoicing with GST/QST/HST, payment link, chasers | ✅ Stripe + e-Transfer | `app/services/billing.py`, `app/routers/payments.py` |
| 8. Review request after payment | ✅ | `app/services/scheduler.py` |
| 9. Rebooking texts | ✅ | same |
| 10. Phone-first owner experience | ✅ SMS commands + mobile web app | `app/services/commands.py`, `app/static/` |
| 11. Billing the business (Starter/Pro) | ✅ Stripe Checkout + webhook lifecycle | `app/plans.py`, `app/routers/payments.py` |
| 12. Pilot instrumentation | ✅ metrics in the dashboard | `docs/PILOT.md` |

Every integration is optional. With no keys the app runs in **dry-run**: texts are written to the message log instead of sent, payment pages have a demo "Pay" button, and the Vapi assistant payload is built but not created. That is why the demo works on a fresh clone.

## Quickstart

```bash
cd autopilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>. In demo mode the app signs you straight into the seeded demo business — a snow-removal company in Saint-Georges, QC. Nothing to click, nothing to install.

* `/demo` — shareable link that signs in and lands in the app.
* `/?auth=1` — the real sign-in screen (phone + code). The demo owner is `(418) 555-0199` and the code is shown on screen.
* `More → Sign out` returns to that sign-in screen.

Set `DEMO_MODE=false` in production to disable the demo link and auto-entry.

Try the whole loop:

1. **Today** → the job waiting on the owner → **Confirm slot** → pick one. Owner and customer texts are logged in **Latest texts**.
2. **Done → invoice** on a confirmed job. Choose amount and payment method; a tax-correct invoice and payment link are created and the customer is texted.
3. Open the **Pay page** for the invoice, press the demo pay button. Receipt goes out; review and rebooking texts are scheduled by the scheduler (`POST /internal/run-scheduler`).
4. **Assistant** → **View full prompt** to see exactly what the voice agent receives for this business.
5. Text commands: simulate an inbound SMS with curl (below) or [configure Twilio](#texting-twilio).

```bash
# Owner texts "DONE 3 145" from the owner's cell to the business line
curl -X POST localhost:8000/webhooks/twilio/sms \
  -d "From=%2B14185550199&To=%2B14185550123&Body=DONE+3+145&MessageSid=SM1&NumMedia=0"
```

Run the tests:

```bash
pytest -q          # 45 tests: tax, availability, booking, invoicing, commands, webhooks, tenancy
```

## The job lifecycle

```
requested ──confirm──▶ confirmed ──DONE──▶ done ──pay──▶ paid
     │                     │                                  │
     └──needs_confirmation─┘ (slot unavailable)         review + rebook scheduled
```

Rules that are enforced in code, not just in the prompt:

* A job is only `confirmed` after `slot_is_available()` passes. A caller is never told they are booked on a slot we cannot honour — it becomes `needs_confirmation` with a callback promise.
* Availability is business hours + service duration + 15-minute travel buffer, computed in the business's timezone (`America/Toronto` by default, per province).
* `mark_paid` is idempotent. Stripe retries webhooks; a retried event cannot send a second receipt.
* Opted-out customers are skipped for every automated text, and the skip is logged.
* Invoices store a tax breakdown (GST 5% + QST 9.975% in QC, HST 13–15%, GST 5%) so remittance is a sum, not a guess.

## Data model

| Table | Purpose | Tenant key |
|---|---|---|
| `businesses` | profile, services, hours, tax, plan, voice config | itself |
| `customers` | caller/customer record + consent + opt-out | `business_id` |
| `jobs` | booking, slot, estimate/final price, follow-up timestamps | `business_id` |
| `invoices` | line items, tax breakdown, payment link, chasers | `business_id` |
| `messages` | every SMS in/out with template + provider status | `business_id` |
| `calls` | transcript, summary, tool calls, recording URL | `business_id` |
| `webhook_events` | provider idempotency ledger | — |
| `login_codes` | hashed OTPs for owner login | `business_id` |
| `onboarding_drafts` | text-message onboarding in progress | phone |

Every tenant-scoped query filters on `business_id`; `tests/test_api.py::test_tenant_isolation` asserts a business cannot fetch another's job. Postgres in production, SQLite locally — the `UTCDateTime` type decorator keeps timezone handling identical on both.

## Text commands

Owners text their own business line. Customers text the same line; the app tells them apart by number.

| From | Command | Result |
|---|---|---|
| Owner | `TODAY` | Today + next jobs + unpaid count |
| Owner | `DONE 3` / `DONE 3 145` | Invoice job 3 at the estimated / given price |
| Owner | `QUOTE 3 145` | Set the price (re-sends the invoice if one exists) |
| Owner | `PAID INV-1004` | Mark an e-Transfer received |
| Owner | `CONFIRM 3 tomorrow 9am` | Confirm/reschedule with an availability check |
| Owner | `CANCEL 3`, `OPEN`, `PLAN`, `HELP` | Cancel, free slots, billing, command list |
| Customer | `C`, `R`, `BOOK`, `PAID`, `STOP`, `START` | Confirm, reschedule, rebook, "I paid", opt out/in |
| Anyone | anything else | Relayed to the owner as a text |

## API and webhooks

| Method | Path | Who calls it |
|---|---|---|
| `POST` | `/webhooks/vapi` | Vapi: `assistant-request`, `tool-calls`, `end-of-call-report`, `status-update` |
| `POST` | `/webhooks/bland` | Bland pathway webhook (tools + call reports) |
| `POST` | `/webhooks/twilio/sms` | Inbound texts, replies with TwiML |
| `POST` | `/webhooks/twilio/status` | Delivery receipts |
| `POST` | `/webhooks/stripe` | Invoice paid, subscription lifecycle (idempotent) |
| `POST` | `/internal/run-scheduler` | Railway cron (`X-Cron-Secret`) |
| `GET` | `/api/dashboard`, `/api/jobs`, `/api/invoices`, `/api/customers`, `/api/messages`, `/api/calls` | Owner app |
| `GET` | `/api/agent/prompt`, `POST /api/agent/provision` | Owner app / provisioning |
| `GET` | `/api/billing/summary`, `/api/billing/plans`, `POST /api/billing/checkout` | Owner app |
| `GET` | `/pay/{invoice_id}` | Customer payment page |
| `GET` | `/health`, `/docs` | Ops, OpenAPI |

Full request/response shapes: [`docs/API.md`](docs/API.md).

## Going live

The short version — the detailed runbook with provider setup is in [`docs/GO_LIVE.md`](docs/GO_LIVE.md).

1. Deploy with the `Dockerfile` to Railway, attach Postgres, set `DATABASE_URL` + `SECRET_KEY`, set `DEMO_MODE=false`.
2. Twilio: buy a Canadian number per business, point **Messaging → webhook** at `/webhooks/twilio/sms` and **Status callback** at `/webhooks/twilio/status`. Register the number for A2P 10DLC / Canadian SMS as required.
3. Vapi: set `VAPI_API_KEY`, `VAPI_WEBHOOK_SECRET`, then `POST /api/agent/provision` for each business. Vapi's server URL is `/webhooks/vapi`; the assistant carries `metadata.business_id` so the webhook knows which tenant answered.
4. Forwarding: owner dials their carrier's forward-on-no-answer code to the business line. Forward *conditional*, never unconditional — the owner must still be able to call out.
5. Stripe: create the two subscription prices, set `STRIPE_*`, add a webhook to `/webhooks/stripe` for `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`.
6. Set `ENABLE_SCHEDULER=true` on a single replica (or use Railway cron hitting `/internal/run-scheduler` with `CRON_SECRET`).

## Compliance

Disclosure, CASL consent + opt-out, recording consent, Quebec Law 25, tax, and what the code enforces vs what needs a human: [`docs/COMPLIANCE.md`](docs/COMPLIANCE.md). The customer-facing privacy draft is served at `/static/privacy.html`.

## Decisions and open questions

Which trade to lead with, Vapi vs Bland with current per-minute math, pricing tiers, naming, and how to find the first three pilots — all written up with numbers in [`docs/DECISIONS.md`](docs/DECISIONS.md). Pilot plan and metrics: [`docs/PILOT.md`](docs/PILOT.md).

## Known limits (deliberate, for v1)

* No Google Calendar sync. The jobs table is the calendar; two-way sync is a later integration.
* No crew scheduling, routing, or dispatch board — one business, one owner, small team.
* Availability is a simple rule engine, not a constraint solver. It is honest, explainable, and easy for an owner to reason about.
* No invoice PDF (the payment page and texted summary are the invoice for now).
* Schema is created on boot (`create_all`). Add Alembic before the first production schema change.
* The AI never quotes firm prices; the owner confirms. This is a product constraint, not a missing feature.
