# API reference

Base URL: `PUBLIC_BASE_URL`. Interactive schema: `/docs`.

All `/api/*` routes are tenant-scoped through the owner session cookie
(`autopilot_session`, HttpOnly, 30 days). In `DEMO_MODE` only, an
`X-Demo-Business: <business id>` header also works.

Money is always **integer cents**, currency CAD.

---

## Auth and onboarding

### `GET /api/auth/options`
Trade presets, province → tax profile map, default hours.

### `POST /api/auth/signup`
```json
{
  "business_name": "Lévesque Déneige",
  "owner_name": "Marc Lévesque",
  "owner_phone": "(418) 555-0199",
  "trade": "snow_removal",
  "city": "Saint-Georges",
  "province": "QC",
  "service_area": "Beauce",
  "review_url": "https://g.page/r/...",
  "etransfer_email": "marc@example.com",
  "greeting": null,
  "hst_enabled": true
}
```
`201`-style body: `{ "business": {...}, "token": "<only in demo mode>" }` and sets the session cookie.
Creates the business, applies the trade's service catalogue, derives the tax profile from the province, and texts the owner a welcome message.

### `POST /api/auth/request-code` `{ "phone": "..." }`
Always returns `{ "sent": true }`. In demo mode includes `demo_code`. In live mode texts a 6-digit code valid for 10 minutes.

### `POST /api/auth/verify` `{ "phone": "...", "code": "123456" }`
Sets the session cookie. `400` on invalid/expired code.

### `POST /api/auth/demo` (GET also accepted)
Demo tenancy only; `404` when `DEMO_MODE=false`.

### `POST /api/auth/logout`

---

## Profile

### `GET /api/me`
Full business profile including services, hours, tax profile and rates, integrations state, plan, and timezone.

### `PATCH /api/me`
Any subset of: `name`, `owner_name`, `owner_phone`, `owner_email`, `city`, `province`, `service_area`, `phone_number`, `greeting`, `tone`, `language`, `hours`, `services`, `review_url`, `review_delay_days`, `rebook_enabled`, `hst_enabled`, `tax_profile`, `tax_number`, `etransfer_email`, `sms_footer`.

`hours` shape: `{"mon": ["07:00","18:00"], "sun": null}`.

`services` item shape:
```json
{
  "key": "driveway",
  "name": "Driveway clearing",
  "duration_min": 45,
  "price_min_cents": 4500,
  "price_max_cents": 9500,
  "unit": "per visit",
  "rebook_after_days": 30,
  "notes": "double driveway more"
}
```

---

## Dashboard and jobs

### `GET /api/dashboard`
```json
{
  "business": {...},
  "today": [job],
  "upcoming": [job],
  "needs_action": [job],
  "open_invoices": [invoice],
  "stats": {
    "jobs_total": 6, "calls_total": 4, "calls_recovered": 3, "recovered_rate": 0.75,
    "revenue_cents": 8623, "outstanding_cents": 5174, "avg_days_to_pay": 2.4,
    "reviews_requested": 1, "minutes_used": 12
  },
  "messages": [message],
  "open_slots": [{"date": "2026-10-26", "label": "Mon Oct 26", "slots": ["...ISO..."]}],
  "demo_mode": true
}
```

### `GET /api/jobs?status=confirmed,needs_confirmation&limit=50`
### `POST /api/jobs`
```json
{
  "customer_name": "Chantal Gagnon",
  "customer_phone": "418-555-0111",
  "address": "1240 3e Avenue, Saint-Georges",
  "service_key": "driveway",
  "preferred_start": "2026-10-26T10:00:00-04:00",
  "requested_for": null,
  "notes": "gate code 1234",
  "source": "owner"
}
```
Returns the job plus `warnings: ["slot_taken"]` when the slot could not be confirmed.

### `GET /api/jobs/{id or number}`
Job + customer + invoice + linked call summaries and transcripts.

### `PATCH /api/jobs/{id}` — `price_final_cents`, `notes`, `requested_for`
### `POST /api/jobs/{id}/confirm` — `{ "start": "2026-10-27T09:00:00-04:00" }`
`409` with `slot_taken`, `outside_business_hours`, `closed_that_day`, or `too_soon`.
### `POST /api/jobs/{id}/reschedule` — same body
### `POST /api/jobs/{id}/cancel`
### `POST /api/jobs/{id}/done`
```json
{ "amount_cents": 14500, "method": "stripe", "already_paid": false, "paid_via": "cash" }
```
Creates the invoice, texts the customer the payment link (or e-Transfer instructions), returns `{ "job": {...}, "invoice": {...} }`. Idempotent per job.

---

## Invoices

### `GET /api/invoices?status=sent,overdue`
### `GET /api/invoices/{id or number}`
Includes `line_items`, `tax_breakdown`, `payment_url`, chaser count.
### `POST /api/invoices/{id}/send` — (re)issue and text the customer
### `POST /api/invoices/{id}/paid` — `{ "via": "etransfer" | "stripe" | "cash" | "cheque" }`
Idempotent; sends a receipt and schedules the review + rebooking.

### `GET /pay/{invoice_id}` (public HTML)
Customer payment page: totals, tax lines, Stripe button (live) or demo button (dry-run), e-Transfer instructions.

---

## Assistant

### `GET /api/agent/prompt`
```json
{
  "system_prompt": "…rendered master prompt…",
  "first_message": "…",
  "tools": [ …Vapi function definitions… ],
  "webhook_url": "https://host/webhooks/vapi",
  "assistant_payload": { …full Vapi assistant body… }
}
```

### `POST /api/agent/provision`
Creates or updates the Vapi assistant. Without `VAPI_API_KEY` returns:
```json
{ "provisioned": false, "mode": "dry_run", "reason": "VAPI_API_KEY not configured", "payload": {...} }
```

---

## Billing (of the business)

### `GET /api/billing/plans` / `GET /api/plans`
Starter $79 (200 min), Pro $149 (600 min), overage $0.49 / $0.39 per minute.

### `GET /api/billing/summary`
Plan, minutes used/included, overage, next amount, trial end, `dry_run`.

### `POST /api/billing/checkout` — `{ "plan": "starter" | "pro" }`
Returns a Stripe Checkout URL. In dry-run it switches the plan on the record and returns `{ "demo": true }`.

---

## Webhooks

### `POST /webhooks/vapi`  (header `x-vapi-secret`)
Events handled: `assistant-request`, `tool-calls`, `end-of-call-report`, `status-update`.

Tool call request:
```json
{
  "message": {
    "type": "tool-calls",
    "call": {
      "id": "call_123",
      "phoneNumber": { "number": "+14185550123" },
      "customer": { "number": "+14185550111" }
    },
    "toolCallList": [
      { "id": "tc_1", "function": { "name": "check_availability", "arguments": "{\"service_key\":\"driveway\"}" } }
    ]
  }
}
```
Response:
```json
{ "results": [ { "toolCallId": "tc_1", "result": "{\"available\":true,...}" } ] }
```

Tools: `check_availability`, `book_job`, `escalate_to_owner`, `get_service_list`.

`book_job` returns `success`, `job_number`, `status` (`confirmed` or `needs_confirmation`), `when`, and `say_to_caller` — the assistant must read that back rather than improvise.

End-of-call reports store duration, summary, transcript, recording URL, and tool history; if no job was booked and nothing was escalated, the owner gets a `MISSED CALL` text.

### `POST /webhooks/bland`
Same tools, Bland shape (`action` / `parameters`), plus call reports.

### `POST /webhooks/twilio/sms` (form-encoded)
`From`, `To`, `Body`, `MessageSid`. Returns TwiML with the reply. Signature validated against `PUBLIC_BASE_URL` and the request URL.

### `POST /webhooks/twilio/status`
Updates `messages.status` by provider SID.

### `POST /webhooks/stripe`
Signature verified with `STRIPE_WEBHOOK_SECRET`; each `event.id` is stored once in `webhook_events`. Duplicate events return `{ "received": true, "duplicate": true }`.

### `POST /internal/run-scheduler` (header `X-Cron-Secret`)
Runs due reminders, chasers, reviews, rebooks, and trial notices. Returns counts per task.

---

## Health

### `GET /health`
```json
{
  "status": "ok",
  "environment": "production",
  "database": "ok",
  "integrations": { "sms": "twilio", "payments": "stripe", "voice": "vapi" },
  "scheduler": "enabled",
  "demo_mode": false
}
```
