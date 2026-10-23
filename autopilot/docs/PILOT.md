# Pilot plan — three businesses, one month

The pilot exists to answer four questions with evidence, not opinions:

1. Will an owner actually forward their phone to an AI?
2. Does the AI book a job a human would have missed?
3. Do customers pay faster when the invoice goes out by text automatically?
4. What does a call minute really cost us at this volume?

Everything below is designed so the answers land in one page at the end.

---

## Offer

**Free for 30 days, then $79/month if it worked.** Includes the dedicated number, the AI receptionist, booking, reminders, invoices, payment links, review requests, and the owner text commands. Cancel by texting STOP. No contract, no setup fee.

Ask in return:

* One 20-minute onboarding call.
* Permission to listen to the first five calls (with the AI disclosure in place).
* A 30-second testimonial if it works.
* A short weekly check-in text from the owner, answering three questions.

Disqualify anyone who wants a website, a CRM, or a crew app. Wrong product, wrong month.

---

## Timeline

| When | What |
|---|---|
| **Week -1** | Recruit 3 (talk to 15). Set up numbers, provision assistants, review each business's price ranges and hours. One test call per business with the owner on the line. |
| **Day 0** | Onboarding session, 20 min: forward the phone, send a test text, book a fake job together, show `TODAY` / `DONE`. Install nothing. |
| **Week 1** | Daily check on call logs. Fix prompts fast (greeting, service names, price ranges). Baseline numbers collected. |
| **Week 2** | First invoices sent automatically. Watch a payment land. Tune the chaser timing. |
| **Week 3** | Review requests go out. Ask the owner what is still annoying. |
| **Week 4** | Measure, write the one-pager, ask for the testimonial, offer the paid plan. |

---

## Metrics

Collect these per business, before and after. The dashboard already computes most of them (`/api/dashboard` → `stats`); the rest need a five-minute weekly ask.

| Metric | Definition | Where |
|---|---|---|
| **Missed calls recovered** | Calls handled by the AI that produced a booked job | `calls.job_id IS NOT NULL` |
| **Recovery rate** | Booked calls ÷ AI-answered calls | `stats.recovered_rate` |
| **Jobs booked by the AI** | Jobs with `source='voice'` | `stats.jobs_total` filtered by source |
| **Time to first invoice** | Job completion → invoice sent | `invoices.issued_at − jobs.completed_at` |
| **Days to payment** | Invoice issued → paid | `invoices.paid_at − invoices.issued_at` (dashboard average) |
| **Collected** | Paid invoice totals | `stats.revenue_cents` |
| **Outstanding** | Sent + overdue totals | `stats.outstanding_cents` |
| **Review requests sent** | Jobs with `review_requested_at` | `stats.reviews_requested` |
| **Review link clicks / new reviews** | Google Business Profile count before/after | owner reports |
| **Hang-up rate** | Calls under 20 s ÷ total calls | provider dashboard (Vapi/Bland) |
| **"Are you a robot?" rate** | From transcripts | sampled manually |
| **Cost per minute** | Provider bill ÷ connected minutes | provider invoices |

Baseline to capture at Day 0 (owner's answers, not data):

* How many calls do you miss on a storm day?
* What's your average invoice, and how long until people pay?
* How many jobs a week do you turn away because you can't answer?
* What do you pay for your current number / answering service?

---

## Weekly owner check-in (3 texts, Sunday night)

> 1. Anything the assistant got wrong this week?
> 2. How many jobs did it book that you'd have missed?
> 3. Would you pay $79 for this next month? (yes / not yet / no, and why)

The third question is the only one that matters for pricing. Ask it every week so it isn't a surprise in week 4.

---

## Go / no-go criteria

**Go** if, across three pilots:

* All three forwarded their phone within 48 hours of onboarding and left it forwarded.
* The AI booked **≥ 5 jobs total** that the owner confirms they would have missed.
* Average days-to-payment **improved versus baseline**, or invoices went out faster and at least one customer paid the same day.
* Fewer than 25% of AI-answered calls ended in a hang-up in the first 20 seconds.
* At least two of three owners say they'd pay $79.

**Iterate** if the technology works but the numbers don't: the problem is either the trade (too few calls), the price ranges (too vague to book), or the greeting.

**No-go on this segment** if owners refuse to forward their phone, or callers refuse the AI at a rate that makes the recovered jobs not worth the friction. Both are cheap to learn — that's the point of the pilot.

---

## Pilot artifacts to produce

1. **One-page results summary** per business: calls answered, jobs booked, dollars collected, days to payment, two quotes from the owner.
2. **A call recording** (with consent) that shows the AI booking a job. This is the best sales asset you will have.
3. **A list of the top five reasons owners said no.** That list drives the next month of product work.
4. **A real provider bill** so the per-minute model in `DECISIONS.md` gets replaced with a measured number.

---

## Data handling during the pilot

* Tell every pilot customer's callers that calls are answered by an AI (already in the prompt) and disclose recording if it's on.
* Keep transcripts for the pilot period only; delete on request, no questions.
* Do not put pilot customer data in a demo account or a public repo.
* If a pilot customer asks to leave, delete their customer data within 7 days but keep invoices for the tax period the owner needs.
