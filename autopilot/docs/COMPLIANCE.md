# Compliance checklist

**Not legal advice.** This is the working checklist the product is built against. Confirm each item with a Canadian privacy/telecom lawyer before you charge a customer, and re-check when you add a province or a provider.

Two columns matter: what the code does, and what a human must do. Anything in the second column is a launch blocker if skipped.

---

## 1. AI disclosure

**Requirement.** A caller must know they are talking to an AI. Beyond ethics, misleading a consumer about the nature of the seller/agent can attract action under provincial consumer protection law, and Quebec's privacy and AI transparency expectations point the same way.

**Enforced in code.**
* The master prompt (`app/prompt.py`) opens with a mandatory disclosure block and instructs the agent never to claim to be human and never to deny being an AI.
* The default first message for every business says "this is … AI assistant".
* The prompt requires offering a callback from the owner whenever a human is requested.

**Human must do.**
* Listen to the first five calls of every new business. The model can drift; the greeting is the control point.
* Keep the disclosure in the first sentence after your custom greeting. Do not let an owner replace the greeting with one that hides the AI.
* State it on the business's website/Google profile: "Calls may be answered by an AI assistant."

## 2. CASL — commercial electronic messages (texts)

**Requirement.** Canada's Anti-Spam Legislation requires (a) consent, (b) sender identification, (c) a working unsubscribe mechanism, and (d) honoring unsubscribe within 10 business days. Penalties are per-message and can reach serious money.

**Consent we rely on.**

| Message type | Basis | Notes |
|---|---|---|
| Booking confirmation, reminder, reschedule/cancel, invoice, receipt | Express consent collected on the call by the assistant, plus the transactional nature of the message | Recorded on the customer row with source and timestamp |
| Payment reminder / chaser | Same express consent; transactional (about an existing transaction) | Cap at 3, 4 days apart |
| Review request | Express consent | Sent 2 days after payment |
| Rebooking / seasonal offers | Express consent on file; treat as marketing if the customer has not purchased in 24 months | Implied consent from an existing business relationship lasts 24 months after a purchase (6 months after an inquiry) — set `rebook_after_days` inside that window, or ask again at booking |

**Enforced in code.**
* `customers.sms_consent`, `sms_consent_source`, `sms_consent_at`, `sms_opt_out_at` are stored per person.
* Every outbound customer message gets the business's footer (`sms_footer`, default "Reply STOP to opt out.").
* `STOP`, `STOPALL`, `UNSUBSCRIBE`, `ARRÊT`, `DÉSABONNER` set the opt-out timestamp; afterwards `send_to_customer` refuses to send and logs `skipped_opt_out`.
* `START` re-subscribes and records the new consent timestamp.
* Owner-facing operational texts are never given the opt-out footer (they are not commercial messages to a customer).
* Every message, in and out, is stored in `messages` with template, timestamp, and provider status — the evidentiary record.

**Human must do.**
* Include the business's legal name, mailing address, and a contact URL in the footer or on the payment page. The current default footer only carries the opt-out; add identification before launch (`sms_footer` is per-business and capped at 200 characters — use a link to the business's contact page if you need more).
* Keep the consent record for as long as the relationship plus three years.
* Do not import a purchased contact list. Ever.
* Confirm A2P/10DLC registration status with Twilio for Canadian numbers.

## 3. Call recording

**Requirement.** Criminal Code s.184 generally allows recording with one party's consent (the business being a party), but Quebec's Civil Code (art. 35) and provincial privacy law are stricter about recording private communications, and several US states require all-party consent. A caller in another province or country can change the answer.

**Enforced in code.**
* `recordingEnabled` is a single flag in the assistant payload, so it can be turned off per business or globally in minutes.
* Transcripts and summaries are stored separately; the product works without audio.

**Human must do.**
* Decide the default. Recommended: announce "this call may be recorded" in the greeting, or disable recording for Quebec callers entirely.
* If you keep recording, add a consent step in the voice flow and store the consent in the call record.
* Set a retention period and enforce deletion at the provider (Vapi/Bland), not just in our database.

## 4. Privacy law (PIPEDA + Quebec Law 25)

**Requirement.** Collect only what you need, say why, protect it, and let people access/correct/delete it. Quebec adds: a designated privacy officer, privacy impact assessments for certain projects, confidentiality-by-default settings, and a register of confidentiality incidents.

**Enforced in code.**
* Tenant isolation on every query (`business_id` filter) with a regression test.
* No card data touches our servers; Stripe handles cards, e-Transfer is person-to-person.
* Owner login is a hashed, 10-minute one-time code; sessions are signed HttpOnly cookies.
* Twilio, Stripe, and Vapi webhooks are signature/secret verified.
* Passwords do not exist in the system; `SECRET_KEY` lives in the environment only.
* A customer-facing privacy draft is served at `/static/privacy.html`.

**Human must do.**
* Replace the placeholder privacy contact and have the policy reviewed.
* Name a privacy officer and publish the role's contact.
* Sign processor agreements (DPAs) with Twilio, Vapi/Bland, Stripe, OpenAI, Railway, and your database host. Confirm where data is stored (many default to the US — disclose that).
* Build the incident register and a 72-hour-ish notification habit; Quebec requires prompt notification to the CAI and to affected people for serious incidents.
* Decide retention: transcripts 90 days by default, job/invoice records 6 years for tax.
* Do not store SINs, driver's licence numbers, or health information in `notes`.

## 5. Pricing and quotes

**Requirement.** An estimate must not be presented as a firm price. Consumer protection law in Quebec and elsewhere treats misleading price representations seriously, and this is the number one way an AI receptionist can create a dispute.

**Enforced in code.**
* The prompt contains only the business's ranges and a rule against firm quotes, invented ranges, and discounts.
* `get_service_list` returns ranges with the instruction "Ranges only. The owner confirms the exact price."
* Every owner booking text includes the service and the callback marker; the owner sets `price_final_cents` (or texts `QUOTE 3 145`) before the invoice.
* Invoices use the owner-confirmed amount, or the low end of the range with the note "estimate used — text QUOTE to fix".

**Human must do.**
* Review each business's ranges before launch. A range that is wrong is worse than no range.
* Tell owners: the AI never commits to a price, and that is deliberate.

## 6. Tax

**Enforced in code.** GST 5% + QST 9.975% in Quebec, HST by province (13/14/15%), GST 5% elsewhere, all with per-component rounding and a stored breakdown. Tax can be switched off per business for a small supplier not yet registered. The dashboard shows a set-aside summary.
**Human must do.** Confirm registration status and the correct treatment with the owner's accountant. Registration is required once revenue passes the small-supplier threshold; charging tax while unregistered is a problem, and not charging while registered is worse. The app is not an accounting system.

## 7. Emergencies and safety

**Enforced in code.** Emergency keywords escalate to the owner with an `URGENT` prefix; the prompt forbids promising an arrival time and forbids giving safety advice.
**Human must do.** Never present the assistant as an emergency service. Add a recorded fallback ("if this is an emergency, hang up and call 911") to the greeting for trades where it could matter, and confirm the owner's transfer line is reachable.

## 8. Accessibility and language

**Enforced in code.** Language can be `en`, `fr`, or `bilingual`; the prompt instructs the agent to continue in the caller's language.
**Human must do.** Test the French path with a real Quebec caller. Charter of the French Language (Bill 96) expectations apply to commerce in Quebec — the customer-facing texts and payment page should be available in French.

---

## Launch checklist

- [ ] Privacy policy reviewed by counsel; contact and privacy officer published
- [ ] Message footer carries business identification + opt-out + contact
- [ ] Recording decision made per province; greeting states it if recording is on
- [ ] Consent records verified on 10 test customers (source + timestamp)
- [ ] Opt-out tested end to end; STOP produces no further automated texts
- [ ] DPAs signed with every processor; data residency known and disclosed
- [ ] Retention job (or documented manual process) for transcripts and calls
- [ ] Tax profile confirmed per business; tax numbers recorded
- [ ] Price ranges approved by the owner in writing
- [ ] Emergency script tested with a real call
- [ ] Incident response contact list written down
