# Jorge's AI System — Where Everything Lives

A reference guide to every part of the system: GHL, the bot server, and the dashboard.

---

## GoHighLevel (GHL)

**Login:** app.gohighlevel.com → your account → sub-account "Rancho Cucamonga, ca"

---

### Workflows
**Path:** Left sidebar → **Automation** → **Workflows** → click the **"AI Workflow"** folder

These are the automations that receive incoming texts and decide what the AI does with them.

| Workflow name | What it does |
|---|---|
| 1. Inbound SMS Trigger | Fires every time a new text comes in |
| 2. (your routing logic) | Routes contact to the correct qualifier step |
| 3. (your routing logic) | Continues flow |
| 4. (your routing logic) | Continues flow |
| **5. Process Message — Which Bot?** | **The main brain** — reads the contact's tags and calls the correct bot (seller, buyer, or lead). This is where `Jorge-Active` is checked. |
| Hot Seller Workflow | Fires when a seller scores "hot" — fires follow-up sequence |

To **edit a workflow**: click the folder, click the workflow name, click **Edit** (pencil icon top-right).

To **pause all automations for one contact**: add the `Jorge-Active` tag to that contact (see Tags below).

---

### Tags
**Path:** Left sidebar → **Contacts** → open any contact → scroll to Tags section

Tags are how GHL and the bots communicate. The bots add/remove tags automatically. You can add/remove them manually too.

| Tag | Who sets it | What it means |
|---|---|---|
| `Needs Qualifying` | Bot or you | Routes contact to the **seller bot** or **lead bot** |
| `Buyer-Lead` | Bot or you | Routes contact to the **buyer bot** |
| `seller_hot` | Seller bot | Seller scored HOT (accepted offer, good timeline) |
| `seller_warm` | Seller bot | Seller scored WARM (qualified, needs nurturing) |
| `seller_cold` | Seller bot | Seller scored COLD (not yet qualified) |
| `Handoff-Lead-to-Seller` | Lead bot | Lead was handed off to seller bot |
| `Handoff-Lead-to-Buyer` | Lead bot | Lead was handed off to buyer bot |
| `Handoff-Buyer-to-Seller` | Buyer bot | Buyer was handed off to seller bot |
| `Handoff-Seller-to-Buyer` | Seller bot | Seller was handed off to buyer bot |
| **`Jorge-Active`** | **You** | **Bot goes silent — you handle the conversation manually. Remove the tag to let the bot resume.** |

**How to take over a conversation:**
1. Go to the contact in GHL
2. Click their Tags field → type `Jorge-Active` → save
3. Text the contact yourself — the bot will not respond
4. When you're done → remove `Jorge-Active` → bot picks up on the next reply

---

### Custom Fields (Contact Data)
**Path:** Left sidebar → **Contacts** → open any contact → scroll down to "Custom Fields" section

To **see all available fields**: Settings → **Custom Fields** → Contact Fields

These fields are filled in automatically as the bots qualify leads.

| Field | Filled by | What it stores |
|---|---|---|
| `seller_temperature` | Seller bot | hot / warm / cold |
| `seller_questions_answered` | Seller bot | 0–4 (how many Q1–Q4 answered) |
| `property_condition` | Seller bot | What seller said about the home condition |
| `seller_price_expectation` | Seller bot | What seller expects to get |
| `seller_motivation` | Seller bot | Why they're selling |
| `ai_lead_score` | Lead bot | 0–100 lead score |
| `lead_temperature` | Lead bot | hot / warm / cold |
| `budget_min` | Lead/Buyer bot | Minimum budget |
| `budget_max` | Lead/Buyer bot | Maximum budget |
| `timeline` | Lead/Buyer bot | How quickly they want to move |
| `financing_status` | Lead/Buyer bot | Cash / pre-approved / not started |
| `bot_type` | Routing bot | Which bot is handling this contact |

---

### Bot Connections (Webhooks)
**Path:** Inside any workflow → look for **"Custom Action"** or **"Webhook"** steps

These are the steps that call the bot server. In the Railway deployment, use one shared webhook URL:

```
https://lead-bot-production-8fd6.up.railway.app/api/ghl/webhook
```

GHL should not call separate buyer, seller, or lead bot URLs. It should always call the shared webhook, and the backend should route based on `customData.bot_type`.

---

## Railway (Bot Server)

**Path:** Railway project -> select service -> **Settings** -> **Networking**

This is where you create or inspect the public domain for the Lead Bot service. Railway will generate an HTTPS domain ending in `.up.railway.app`. That Lead Bot public domain is the URL you put into GHL.

Current production domains:
- Lead Bot (use in GHL): `https://lead-bot-production-8fd6.up.railway.app`
- Seller Bot: `https://seller-bot-production.up.railway.app`
- Buyer Bot: `https://buyer-bot-production.up.railway.app`

| Section | Path in Railway | What you can do |
|---|---|---|
| **Networking** | service → **Settings** → **Networking** | Generate the public domain used by GHL |
| **Logs** | service → **Observability** or **Deployments** | See every message the bot processed, errors, tag writes |
| **Variables** | service → **Variables** | View/change API keys (GHL key, Anthropic key, etc.) |
| **Deployments** | service → **Deployments** | See deploy history and latest release |
| **Metrics** | service → **Metrics** | Check health, resource usage, and restarts |

**Bot endpoints you can call directly**:

```
GET  /health                          — check if server is running
GET  /admin/settings                  — see current bot tone/question overrides
PUT  /admin/settings/seller           — update seller bot settings
GET  /api/jorge-seller/{id}/progress  — check a contact's Q1–Q4 progress
```

**Note:** Settings (system prompt, phrases, questions) are stored in bot memory — they reset if the server restarts. The Lyrio dashboard re-saves them automatically on load. If tone settings ever disappear, go to the Tone page in the dashboard and hit Save.

---

## Lyrio Dashboard (Streamlit)

**URL:** https://lyrio-jorge.streamlit.app

**Login:** not required — it's private by URL

| Page | What's on it |
|---|---|
| **Chat** | Concierge — ask questions about your leads in plain English. "How many hot leads this week?" |
| **Bots** | Bot Command Center — see which bots are active, conversation stats |
| **Costs** | AI cost tracker — monthly Claude API spend, ROI calculation |
| **Activity** | Lead activity feed — every bot action in chronological order |
| **Leads** | Lead browser — search and filter your contacts |
| **Tone** | Edit the seller bot's voice — system prompt, opener phrases, Q1–Q4 questions |

**Tone page is the main one you'll use.** It's a direct connection to the live bot — changes apply immediately without any restart.

---

## Quick Reference — "Where do I go to…"

| Task | Where |
|---|---|
| See why a lead isn't getting bot replies | GHL → Contacts → check if `Jorge-Active` tag is on them |
| Change what the bot says in its first message | Lyrio Dashboard → **Tone** → Opener phrases |
| Change Q1–Q4 questions | Lyrio Dashboard → **Tone** → Q1–Q4 questions |
| Change the bot's personality/persona | Lyrio Dashboard → **Tone** → System prompt |
| See how qualified a seller lead is | GHL → Contact → Custom Fields (`seller_questions_answered`, `seller_temperature`) |
| Manually take over a conversation | Add `Jorge-Active` tag to contact in GHL |
| See the bot's recent activity / errors | Railway → service → **Observability** or **Deployments** |
| See lead scores and AI cost | Lyrio Dashboard → **Activity** or **Costs** |
| Find which workflow routes texts to bots | GHL → Automation → Workflows → "AI Workflow" folder → "5. Process Message — Which Bot?" |
| Update the GHL API key | Railway → service → **Variables** → `GHL_API_KEY` |
| Update the Anthropic (Claude) API key | Railway → service → **Variables** → `ANTHROPIC_API_KEY` |
