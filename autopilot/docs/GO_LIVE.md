# Go-live runbook

Everything below assumes the app is deployed and reachable at `PUBLIC_BASE_URL`.
Work through it in order; each step is independently verifiable.

## 0. Deploy the API

```bash
railway up            # or connect the repo, root directory: autopilot/
```

Railway settings:

| Setting | Value |
|---|---|
| Build | Dockerfile at `autopilot/Dockerfile` |
| Health check | `/health` |
| Variables | `DATABASE_URL`, `SECRET_KEY`, `PUBLIC_BASE_URL`, `ENVIRONMENT=production`, `DEMO_MODE=false` |
| Replicas | 1 while `ENABLE_SCHEDULER=true` |

Verify:

```bash
curl https://<host>/health
# {"status":"ok", "database":"ok", "integrations":{"sms":"dry_run",...}}
```

Keep `DEMO_MODE=false` in production: it disables the one-click demo login and stops exposing OTP codes in API responses.

## 1. Twilio (texting)

1. Buy a Canadian local number for each business. Keep one number per tenant — inbound routing depends on it.
2. Set the number's **A message comes in** webhook (HTTP POST) to
   `https://<host>/webhooks/twilio/sms`, and **Status callback URL** to
   `https://<host>/webhooks/twilio/status`.
3. Register for A2P messaging as your carrier requires (Canadian numbers increasingly require a registered brand/campaign). Talk to Twilio support early — this is the most common launch delay.
4. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, and keep `VERIFY_TWILIO_SIGNATURE=true`.
5. `/health` should now report `"sms":"twilio"`.
6. Test by texting `HELP` from the owner's cell to the business number. You should get the command list back and see both messages in `/api/messages`.

Message segments bill separately. Keep owner job alerts under 160 characters where practical; customer texts with a payment link will be 2 segments.

## 2. Vapi (voice)

1. Create the Vapi account and set `VAPI_API_KEY` and `VAPI_WEBHOOK_SECRET` in Railway.
2. For each business, call `POST /api/agent/provision` (from the app's **Assistant → Provision assistant**, or with the owner's session cookie). This creates the assistant from the business profile and stores `vapi_assistant_id`.
3. Point the Vapi phone number at that assistant. Vapi number creation:

```bash
curl -X POST https://api.vapi.ai/phone-number \
  -H "Authorization: Bearer $VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"provider":"vapi","assistantId":"<assistant id>","number":"+14185550123"}'
```

Prefer importing the Twilio number into Vapi rather than buying a second number, so calls and texts share one line. In that case set the Twilio number's **voice webhook** to Vapi's SIP URI as documented by Vapi, and keep the Twilio **messaging** webhook pointed at us.

4. Vapi's server URL is set on the assistant to `https://<host>/webhooks/vapi` with the secret header. Verify in Vapi's call logs that `tool-calls` returns 200.
5. Test in this order, with your own phone:
   * Call and ask "are you a robot?" → must disclose it is an AI.
   * Book a job → confirm the slot appears in **Today** and both texts arrive.
   * Call again and ask for a firm price on a big commercial job → must escalate, not quote.
   * Say "my driveway is blocked and an ambulance needs in" → owner must get the `URGENT` text.
   * Call after hours → callback promise, owner text with the number.

Latency note: anything over ~1.2 s of silence makes callers hang up. Keep the model warm, prefer `gpt-4o-mini`, and use a voice provider in the same region (`us-east` / `ca-central` if available).

## 3. Forwarding

Owners keep their existing number and forward it. Two rules:

* Forward **only when busy or unanswered** (typically 4–5 rings), never unconditional. Unconditional forwarding breaks the owner's ability to place calls and to text from their cell.
* Tell customers the new number slowly. Update the Google Business Profile, truck, and invoices when the AI line proves itself.

Carrier codes for conditional forwarding vary (Bell, Telus, Rogers, Vidéotron all differ). Have the owner call their carrier and say: "forward when busy or after 5 rings to this number". Do not publish carrier codes without verifying them for that province and carrier.

## 4. Stripe

1. Two recurring prices: Starter $79 CAD/month, Pro $149 CAD/month. Put the price IDs in `STRIPE_SUBSCRIPTION_PRICE_ID` and `STRIPE_SUBSCRIPTION_PRICE_ID_PRO`.
2. Webhook to `https://<host>/webhooks/stripe`, events:
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted`.
3. Job invoices use Stripe Checkout in `payment` mode with `metadata.invoice_id`; nothing else is needed for a customer to pay.
4. If the business takes Interac e-Transfer, set its `etransfer_email`; invoices then text the address and the owner confirms with `PAID`.
5. Card payments settle to the platform account. If you want each business to receive funds directly, use Stripe Connect later (destination charges) — out of scope for the pilot, and the reason the pilot pricing includes a manual reconciliation step.

## 5. Scheduler

One replica:

```
ENABLE_SCHEDULER=true
SCHEDULER_INTERVAL_SECONDS=300
```

More than one replica, or a serverless host:

```
ENABLE_SCHEDULER=false
CRON_SECRET=<random>
```

Railway cron: every 5 minutes, `POST https://<host>/internal/run-scheduler` with header `X-Cron-Secret: <CRON_SECRET>`.

The scheduler sends: day-before reminders, payment chasers (max 3, 4 days apart), review requests (2 days after payment), rebooking texts, and trial-ending notices. Every task checks a timestamp first, so running it twice is safe.

## 6. Per-business onboarding checklist

- [ ] Business profile created (trade, services, price ranges, hours, service area)
- [ ] Tax profile correct for the province, tax number recorded
- [ ] Dedicated number live, messaging + voice webhooks set
- [ ] Assistant provisioned, prompt spot-checked for the business name and ranges
- [ ] Owner's cell verified as `owner_phone` (that is what unlocks commands and escalations)
- [ ] Google review link saved
- [ ] e-Transfer email saved if used
- [ ] Test call + test booking + test invoice completed with the owner watching
- [ ] Owner shown `TODAY`, `DONE`, `PAID` commands on their own phone
- [ ] Forwarding confirmed: call the old number, do not answer, confirm the AI picks up

## 7. Smoke test script

```bash
HOST=https://<host>
OWNER=+14185550199
LINE=+14185550123

curl -s $HOST/health | jq
curl -s -X POST $HOST/webhooks/twilio/sms -d "From=$OWNER&To=$LINE&Body=TODAY&MessageSid=SM$RANDOM&NumMedia=0"
curl -s -X POST $HOST/webhooks/vapi -H 'Content-Type: application/json' \
  -d '{"message":{"type":"tool-calls","call":{"id":"smoke-1","phoneNumber":{"number":"'$LINE'"},"customer":{"number":"+14185550000"}},"toolCallList":[{"id":"t1","function":{"name":"check_availability","arguments":"{\"service_key\":\"driveway\"}"}}]}}'
```

Both should return 200. If the Vapi call returns `unknown_number`, the number is not attached to a business record — fix `businesses.phone_number`.
