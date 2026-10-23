# Decisions and open questions

Answers to the open questions in the build plan, with the reasoning and the numbers behind them. Revisit the pricing and provider sections quarterly — both move.

---

## 1. Which trade first?

**Snow removal, in the Beauce / Chaudière-Appalaches region of Quebec.**

Why this trade:

* **The call arrives when the owner physically cannot answer.** The first real snowfall generates a week of calls in a day, and the owner is outside, gloves on, plow running. That is the exact moment a missed call is worth $45–$95.
* **Seasonal contract sales create a natural deadline.** September–November is when homeowners buy seasonal contracts. An owner who is still plowing last season's invoices is not selling next season's contracts.
* **The price is simple.** Driveway clearing is a range, not a design consultation. Ranges work; custom quotes don't.
* **Repeat business is built in.** The same customer needs the same service 15–30 times a season, so the rebooking and reminder loops earn their keep immediately.
* **Local advantage matters.** You can meet these owners in person, in French, at the equipment dealer. Trust beats features in this segment.

Risks, and the answer:

| Risk | Mitigation |
|---|---|
| Seasonality: revenue collapses in April | Add lawn care/spring cleanup to the same customer base; the trade presets already cover it, so it's a profile change, not a new product |
| Owners are price-sensitive and low-tech | Price at $79, not $299; onboarding is a text conversation; no app to install |
| Storm days can overflow concurrency | Availability rules are per-business; a queue and callback promise is the designed behaviour, not an error |
| Quebec French requirements | `language=bilingual`, French-first greeting, French opt-out keywords already handled |

**Second trade:** lawn care (same owners, opposite season). **Third:** cleaning (recurring, less seasonal, more competitive).

---

## 2. Vapi or Bland? What does a minute cost?

**Recommendation: build on Vapi (done), keep the provider boundary thin, revisit at ~5,000 minutes/month.**

Published rates as of late 2026 (verify before you sign — these changed twice in the last year):

| Provider | Rate | What it includes |
|---|---|---|
| Vapi | **$0.05/min** platform | Hosting only. Model, transcriber, voice, and telephony are billed at cost or by your own keys |
| Bland | **$0.14/min** (Start, no platform fee) | Model + STT + TTS included. Telephony separate |
| Bland | $0.12/min + $299/mo (Build) | Same, higher limits |
| Telephony | ~$0.008–0.014/min | Twilio inbound/outbound, on top of either |

**All-in estimate for this product:** $0.11–0.15/min.
A typical minute is ~$0.05 Vapi + ~$0.01 Deepgram + ~$0.02–0.04 LLM + ~$0.02 ElevenLabs + ~$0.01 telephony. That lands at **≈$0.12/min**, and lower if you bring your own OpenAI key and a cheaper voice.

**Per business per month**, assuming 90–150 call minutes:

| | Vapi stack | Bland Start |
|---|---|---|
| 150 min voice | $18.00 | $21.00 |
| Telephony | $1.50 | separate (~$1.50) |
| SMS (~150 msgs × $0.012) | $1.80 | $1.80 |
| Number rental | $1.15 | $1.15 |
| **Cost before Stripe fees** | **≈$22.45** | **≈$25.45** |

At $79/month, gross margin is ~68% on Vapi and ~65% on Bland at that volume. Bland's simplicity (one bundled rate, no token accounting) is worth something operationally, but Vapi's BYO-key path and per-business assistant provisioning are what let this product generate one assistant per tenant from a profile in a single API call — which is the core of the architecture.

**Switch trigger:** if Bland's Build tier ($299/mo) is cheaper than your Vapi bill at your actual volume — roughly above 4,000–5,000 minutes/month — or if Vapi's unbundled billing becomes operationally annoying. The adapter for Bland already exists (`POST /webhooks/bland`), so the switch is a payload change plus one webhook URL.

---

## 3. Pricing tiers

Two plans, priced against the value of one recovered job, not against cost.

| | **Starter — $79/mo** | **Pro — $149/mo** |
|---|---|---|
| Voice minutes included | 200 | 600 |
| Overage | $0.49/min | $0.39/min |
| AI receptionist + booking | ✓ | ✓ |
| Reminders, invoices, chasers | ✓ | ✓ |
| Review + rebooking texts | ✓ | ✓ |
| Owner text commands | ✓ | ✓ |
| Seasonal campaigns | — | ✓ |
| Quarterly tax summary | — | ✓ |
| Support | Text | Priority |

Reasoning:

* **$79 is below the "ask my wife" threshold** for a solo operator, and roughly the value of one driveway job. One recovered call pays for the month.
* **Minutes are the only variable cost**, so the allowances are generous at typical volume (90–150 min/mo) and still protect margin at the cap. At 200 minutes of Vapi usage, cost is ~$26 and margin is ~67%.
* **Pro is for two-truck operations** that also want campaigns and the tax export. The 600-minute allowance keeps margin near 45% even if fully used.
* **Trial: 14 days, full features, 60-minute voice cap** so a trial cannot be farmed as free answering. After the trial, the line stays live for 3 days while the owner decides (already wired: the trial-ending text).
* **No per-job fee, ever.** It punishes the behaviour you want (booking jobs) and makes the value story complicated.
* Future: annual prepay at 2 months free; a $39 "off-season hold" for snow businesses (number stays, texts pause) — seasonality is the biggest churn risk.

---

## 4. Name and branding

Working name in the code: **Autopilot for Small Trades** (descriptive, not a brand).

Shortlist, in order:

1. **Crewline** — works in English and French, sounds like a phone line and a crew, `.ca` likely available, no obvious conflict in trades software. Pairs well with "your line, covered".
2. **Métier** — "trade/craft" in French; strong in Quebec, weaker in English Canada, excellent for a French-first launch.
3. **Snowline** — sharp for the pilot, but you are stuck when you add lawn care; would work as a *product* name inside a parent brand.
4. **Relay** — accurate (we relay calls and jobs) but heavily used in SaaS; expect trademark friction.

Before committing: run a CIPO trademark search, a domain check for `.ca` and `.com`, and say the name aloud in a French sentence. Avoid anything with "AI" in it — owners don't buy AI, they buy "the phone gets answered".

Positioning line: **"Your phone gets answered. Your invoices get paid. You keep working."**
French: **« Ton téléphone se fait répondre. Tes factures se font payer. Toi, tu travailles. »**

---

## 5. Finding the first three pilot customers

Goal: three real businesses, free or 50% off for one month, in exchange for a testimonial and a number.

Channels, ranked by conversion likelihood:

1. **Your existing network, one degree out.** Ask everyone you know in the Beauce for "the snow guy you use". A warm introduction from a homeowner the contractor already serves is worth 50 cold calls.
2. **The equipment dealer and the parts counter.** Snow-removal owners are physically there in October. Ask the owner of the dealership for an introduction; offer to answer their phone for a week as a demo.
3. **Local Facebook groups and marketplace** (e.g. Beauce buy/sell/community groups). Post as a local business, not as a tech startup: "Je cherche 3 entrepreneurs en déneigement pour tester gratuitement un service qui répond à leurs appels quand ils sont dans la gratte."
4. **Direct door-knock at 7am at the Tim Hortons** where crews stage during a storm. Not a metaphor — this is where the buying conversation happens.
5. **The snow-removal association / regional chamber of commerce.** Slower, but gives you a room full of qualified owners and a credibility signal.

Pilot offer (say it in one breath):

> "I'll answer your phone for a month, free. When someone calls while you're plowing, they get a real answer and a booked job instead of your voicemail. After the month, if it booked you work, it's $79. If not, I turn it off and you keep the number's call log."

What to ask for in return: 20 minutes of onboarding, permission to listen to five calls, a short testimonial if it works, and the numbers (missed calls before/after, jobs booked, days to payment).

Qualifying questions:

* "How many calls do you miss on a snow day?" (If the answer is "none", they don't have the problem.)
* "What happens today when someone calls and you're on the plow?"
* "How do you invoice now, and how long until people pay?"
* "Do you text with customers already?" (Text-savvy owners adopt in a day.)

Disqualify: anyone who wants a full CRM, a crew app, or a website. This product is one job: the phone and the money.

Target: 15 conversations to get 3 pilots. If the conversion is worse than 1 in 5, the message is wrong, not the market.

---

## 6. What would make this a no-go

Be honest about these before spending a season on it:

* **Pilot owners don't forward their phones.** Forwarding is the entire product. If owners won't do it (or their carrier makes it hard), the value never materializes.
* **Callers hate the AI.** Measure: hang-up rate in the first 20 seconds, and how often callers ask for a human. Above ~25% hang-ups, the voice/prompt needs work before scaling.
* **Payment collection doesn't improve.** If days-to-payment doesn't move, you're selling an answering service, not an admin autopilot — and answering services are cheaper.
* **Voice cost per minute rises faster than price tolerance.** Keep the overage rate and the switch-to-Bland path ready.
