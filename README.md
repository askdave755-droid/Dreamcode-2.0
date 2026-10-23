# Dreamcode-2.0
Biblical dream reflection app — free preview, full reports $4.99/mo (cancel anytime).

- `frontend/` — React + Vite + Tailwind SPA (deployed to Vercel)
- `backend/` — FastAPI API on Railway (OpenAI reflections, Stripe subscriptions, PDF + email delivery)

## Autopilot for Small Trades (separate product)

`autopilot/` holds a self-contained second product: a phone-first admin
autopilot for small Canadian trade businesses (snow removal, lawn care,
cleaning, mobile grooming). A Vapi voice agent answers calls, books jobs,
FastAPI invoices with GST/QST/HST, texts payment links, chases late payers,
requests reviews, and rebooks seasonal work.

It has its own dependencies, tests, Dockerfile, and docs — nothing in it
imports from `backend/` or `frontend/`.

```bash
cd autopilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000     # open http://localhost:8000
pytest -q                            # 42 tests
```

Start with [`autopilot/README.md`](autopilot/README.md).
