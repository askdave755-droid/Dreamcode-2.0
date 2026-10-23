/* Autopilot for Small Trades — phone-first owner app.
   Vanilla JS on purpose: one file, no build step, fast on a job-site phone. */

const state = {
  business: null,
  dash: null,
  tab: "today",
  jobFilter: "upcoming",
  loading: false,
  authStep: "phone",
  authPhone: "",
  authCode: "",
  demoCode: null,
  onboarding: { step: 0, trade: "snow_removal", services: [] },
  prompt: null,
  provisioning: null,
  plans: null,
  billing: null,
};

const root = document.getElementById("root");
const boot = document.getElementById("boot");
const toastEl = document.getElementById("toast");
const sheetEl = document.getElementById("sheet");
const sheetBody = document.getElementById("sheet-body");

/* ------------------------------------------------------------------ utils */
const money = (cents) =>
  cents == null ? "—" : "$" + (cents / 100).toLocaleString("en-CA", { minimumFractionDigits: 0, maximumFractionDigits: 2 });

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const shortTime = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-CA", { hour: "numeric", minute: "2-digit" });
};

const dayLabel = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const diff = Math.round((new Date(d.toDateString()) - new Date(today.toDateString())) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return d.toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric" });
};

const relTime = (iso) => {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
};

function toast(message, kind = "ok") {
  toastEl.textContent = message;
  toastEl.className = "toast" + (kind === "err" ? " err" : "");
  toastEl.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (toastEl.hidden = true), 3400);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const detail =
      (body && (body.detail || body.message)) ||
      "Something went wrong (" + response.status + ")";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

const statusBadge = (job) => {
  if (job.status === "confirmed")
    return `<span class="badge confirmed">Confirmed</span>`;
  if (job.status === "needs_confirmation")
    return `<span class="badge needs">Call back</span>`;
  if (job.status === "requested")
    return `<span class="badge needs">New request</span>`;
  if (job.status === "paid") return `<span class="badge done">Paid</span>`;
  if (job.status === "done") return `<span class="badge done">Invoiced</span>`;
  if (job.status === "cancelled") return `<span class="badge open">Cancelled</span>`;
  return `<span class="badge open">${esc(job.status)}</span>`;
};

const invoiceBadge = (inv) => {
  if (inv.status === "paid") return `<span class="badge done">Paid</span>`;
  if (inv.status === "overdue") return `<span class="badge overdue">Overdue</span>`;
  if (inv.status === "sent") return `<span class="badge open">Awaiting payment</span>`;
  return `<span class="badge open">Draft</span>`;
};

/* ---------------------------------------------------------------- session */
async function bootApp() {
  try {
    const business = await api("/api/me");
    state.business = business;
    await loadDashboard();
    renderApp();
  } catch {
    renderAuth();
  } finally {
    boot.hidden = true;
    root.hidden = false;
  }
}

async function loadDashboard() {
  state.dash = await api("/api/dashboard");
  state.business = state.dash.business;
}

/* ------------------------------------------------------------------- auth */
function renderAuth() {
  root.innerHTML = `
    <div class="auth">
      <div class="logo">A</div>
      <h1>Your business runs<br>while you work.</h1>
      <p class="lede">The phone gets answered, the job gets booked, the invoice gets paid. You just show up.</p>

      <div class="panel">
        ${
          state.authStep === "phone"
            ? `
          <div class="stack">
            <div class="field">
              <label for="phone">Owner mobile number</label>
              <input id="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="(418) 555-0199" value="${esc(state.authPhone)}" />
              <span class="hint">We text you a 6-digit code. No passwords.</span>
            </div>
            <button class="btn primary block" data-act="request-code">Text me a code</button>
            <button class="btn ghost block" data-act="demo-login">Open the demo business</button>
            <button class="btn ghost block" data-act="start-onboarding" style="border-style:dashed">I'm new — set up my business</button>
          </div>`
            : `
          <div class="stack">
            <div class="field">
              <label for="code">Code sent to ${esc(state.authPhone)}</label>
              <input id="code" class="code-input" inputmode="numeric" maxlength="6" placeholder="000000" value="${esc(state.authCode)}" />
              ${state.demoCode ? `<span class="hint">Demo mode — your code is <b>${esc(state.demoCode)}</b></span>` : `<span class="hint">Expires in 10 minutes.</span>`}
            </div>
            <button class="btn primary block" data-act="verify-code">Sign in</button>
            <button class="btn ghost block" data-act="back-phone">Use a different number</button>
          </div>`
        }
      </div>

      <div class="points">
        <div class="point"><span class="dot"></span><span><b>Answers every call</b> — even at 6am on a snow day.</span></div>
        <div class="point"><span class="dot"></span><span><b>Books without a calendar</b> — the slot is checked before it is promised.</span></div>
        <div class="point"><span class="dot"></span><span><b>Chases the money</b> — invoice, reminder, review, rebook.</span></div>
      </div>

      <p class="foot">Built for Canadian trades. Calls are answered by an AI assistant that says so up front. Texts include opt-out.</p>
    </div>`;
}

/* -------------------------------------------------------------- onboarding */
const TRADES = [
  { key: "snow_removal", emoji: "❄️", label: "Snow removal", sub: "Driveways & walkways" },
  { key: "lawn_care", emoji: "🌿", label: "Lawn care", sub: "Mowing & cleanups" },
  { key: "cleaning", emoji: "🧽", label: "Cleaning", sub: "Homes & move-outs" },
  { key: "mobile_grooming", emoji: "🐕", label: "Mobile grooming", sub: "Grooming at the door" },
];

const PROVINCES = [
  ["QC", "Quebec"], ["ON", "Ontario"], ["NB", "New Brunswick"], ["NS", "Nova Scotia"],
  ["PE", "Prince Edward Island"], ["NL", "Newfoundland"], ["BC", "British Columbia"],
  ["AB", "Alberta"], ["SK", "Saskatchewan"], ["MB", "Manitoba"], ["YT", "Yukon"],
  ["NT", "NWT"], ["NU", "Nunavut"],
];

function renderOnboarding() {
  const ob = state.onboarding;
  const total = 3;
  const step = ob.step;
  root.innerHTML = `
  <div class="wizard">
    <div class="top">
      <div class="logo" style="width:38px;height:38px;border-radius:12px;background:var(--navy);color:#fff;display:grid;place-items:center;font-weight:800">A</div>
      <span class="small muted">Step ${step + 1} of ${total}</span>
    </div>
    <div class="progress">${[0, 1, 2].map((i) => `<span class="${i <= step ? "on" : ""}"></span>`).join("")}</div>
    <div style="height:18px"></div>
    ${step === 0 ? onboardingTrade() : ""}
    ${step === 1 ? onboardingBasics() : ""}
    ${step === 2 ? onboardingFinish() : ""}
    <div style="height:18px"></div>
    <div class="row">
      ${step > 0 ? `<button class="btn ghost" data-act="ob-back">Back</button>` : `<button class="btn ghost" data-act="back-auth">Cancel</button>`}
      <button class="btn primary grow" data-act="${step === 2 ? "ob-create" : "ob-next"}">${step === 2 ? "Create my line" : "Continue"}</button>
    </div>
    <p class="tiny soft" style="margin-top:16px">Under five minutes. You can change everything later — including prices, hours, and your greeting.</p>
  </div>`;
}

function onboardingTrade() {
  return `
    <h1>What's your trade?</h1>
    <p class="muted small" style="margin-top:6px">We'll pre-fill services, price ranges, and the phone script. Edit anything later.</p>
    <div style="height:16px"></div>
    <div class="trade-grid">
      ${TRADES.map(
        (trade) => `
        <button class="trade ${state.onboarding.trade === trade.key ? "on" : ""}" data-trade="${trade.key}">
          <span class="emoji">${trade.emoji}</span>
          <span class="t">${trade.label}</span>
          <span class="s">${trade.sub}</span>
        </button>`
      ).join("")}
    </div>`;
}

function onboardingBasics() {
  return `
    <h1>Your business</h1>
    <p class="muted small" style="margin-top:6px">This is what the assistant says when it answers.</p>
    <div style="height:16px"></div>
    <div class="form-grid">
      <div class="field"><label>Business name</label><input id="ob-name" placeholder="Lévesque Déneigement" /></div>
      <div class="field"><label>Your first and last name</label><input id="ob-owner" placeholder="Marc Lévesque" /></div>
      <div class="form-grid two">
        <div class="field"><label>Your mobile</label><input id="ob-phone" type="tel" inputmode="tel" placeholder="(418) 555-0199" value="${esc(state.authPhone)}" /></div>
        <div class="field"><label>City</label><input id="ob-city" placeholder="Saint-Georges" /></div>
      </div>
      <div class="form-grid two">
        <div class="field"><label>Province</label>
          <select id="ob-province">${PROVINCES.map(([code, name]) => `<option value="${code}">${name}</option>`).join("")}</select>
        </div>
        <div class="field"><label>Areas you cover</label><input id="ob-area" placeholder="Beauce" /></div>
      </div>
    </div>
    <p class="tiny soft" style="margin-top:12px">Tax is set from your province (GST + QST in Quebec, HST in Ontario).</p>`;
}

function onboardingFinish() {
  return `
    <h1>Finish strong</h1>
    <p class="muted small" style="margin-top:6px">Two optional things that make the automation work better.</p>
    <div style="height:16px"></div>
    <div class="form-grid">
      <div class="field"><label>Google review link</label>
        <input id="ob-review" placeholder="https://g.page/r/..." />
        <span class="hint">Sent automatically a couple of days after payment.</span>
      </div>
      <div class="field"><label>Interac e-Transfer email</label>
        <input id="ob-etransfer" type="email" placeholder="you@example.com" />
        <span class="hint">Optional. Customers who don't want to pay by card get this instead.</span>
      </div>
      <div class="field"><label>Your greeting (optional)</label>
        <textarea id="ob-greeting" placeholder="Lévesque Déneigement, bonjour! This is Marc's AI assistant. Are you calling about a driveway?"></textarea>
      </div>
    </div>
    <div class="notice info" style="margin-top:12px">Your AI assistant will always say it is an AI, give rough price ranges only, and text you for anything unusual or urgent.</div>`;
}

/* --------------------------------------------------------------- main app */
const TABS = [
  { key: "today", label: "Today", icon: "M3 10.5 12 3l9 7.5M5.5 9.5V21h13V9.5" },
  { key: "jobs", label: "Jobs", icon: "M4 7h16v13H4zM8 7V4h8v3M4 12h16" },
  { key: "money", label: "Money", icon: "M3 6h18v12H3zM3 10h18M7 15h3" },
  { key: "assistant", label: "Assistant", icon: "M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V7a4 4 0 0 1 4-4ZM5 21a7 7 0 0 1 14 0" },
  { key: "more", label: "More", icon: "M4 7h16M4 12h16M4 17h10" },
];

function renderApp() {
  const business = state.business;
  const planChip =
    business.plan_status === "active"
      ? `${business.plan}`
      : business.plan_status === "trialing"
      ? "trial"
      : business.plan_status;
  const outstanding = state.dash ? state.dash.stats.outstanding_cents : 0;

  root.innerHTML = `
  <div class="screen">
    <header class="appbar">
      <div class="brandline">
        <div>
          <div class="biz">${esc(business.name)}</div>
          <div class="sub line-num">${esc(business.phone_number || "No line assigned yet")} · ${esc(business.city || "")}${business.province ? ", " + esc(business.province) : ""}</div>
        </div>
        <span class="plan-chip ${business.plan_status !== "active" ? "warn" : ""}">${esc(planChip)}</span>
      </div>
      ${
        !business.phone_number
          ? `<div class="hero-note"><span>◍</span><span><strong>No business line yet.</strong> Add the dedicated number in <b>More → Business profile</b> so calls and texts can reach your assistant.</span></div>`
          : business.demo_mode
          ? `<div class="hero-note"><span>◍</span><span><strong>Dry-run mode.</strong> Texts, calls, and payments are simulated until you add Twilio, Stripe, and Vapi keys.</span></div>`
          : outstanding
          ? `<div class="hero-note"><span>◍</span><span><strong>${money(outstanding)}</strong> is still outstanding. Chasers run automatically.</span></div>`
          : ""
      }
    </header>
    <div class="content" id="tab-content">${renderTab()}</div>
    <nav class="tabbar">
      ${TABS.map(
        (tab) => `
        <button class="tab ${state.tab === tab.key ? "on" : ""}" data-tab="${tab.key}" aria-label="${tab.label}">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><path d="${tab.icon}"/></svg>
          <span>${tab.label}</span>
        </button>`
      ).join("")}
    </nav>
  </div>`;
}

function renderTab() {
  if (!state.dash) return `<p class="muted">Loading…</p>`;
  switch (state.tab) {
    case "today": return todayTab();
    case "jobs": return jobsTab();
    case "money": return moneyTab();
    case "assistant": return assistantTab();
    case "more": return moreTab();
    default: return todayTab();
  }
}

/* ----------------------------------------------------------------- today */
function jobCard(job, extra = "") {
  const customer = job.customer || {};
  const when = job.scheduled_start
    ? `${dayLabel(job.scheduled_start)} · ${shortTime(job.scheduled_start)}`
    : job.requested_for || "Time to confirm";
  return `
  <article class="card job-card">
    <div class="job-top">
      <div>
        <div class="job-when">${esc(when)}</div>
        <div class="job-service">${esc(job.service)}</div>
        <div class="job-meta">${esc(customer.name || "Unknown caller")}${customer.phone ? " · " + esc(customer.phone) : ""}</div>
        ${job.address ? `<div class="job-meta">${esc(job.address)}</div>` : ""}
      </div>
      <div class="stack" style="gap:6px;align-items:flex-end">
        ${statusBadge(job)}
        ${job.source === "voice" ? `<span class="badge voice">AI call</span>` : ""}
      </div>
    </div>
    ${job.notes ? `<p class="small muted" style="background:#fafbfc;border-radius:10px;padding:9px 10px">${esc(job.notes)}</p>` : ""}
    ${extra}
    <div class="job-actions">
      ${
        job.status === "confirmed"
          ? `<button class="btn sm primary" data-act="done" data-id="${job.id}">Done → invoice</button>
             <button class="btn sm ghost" data-act="reschedule" data-id="${job.id}">Reschedule</button>`
          : ""
      }
      ${
        job.status === "needs_confirmation" || job.status === "requested"
          ? `<button class="btn sm primary" data-act="confirm" data-id="${job.id}">Confirm slot</button>
             <button class="btn sm soft" data-act="open-job" data-id="${job.id}">Details</button>`
          : `<button class="btn sm ghost" data-act="open-job" data-id="${job.id}">Details</button>`
      }
      <a class="btn sm ghost" href="tel:${esc(customer.phone || "")}">Call</a>
    </div>
  </article>`;
}

function todayTab() {
  const dash = state.dash;
  const stats = dash.stats;
  return `
    <section class="section">
      <div class="stat-grid">
        <div class="stat"><div class="k">Calls saved</div><div class="v">${stats.calls_recovered}</div><div class="d">booked by the AI</div></div>
        <div class="stat"><div class="k">Collected</div><div class="v">${money(stats.revenue_cents)}</div><div class="d">${stats.avg_days_to_pay != null ? stats.avg_days_to_pay + "d avg to pay" : "paid invoices"}</div></div>
        <div class="stat"><div class="k">Outstanding</div><div class="v">${money(stats.outstanding_cents)}</div><div class="d">${dash.open_invoices.length} open</div></div>
      </div>
    </section>

    ${
      dash.needs_action.length
        ? `<section class="section">
        <div class="section-head"><h2>Needs you</h2><span class="tiny muted">${dash.needs_action.length} waiting</span></div>
        <div class="stack">${dash.needs_action.map((job) => jobCard(job)).join("")}</div>
      </section>`
        : ""
    }

    <section class="section">
      <div class="section-head"><h2>Today</h2><span class="tiny muted">${dash.today.length} job${dash.today.length === 1 ? "" : "s"}</span></div>
      ${
        dash.today.length
          ? `<div class="stack">${dash.today.map((job) => jobCard(job)).join("")}</div>`
          : `<div class="empty"><div class="big">☀️</div><p>Nothing scheduled today.</p><p class="tiny">Open slots below — the assistant is offering them.</p></div>`
      }
    </section>

    <section class="section">
      <div class="section-head"><h2>Next up</h2><button class="link" style="background:none;border:0;padding:0" data-act="refresh">Refresh</button></div>
      ${
        dash.upcoming.length
          ? `<div class="card flush"><div class="list">${dash.upcoming
              .map(
                (job) => `
              <div class="list-item" data-act="open-job" data-id="${job.id}">
                <div class="li-main">
                  <div class="li-title">${esc(job.service)} · ${esc(job.customer?.name || "Customer")}</div>
                  <div class="li-sub">${esc(dayLabel(job.scheduled_start))} at ${esc(shortTime(job.scheduled_start))}${job.address ? " · " + esc(job.address) : ""}</div>
                </div>
                <div class="li-right">${statusBadge(job)}</div>
              </div>`
              )
              .join("")}</div></div>`
          : `<div class="empty"><p>No upcoming jobs yet.</p></div>`
      }
    </section>

    ${
      dash.open_slots.length
        ? `<section class="section">
        <div class="section-head"><h2>Open slots</h2><span class="tiny muted">offered on calls</span></div>
        <div class="chips">
          ${dash.open_slots
            .map(
              (day) =>
                `<button class="chip slot" data-act="book-slot" data-day="${esc(day.slots[0])}">${esc(day.label)} ${esc(shortTime(day.slots[0]))}</button>`
            )
            .join("")}
        </div>
      </section>`
        : ""
    }

    <section class="section">
      <div class="section-head"><h2>Latest texts</h2></div>
      <div class="card flush"><div class="list">
        ${
          dash.messages.length
            ? dash.messages
                .slice(0, 6)
                .map(
                  (message) => `
          <div class="list-item">
            <div class="li-main">
              <div class="li-title">${message.direction === "in" ? "From " + esc(message.from) : "To " + esc(message.to)}</div>
              <div class="li-sub">${esc(message.body.slice(0, 110))}${message.body.length > 110 ? "…" : ""}</div>
            </div>
            <div class="li-right tiny soft">${esc(relTime(message.created_at))}<br>${message.status === "dry_run" ? "dry-run" : esc(message.status)}</div>
          </div>`
                )
                .join("")
            : `<div class="list-item"><div class="li-main"><div class="li-sub">No texts yet. Book a job and watch the confirmation go out.</div></div></div>`
        }
      </div></div>
    </section>`;
}

/* ------------------------------------------------------------------ jobs */
function jobsTab() {
  const filters = [
    ["upcoming", "Upcoming"],
    ["needs", "Needs action"],
    ["done", "Finished"],
    ["all", "All"],
  ];
  const jobs = state.jobs || [];
  return `
    <section class="section">
      <div class="chips" style="margin-bottom:12px">
        ${filters
          .map(
            ([key, label]) =>
              `<button class="chip ${state.jobFilter === key ? "on" : ""}" data-filter="${key}">${label}</button>`
          )
          .join("")}
        <button class="chip" data-act="new-job">+ New job</button>
      </div>
      ${
        jobs.length
          ? `<div class="stack">${jobs.map((job) => jobCard(job)).join("")}</div>`
          : `<div class="empty"><div class="big">🗂</div><p>No jobs in this view.</p><p class="tiny">The assistant books them; you can add one by hand too.</p></div>`
      }
    </section>`;
}

/* ----------------------------------------------------------------- money */
function moneyTab() {
  const invoices = state.invoices || [];
  const stats = state.dash.stats;
  const tax = state.taxTotals || { gst: 0, qst: 0, hst: 0, subtotal: 0 };
  return `
    <section class="section">
      <div class="stat-grid">
        <div class="stat"><div class="k">Collected</div><div class="v">${money(stats.revenue_cents)}</div><div class="d">all time</div></div>
        <div class="stat"><div class="k">Open</div><div class="v">${money(stats.outstanding_cents)}</div><div class="d">${invoices.filter((i) => i.status !== "paid").length} invoices</div></div>
        <div class="stat"><div class="k">Avg to pay</div><div class="v">${stats.avg_days_to_pay ?? "—"}${stats.avg_days_to_pay != null ? "d" : ""}</div><div class="d">since issue</div></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Your tax set-aside</h2><span class="tiny muted">collected on paid invoices</span></div>
      <div class="card">
        <div class="kv"><span class="k">Revenue before tax</span><span>${money(tax.subtotal)}</span></div>
        <div class="kv"><span class="k">GST (5%)</span><span>${money(tax.gst)}</span></div>
        <div class="kv"><span class="k">QST (9.975%)</span><span>${money(tax.qst)}</span></div>
        ${tax.hst ? `<div class="kv"><span class="k">HST</span><span>${money(tax.hst)}</span></div>` : ""}
        <div class="kv"><span class="k bold">Total tax collected</span><span class="bold">${money(tax.gst + tax.qst + tax.hst)}</span></div>
      </div>
      <p class="tiny soft" style="margin-top:8px">Informational only — confirm remittance with your accountant. Tax is applied per your province (${esc(state.business?.tax_profile || "")}).</p>
    </section>

    <section class="section">
      <div class="section-head"><h2>Invoices</h2><button class="link" style="background:none;border:0;padding:0" data-act="refresh">Refresh</button></div>
      ${
        invoices.length
          ? `<div class="card flush"><div class="list">${invoices
              .map(
                (inv) => `
            <div class="list-item">
              <div class="li-main">
                <div class="li-title">${esc(inv.number)} · ${esc(inv.service || "Service")}</div>
                <div class="li-sub">${esc(inv.customer_name || "Customer")}${inv.job_number ? " · job #" + inv.job_number : ""} · ${esc(relTime(inv.issued_at))}</div>
              </div>
              <div class="li-right">
                <div class="bold">${money(inv.total_cents)}</div>
                <div style="margin-top:4px">${invoiceBadge(inv)}</div>
                ${
                  inv.status !== "paid"
                    ? `<button class="btn sm ghost" style="margin-top:6px" data-act="invoice-actions" data-id="${inv.id}">Manage</button>`
                    : ""
                }
              </div>
            </div>`
              )
              .join("")}</div></div>`
          : `<div class="empty"><p>No invoices yet.</p><p class="tiny">Text DONE after a job and one is created automatically.</p></div>`
      }
    </section>

    <section class="section">
      <div class="section-head"><h2>Your subscription</h2></div>
      <div class="card">
        ${billingBlock()}
      </div>
    </section>`;
}

function billingBlock() {
  const billing = state.billing;
  if (!billing) return `<p class="small muted">Loading plan…</p>`;
  return `
    <div class="row between">
      <div>
        <h3>${esc(billing.plan_name)} plan</h3>
        <p class="small muted">${money(billing.monthly_cents)}/mo · ${billing.minutes_included} voice minutes</p>
      </div>
      <span class="badge ${billing.plan_status === "active" ? "done" : "needs"}">${esc(billing.plan_status)}</span>
    </div>
    <div class="kv" style="margin-top:10px"><span class="k">Minutes used</span><span>${billing.minutes_used} min${billing.overage_minutes ? ` · ${billing.overage_minutes} over` : ""}</span></div>
    <div class="kv"><span class="k">Overage</span><span>${money(billing.overage_cents)}</span></div>
    <div class="row" style="margin-top:12px">
      <button class="btn sm dark grow" data-act="plan" data-plan="starter">Starter</button>
      <button class="btn sm primary grow" data-act="plan" data-plan="pro">Upgrade to Pro</button>
    </div>
    ${billing.dry_run ? `<p class="tiny soft" style="margin-top:10px">Stripe is in dry-run — switching plans here only changes the record.</p>` : ""}`;
}

/* -------------------------------------------------------------- assistant */
function assistantTab() {
  const business = state.business;
  const integrations = business.integrations || {};
  const services = business.services || [];
  return `
    <section class="section">
      <div class="section-head"><h2>Your receptionist</h2><span class="tiny muted">${esc(business.voice || "")}</span></div>
      <div class="card">
        <div class="field">
          <label>Greeting (first thing callers hear)</label>
          <textarea id="greeting" style="min-height:84px">${esc(business.greeting || "")}</textarea>
          <span class="hint">Always introduces itself as an AI. Keep it under two sentences.</span>
        </div>
        <div class="row" style="margin-top:10px">
          <button class="btn sm primary" data-act="save-greeting">Save greeting</button>
          <button class="btn sm ghost" data-act="preview-prompt">View full prompt</button>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Services & ranges</h2><span class="tiny muted">${services.length} services</span></div>
      <div class="card flush"><div class="list">
        ${services
          .map(
            (service) => `
          <div class="list-item">
            <div class="li-main">
              <div class="li-title">${esc(service.name)}</div>
              <div class="li-sub">${service.duration_min} min · ${esc(service.unit || "per visit")}${service.rebook_after_days ? " · rebook in " + service.rebook_after_days + "d" : ""}</div>
            </div>
            <div class="li-right bold">${money(service.price_min_cents)}–${money(service.price_max_cents)}</div>
          </div>`
          )
          .join("")}
      </div></div>
      <p class="tiny soft" style="margin-top:8px">The assistant may only quote these ranges and always says the owner confirms the exact price.</p>
    </section>

    <section class="section">
      <div class="section-head"><h2>Call handling</h2></div>
      <div class="card">
        <div class="kv"><span class="k">Voice provider</span><span>${integrations.voice === "configured" ? "Vapi" : "Vapi (dry-run)"}</span></div>
        <div class="kv"><span class="k">Webhook</span><span class="tiny">/webhooks/vapi</span></div>
        <div class="kv"><span class="k">Assistant ID</span><span class="tiny">${esc(business.vapi_assistant_id || "not provisioned")}</span></div>
        <div class="row" style="margin-top:12px">
          <button class="btn sm dark grow" data-act="provision">${business.vapi_assistant_id ? "Re-sync assistant" : "Provision assistant"}</button>
        </div>
        ${
          state.provisioning
            ? `<div class="notice ${state.provisioning.provisioned ? "ok" : "demo"}" style="margin-top:10px">
                 ${
                   state.provisioning.provisioned
                     ? "Assistant is live in Vapi."
                     : `Dry-run: the assistant payload is built and ready. Add <b>VAPI_API_KEY</b> to go live.`
                 }
               </div>`
            : ""
        }
        <p class="tiny soft" style="margin-top:10px">The assistant must disclose it is an AI, capture name/phone/address/service/time, and escalate anything unusual to you by text.</p>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Integrations</h2></div>
      <div class="card">
        <div class="kv"><span class="k">Texting</span><span class="badge ${integrations.sms === "twilio" ? "done" : "open"}">${integrations.sms}</span></div>
        <div class="kv"><span class="k">Payments</span><span class="badge ${integrations.payments === "stripe" ? "done" : "open"}">${integrations.payments}</span></div>
        <div class="kv"><span class="k">Voice</span><span class="badge ${integrations.voice === "configured" ? "done" : "open"}">${integrations.voice}</span></div>
        <p class="tiny soft" style="margin-top:10px">Set TWILIO_*, STRIPE_*, and VAPI_* environment variables to switch each one live. Nothing else changes.</p>
      </div>
    </section>`;
}

/* ------------------------------------------------------------------ more */
function moreTab() {
  const business = state.business;
  return `
    <section class="section">
      <div class="section-head"><h2>Business profile</h2></div>
      <div class="card">
        <div class="form-grid">
          <div class="field"><label>Business name</label><input id="set-name" value="${esc(business.name)}" /></div>
          <div class="form-grid two">
            <div class="field"><label>Owner name</label><input id="set-owner" value="${esc(business.owner_name)}" /></div>
            <div class="field"><label>Owner mobile</label><input id="set-owner-phone" value="${esc(business.owner_phone)}" /></div>
          </div>
          <div class="form-grid two">
            <div class="field"><label>Business line</label><input id="set-line" value="${esc(business.phone_number || "")}" placeholder="+1418..." /></div>
            <div class="field"><label>City</label><input id="set-city" value="${esc(business.city || "")}" /></div>
          </div>
          <div class="field"><label>Service area</label><input id="set-area" value="${esc(business.service_area || "")}" /></div>
          <div class="field"><label>Google review link</label><input id="set-review" value="${esc(business.review_url || "")}" /></div>
          <div class="field"><label>e-Transfer email</label><input id="set-etransfer" value="${esc(business.etransfer_email || "")}" /></div>
          <div class="field"><label>SMS footer</label><input id="set-footer" value="${esc(business.sms_footer || "")}" /></div>
          <label class="row small" style="gap:8px"><input type="checkbox" id="set-hst" style="width:auto" ${business.hst_enabled ? "checked" : ""}/> Charge sales tax (${esc(business.tax_profile)})</label>
        </div>
        <button class="btn primary block" style="margin-top:12px" data-act="save-business">Save profile</button>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Hours</h2><span class="tiny muted">used for slots</span></div>
      <div class="card">
        ${["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
          .map((day) => {
            const window = (business.hours || {})[day];
            return `<div class="kv">
              <span class="k" style="text-transform:capitalize">${day}</span>
              <span class="row" style="gap:6px">
                <input class="hour-input" data-day="${day}" data-i="0" type="time" value="${window?.[0] || ""}" style="width:110px;padding:7px 8px;font-size:14px" />
                <input class="hour-input" data-day="${day}" data-i="1" type="time" value="${window?.[1] || ""}" style="width:110px;padding:7px 8px;font-size:14px" />
              </span>
            </div>`;
          })
          .join("")}
        <button class="btn sm ghost block" style="margin-top:10px" data-act="save-hours">Save hours</button>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Text commands</h2></div>
      <div class="card">
        <div class="kv"><span class="k">TODAY</span><span>Your schedule</span></div>
        <div class="kv"><span class="k">DONE 3</span><span>Invoice job #3</span></div>
        <div class="kv"><span class="k">DONE 3 145</span><span>Invoice at $145</span></div>
        <div class="kv"><span class="k">PAID INV-1004</span><span>Mark e-transfer received</span></div>
        <div class="kv"><span class="k">CONFIRM 3 tomorrow 9am</span><span>Book a callback</span></div>
        <div class="kv"><span class="k">OPEN</span><span>Free slots this week</span></div>
        <p class="tiny soft" style="margin-top:10px">Text these to your business line from your mobile. The assistant treats your number as the owner.</p>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Compliance & data</h2></div>
      <div class="card">
        <div class="notice info">The AI introduces itself as an AI on every call. Price quotes are ranges only. Texts carry “Reply STOP” and opt-outs are stored per customer.</div>
        <div class="row" style="margin-top:10px;flex-wrap:wrap">
          <button class="btn sm ghost" data-act="view-messages">Message log</button>
          <button class="btn sm ghost" data-act="view-calls">Call log</button>
          <a class="btn sm ghost" href="/static/privacy.html" target="_blank" rel="noopener">Privacy</a>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>Account</h2></div>
      <div class="card">
        <div class="kv"><span class="k">Plan</span><span>${esc(business.plan)} (${esc(business.plan_status)})</span></div>
        <div class="kv"><span class="k">Trial ends</span><span>${business.trial_ends_at ? new Date(business.trial_ends_at).toLocaleDateString("en-CA") : "—"}</span></div>
        <div class="kv"><span class="k">Timezone</span><span>${esc(business.timezone)}</span></div>
        <button class="btn danger block" style="margin-top:12px" data-act="logout">Sign out</button>
      </div>
    </section>`;
}

/* --------------------------------------------------------------- actions */
root.addEventListener("click", async (event) => {
  const tabButton = event.target.closest("[data-tab]");
  if (tabButton) {
    state.tab = tabButton.dataset.tab;
    if (state.tab === "jobs") await loadJobs();
    if (state.tab === "money") await loadMoney();
    if (state.tab === "assistant" && !state.billing) await loadBilling();
    renderApp();
    window.scrollTo({ top: 0 });
    return;
  }

  const tradeButton = event.target.closest("[data-trade]");
  if (tradeButton) {
    state.onboarding.trade = tradeButton.dataset.trade;
    document.querySelectorAll(".trade").forEach((node) => node.classList.toggle("on", node === tradeButton));
    return;
  }

  const filterButton = event.target.closest("[data-filter]");
  if (filterButton) {
    state.jobFilter = filterButton.dataset.filter;
    await loadJobs();
    renderTabInto();
    return;
  }

  const action = event.target.closest("[data-act]");
  if (!action) return;
  const id = action.dataset.id;
  const act = action.dataset.act;

  try {
    switch (act) {
      case "request-code": {
        const phone = document.getElementById("phone").value.trim();
        if (!phone) return toast("Enter your mobile number", "err");
        const result = await api("/api/auth/request-code", { method: "POST", body: JSON.stringify({ phone }) });
        state.authPhone = phone;
        state.demoCode = result.demo_code || null;
        state.authStep = "code";
        renderAuth();
        toast(result.demo_code ? "Demo code generated" : "Code sent by text");
        return;
      }
      case "verify-code": {
        const code = document.getElementById("code").value.trim();
        const result = await api("/api/auth/verify", { method: "POST", body: JSON.stringify({ phone: state.authPhone, code }) });
        state.business = result.business;
        await loadDashboard();
        renderApp();
        return;
      }
      case "back-phone":
        state.authStep = "phone";
        state.demoCode = null;
        renderAuth();
        return;
      case "demo-login": {
        const result = await api("/api/auth/demo", { method: "POST" });
        state.business = result.business;
        await loadDashboard();
        renderApp();
        toast("Signed in to the demo business");
        return;
      }
      case "start-onboarding":
        state.onboarding.step = 0;
        renderOnboarding();
        return;
      case "back-auth":
        state.onboarding.step = 0;
        renderAuth();
        return;
      case "ob-back":
        state.onboarding.step = Math.max(0, state.onboarding.step - 1);
        renderOnboarding();
        return;
      case "ob-next": {
        if (state.onboarding.step === 0) {
          state.onboarding.step = 1;
          renderOnboarding();
          return;
        }
        const name = document.getElementById("ob-name").value.trim();
        const owner = document.getElementById("ob-owner").value.trim();
        const phone = document.getElementById("ob-phone").value.trim();
        const city = document.getElementById("ob-city").value.trim();
        if (!name || !owner || !phone) return toast("Business name, your name, and mobile are required", "err");
        state.onboarding.draft = {
          name,
          owner,
          phone,
          city,
          province: document.getElementById("ob-province").value,
          area: document.getElementById("ob-area").value.trim(),
        };
        state.onboarding.step = 2;
        renderOnboarding();
        return;
      }
      case "ob-create": {
        const draft = state.onboarding.draft || {};
        const payload = {
          business_name: draft.name,
          owner_name: draft.owner,
          owner_phone: draft.phone,
          trade: state.onboarding.trade,
          city: draft.city,
          province: draft.province || "QC",
          service_area: draft.area,
          review_url: document.getElementById("ob-review")?.value.trim() || null,
          etransfer_email: document.getElementById("ob-etransfer")?.value.trim() || null,
          greeting: document.getElementById("ob-greeting")?.value.trim() || null,
        };
        const result = await api("/api/auth/signup", { method: "POST", body: JSON.stringify(payload) });
        state.business = result.business;
        state.onboarding = { step: 0, trade: "snow_removal", services: [] };
        await loadDashboard();
        renderApp();
        toast("You're live. Text HELP to your line to try commands.");
        return;
      }
      case "refresh":
        await refreshAll();
        toast("Refreshed");
        return;
      case "done":
        return openDoneSheet(id);
      case "confirm":
        return openConfirmSheet(id);
      case "reschedule":
        return openConfirmSheet(id, true);
      case "open-job":
        return openJobSheet(id);
      case "invoice-actions":
        return openInvoiceSheet(id);
      case "save-greeting": {
        const greeting = document.getElementById("greeting").value.trim();
        await api("/api/me", { method: "PATCH", body: JSON.stringify({ greeting }) });
        state.business.greeting = greeting;
        toast("Greeting saved");
        return;
      }
      case "preview-prompt": {
        const data = await api("/api/agent/prompt");
        openSheet(`
          <h2>Master prompt</h2>
          <p class="small muted" style="margin:6px 0 12px">Rendered from your business profile. This is exactly what the assistant receives.</p>
          <div class="code">${esc(data.system_prompt)}</div>
          <div style="height:12px"></div>
          <div class="row">
            <button class="btn sm ghost grow" data-act="copy-prompt">Copy</button>
            <button class="btn sm dark grow" data-act="provision">Provision in Vapi</button>
          </div>`);
        state._lastPrompt = data.system_prompt;
        return;
      }
      case "copy-prompt":
        navigator.clipboard?.writeText(state._lastPrompt || "");
        toast("Prompt copied");
        return;
      case "provision": {
        state.provisioning = await api("/api/agent/provision", { method: "POST" });
        closeSheet();
        state.tab = "assistant";
        renderApp();
        toast(state.provisioning.provisioned ? "Assistant provisioned" : "Dry-run payload built");
        return;
      }
      case "plan": {
        const plan = action.dataset.plan;
        const result = await api("/api/billing/checkout", { method: "POST", body: JSON.stringify({ plan }) });
        if (result.url) window.location.href = result.url;
        else {
          toast(result.message || "Plan updated");
          await loadBilling();
          renderTabInto();
        }
        return;
      }
      case "save-business": {
        const payload = {
          name: document.getElementById("set-name").value.trim(),
          owner_name: document.getElementById("set-owner").value.trim(),
          owner_phone: document.getElementById("set-owner-phone").value.trim(),
          phone_number: document.getElementById("set-line").value.trim() || null,
          city: document.getElementById("set-city").value.trim(),
          service_area: document.getElementById("set-area").value.trim(),
          review_url: document.getElementById("set-review").value.trim() || null,
          etransfer_email: document.getElementById("set-etransfer").value.trim() || null,
          sms_footer: document.getElementById("set-footer").value.trim(),
          hst_enabled: document.getElementById("set-hst").checked,
        };
        state.business = await api("/api/me", { method: "PATCH", body: JSON.stringify(payload) });
        await loadDashboard();
        renderApp();
        toast("Profile saved");
        return;
      }
      case "save-hours": {
        const hours = {};
        for (const day of ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]) {
          const inputs = [...document.querySelectorAll(`.hour-input[data-day="${day}"]`)];
          const start = inputs[0]?.value;
          const end = inputs[1]?.value;
          hours[day] = start && end ? [start, end] : null;
        }
        await api("/api/me", { method: "PATCH", body: JSON.stringify({ hours }) });
        state.business.hours = hours;
        toast("Hours saved");
        return;
      }
      case "view-messages": {
        const messages = await api("/api/messages?limit=40");
        openSheet(`
          <h2>Message log</h2>
          <p class="small muted" style="margin:6px 0 12px">Every text in and out, kept for consent records.</p>
          <div class="thread">
            ${messages
              .map(
                (message) => `<div class="msg-bubble ${message.direction === "in" ? "in" : "out"}">
                  <div class="tiny soft" style="margin-bottom:3px">${message.direction === "in" ? "them" : "you → " + esc(message.to)} · ${esc(relTime(message.created_at))} · ${esc(message.status)}</div>
                  ${esc(message.body)}</div>`
              )
              .join("") || `<p class="muted small">No messages yet.</p>`}
          </div>`);
        return;
      }
      case "view-calls": {
        const calls = await api("/api/calls?limit=20");
        openSheet(`
          <h2>Call log</h2>
          <div class="stack" style="margin-top:12px">
            ${
              calls
                .map(
                  (call) => `
              <div class="card">
                <div class="row between"><b>${esc(call.caller || "Unknown")}</b><span class="tiny soft">${Math.round(call.duration_seconds / 60)} min · ${esc(relTime(call.started_at))}</span></div>
                <p class="small muted" style="margin-top:6px">${esc(call.summary || "No summary recorded.")}</p>
                ${call.job_id ? `<span class="badge done" style="margin-top:8px">Job booked</span>` : `<span class="badge needs" style="margin-top:8px">Follow up</span>`}
              </div>`
                )
                .join("") || `<p class="muted small">No calls yet.</p>`
            }
          </div>`);
        return;
      }
      case "logout":
        await api("/api/auth/logout", { method: "POST" });
        state.business = null;
        state.dash = null;
        state.authStep = "phone";
        renderAuth();
        return;
    }

    /* Sheet-hosted actions */
    switch (act) {
      case "close-sheet":
        closeSheet();
        return;
      case "confirm-now": {
        const start = action.dataset.start;
        await api(`/api/jobs/${id}/confirm`, { method: "POST", body: JSON.stringify({ start }) });
        closeSheet();
        await refreshAll();
        toast("Job confirmed and customer texted");
        return;
      }
      case "do-done": {
        const amount = parseInt(document.getElementById("done-amount").value * 100, 10);
        const method = document.getElementById("done-method").value;
        const already = document.getElementById("done-already").checked;
        await api(`/api/jobs/${id}/done`, {
          method: "POST",
          body: JSON.stringify({
            amount_cents: Number.isFinite(amount) ? amount : null,
            method: already ? null : method,
            already_paid: already,
            paid_via: method === "etransfer" ? "etransfer" : "cash",
          }),
        });
        closeSheet();
        await refreshAll();
        toast(already ? "Marked paid — review text scheduled" : "Invoice sent to the customer");
        return;
      }
      case "job-cancel": {
        await api(`/api/jobs/${id}/cancel`, { method: "POST" });
        closeSheet();
        await refreshAll();
        toast("Job cancelled");
        return;
      }
      case "invoice-send": {
        await api(`/api/invoices/${id}/send`, { method: "POST" });
        closeSheet();
        await refreshAll();
        toast("Invoice re-sent");
        return;
      }
      case "invoice-paid": {
        const via = document.getElementById("paid-via")?.value || "etransfer";
        await api(`/api/invoices/${id}/paid`, { method: "POST", body: JSON.stringify({ via }) });
        closeSheet();
        await refreshAll();
        toast("Marked paid — receipt sent");
        return;
      }
      case "invoice-open": {
        window.open(`/pay/${id}`, "_blank", "noopener");
        return;
      }
      case "new-job": {
        const services = state.business.services || [];
        openSheet(`
          <h2>New job</h2>
          <div class="form-grid" style="margin-top:12px">
            <div class="field"><label>Customer name</label><input id="nj-name" placeholder="Name" /></div>
            <div class="field"><label>Mobile</label><input id="nj-phone" type="tel" placeholder="(418) 555-0123" /></div>
            <div class="field"><label>Address</label><input id="nj-address" placeholder="Street, city" /></div>
            <div class="field"><label>Service</label><select id="nj-service">${services
              .map((s) => `<option value="${s.key}">${esc(s.name)}</option>`)
              .join("")}</select></div>
            <div class="field"><label>Start (optional)</label><input id="nj-start" type="datetime-local" /></div>
          </div>
          <button class="btn primary block" style="margin-top:12px" data-act="create-job">Create job</button>`);
        return;
      }
      case "create-job": {
        const payload = {
          customer_name: document.getElementById("nj-name").value.trim() || null,
          customer_phone: document.getElementById("nj-phone").value.trim() || null,
          address: document.getElementById("nj-address").value.trim() || null,
          service_key: document.getElementById("nj-service").value,
          preferred_start: document.getElementById("nj-start").value || null,
          source: "owner",
        };
        const result = await api("/api/jobs", { method: "POST", body: JSON.stringify(payload) });
        closeSheet();
        await refreshAll();
        toast(result.status === "confirmed" ? "Job created and confirmed" : "Job saved — confirm the time");
        return;
      }
    }
  } catch (error) {
    toast(error.message || "That didn't work", "err");
  }
});

/* ------------------------------------------------------------- sheet views */
function openSheet(html) {
  sheetBody.innerHTML = html;
  sheetEl.hidden = false;
}
function closeSheet() {
  sheetEl.hidden = true;
  sheetBody.innerHTML = "";
}
sheetEl.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-sheet]")) closeSheet();
});

async function openConfirmSheet(jobId, reschedule = false) {
  const job = (state.jobs || []).find((j) => j.id === jobId) ||
    (state.dash.today || []).find((j) => j.id === jobId) ||
    (state.dash.upcoming || []).find((j) => j.id === jobId) ||
    (state.dash.needs_action || []).find((j) => j.id === jobId);
  const serviceKey = job?.service_key || "";
  const availability = await api(`/api/availability?service_key=${encodeURIComponent(serviceKey)}&days_ahead=10`);
  const slots = availability.days.flatMap((day) =>
    day.slots.slice(0, 2).map((slot) => ({ label: day.label, slot }))
  );
  openSheet(`
    <h2>${reschedule ? "Reschedule" : "Confirm"} ${esc(job?.service || "job")}</h2>
    <p class="small muted" style="margin:6px 0 12px">
      ${esc(job?.customer?.name || "Customer")}${job?.requested_for ? " asked for " + esc(job.requested_for) : ""}.
      The customer and you both get a text when you confirm.
    </p>
    <div class="stack">
      ${
        slots.length
          ? slots
              .slice(0, 8)
              .map(
                (option) => `
        <button class="btn ghost block" style="justify-content:space-between" data-act="confirm-now" data-id="${jobId}" data-start="${esc(option.slot)}">
          <span>${esc(option.label)} · ${esc(shortTime(option.slot))}</span>
          <span class="badge confirmed">Pick</span>
        </button>`
              )
              .join("")
          : `<div class="notice warn">No open slots in the next 10 days. Check your hours, or call the customer with a date.</div>`
      }
    </div>
    <p class="tiny soft" style="margin-top:12px">Times are ${esc(state.business.timezone)} and account for travel between jobs.</p>`);
}

function openDoneSheet(jobId) {
  const job = (state.jobs || []).find((j) => j.id === jobId) ||
    (state.dash.today || []).find((j) => j.id === jobId) ||
    (state.dash.upcoming || []).find((j) => j.id === jobId);
  const suggested = job?.price_final_cents || job?.estimate_low_cents || 0;
  openSheet(`
    <h2>Finish job ${job ? "#" + job.number : ""}</h2>
    <p class="small muted" style="margin:6px 0 12px">${esc(job?.service || "")} for ${esc(job?.customer?.name || "customer")}. Tax is added automatically.</p>
    <div class="form-grid">
      <div class="field"><label>Amount before tax (CAD)</label>
        <input id="done-amount" type="number" inputmode="decimal" step="0.01" value="${(suggested / 100).toFixed(2)}" /></div>
      <div class="field"><label>How they'll pay</label>
        <select id="done-method">
          <option value="stripe">Card link by text (Stripe)</option>
          <option value="etransfer">Interac e-Transfer</option>
          <option value="cash">Cash / cheque</option>
        </select>
      </div>
      <label class="row small" style="gap:8px"><input type="checkbox" id="done-already" style="width:auto" /> Already paid — just record it</label>
    </div>
    <button class="btn primary block" style="margin-top:14px" data-act="do-done" data-id="${jobId}">Create invoice &amp; text customer</button>`);
}

async function openJobSheet(jobId) {
  const job = await api(`/api/jobs/${jobId}`);
  const call = (job.calls || [])[0];
  openSheet(`
    <div class="row between">
      <h2>Job #${job.number}</h2>
      ${statusBadge(job)}
    </div>
    <div class="card" style="margin-top:12px;box-shadow:none">
      <div class="kv"><span class="k">Service</span><span>${esc(job.service)}</span></div>
      <div class="kv"><span class="k">When</span><span>${job.scheduled_start ? esc(dayLabel(job.scheduled_start) + " · " + shortTime(job.scheduled_start)) : esc(job.requested_for || "to confirm")}</span></div>
      <div class="kv"><span class="k">Customer</span><span>${esc(job.customer?.name || "—")}</span></div>
      <div class="kv"><span class="k">Phone</span><span>${esc(job.customer?.phone || "—")}</span></div>
      <div class="kv"><span class="k">Address</span><span>${esc(job.address || "—")}</span></div>
      <div class="kv"><span class="k">Estimate</span><span>${money(job.estimate_low_cents)}–${money(job.estimate_high_cents)}</span></div>
      <div class="kv"><span class="k">Source</span><span>${job.source === "voice" ? "AI phone call" : esc(job.source)}</span></div>
    </div>
    ${job.notes ? `<div class="notice info" style="margin-top:10px">${esc(job.notes)}</div>` : ""}
    ${
      call
        ? `<div class="section" style="margin-top:16px">
             <div class="section-head"><h2>Call summary</h2><span class="tiny muted">${Math.round(call.duration_seconds / 60)} min</span></div>
             <div class="card" style="box-shadow:none"><p class="small">${esc(call.summary || "")}</p>
             ${call.transcript ? `<details style="margin-top:8px"><summary class="small" style="cursor:pointer;color:var(--teal)">Transcript</summary><div class="code" style="margin-top:8px">${esc(call.transcript)}</div></details>` : ""}
             </div>
           </div>`
        : ""
    }
    <div class="row" style="margin-top:16px;flex-wrap:wrap">
      ${job.status === "confirmed" ? `<button class="btn primary grow" data-act="done" data-id="${job.id}">Done → invoice</button>` : ""}
      ${job.status === "needs_confirmation" ? `<button class="btn primary grow" data-act="confirm" data-id="${job.id}">Confirm</button>` : ""}
      <button class="btn danger" data-act="job-cancel" data-id="${job.id}">Cancel</button>
    </div>`);
}

function openInvoiceSheet(invoiceId) {
  const invoice = (state.invoices || []).find((i) => i.id === invoiceId);
  if (!invoice) return;
  openSheet(`
    <h2>${esc(invoice.number)}</h2>
    <p class="small muted" style="margin:6px 0 12px">${esc(invoice.customer_name || "Customer")} · ${esc(invoice.service || "")}</p>
    <div class="card" style="box-shadow:none">
      <div class="kv"><span class="k">Subtotal</span><span>${money(invoice.subtotal_cents)}</span></div>
      ${(invoice.tax_breakdown || [])
        .map((component) => `<div class="kv"><span class="k">${esc(component.label)} (${(+((component.rate * 100).toFixed(3)))}%)</span><span>${money(component.amount_cents)}</span></div>`)
        .join("")}
      <div class="kv"><span class="k bold">Total</span><span class="bold">${money(invoice.total_cents)}</span></div>
      <div class="kv"><span class="k">Chasers sent</span><span>${invoice.reminders_sent}</span></div>
    </div>
    <div class="form-grid" style="margin-top:12px">
      <div class="field"><label>Mark paid via</label>
        <select id="paid-via">
          <option value="etransfer">Interac e-Transfer</option>
          <option value="stripe">Card (Stripe)</option>
          <option value="cash">Cash</option>
          <option value="cheque">Cheque</option>
        </select>
      </div>
    </div>
    <div class="row" style="margin-top:12px;flex-wrap:wrap">
      <button class="btn primary grow" data-act="invoice-paid" data-id="${invoice.id}">Mark paid</button>
      <button class="btn ghost" data-act="invoice-send" data-id="${invoice.id}">Re-send</button>
      <button class="btn ghost" data-act="invoice-open" data-id="${invoice.id}">Pay page</button>
    </div>`);
}

/* --------------------------------------------------------------- loading */
async function loadJobs() {
  const map = {
    upcoming: "requested,needs_confirmation,confirmed,in_progress",
    needs: "requested,needs_confirmation",
    done: "done,invoiced,paid",
    all: null,
  };
  const status = map[state.jobFilter];
  state.jobs = await api("/api/jobs" + (status ? `?status=${status}` : ""));
}

async function loadMoney() {
  state.invoices = await api("/api/invoices");
  const paid = state.invoices.filter((i) => i.status === "paid");
  const totals = { subtotal: 0, gst: 0, qst: 0, hst: 0 };
  for (const invoice of paid) {
    totals.subtotal += invoice.subtotal_cents;
    for (const component of invoice.tax_breakdown || []) {
      if (component.label === "GST") totals.gst += component.amount_cents;
      if (component.label === "QST") totals.qst += component.amount_cents;
      if (component.label === "HST") totals.hst += component.amount_cents;
    }
  }
  state.taxTotals = totals;
  await loadBilling();
}

async function loadBilling() {
  try {
    state.billing = await api("/api/billing/summary");
  } catch {
    state.billing = null;
  }
}

function renderTabInto() {
  const container = document.getElementById("tab-content");
  if (container) container.innerHTML = renderTab();
}

async function refreshAll() {
  await loadDashboard();
  if (state.tab === "jobs") await loadJobs();
  if (state.tab === "money") await loadMoney();
  renderApp();
}

/* ------------------------------------------------------------------ start */
bootApp();
