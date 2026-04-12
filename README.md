# LaunchMind — GeoRank

> **FAST NUCES — Agentic AI / Multi-Agent Systems — Group Assignment**

## What Is GeoRank?

GeoRank is a **Generative Engine Optimization (GEO)** platform for e-commerce store owners. When customers ask ChatGPT, Claude, or Gemini *"What's the best running shoe under $100?"* or *"Where can I buy organic coffee online?"*, GeoRank ensures **your store** is the answer. It audits LLM citation rates, rewrites product descriptions using GEO best practices, and generates structured data markup that language models understand.

---

## Agent Architecture

```
 ┌──────────────────────────────────────────────────────┐
 │                   CEO Agent (Orchestrator)            │
 │  LLM calls: decompose idea • review spec • QA verdict│
 └───┬───────────────┬──────────────┬────────────────────┘
     │ task          │ task         │ task
     ▼               ▼             ▼
 ┌────────┐   ┌──────────┐  ┌──────────────┐
 │Product │   │Engineer  │  │  Marketing   │
 │Agent   │   │Agent     │  │  Agent       │
 │        │   │          │  │              │
 │LLM:    │   │LLM:      │  │LLM:          │
 │spec gen│   │HTML gen  │  │copy gen      │
 └────┬───┘   │GitHub:   │  │SendGrid:     │
      │ spec  │• Issue   │  │• email       │
      │       │• Branch  │  │Slack:        │
      │       │• Commit  │  │• Block Kit   │
      │       │• PR      │  │  message     │
      │       └────┬─────┘  └──────┬───────┘
      │            │ PR URL         │ copy
      └────────────┴────────────────┘
                   │ (both results)
                   ▼
           ┌──────────────┐
           │  QA Agent    │
           │              │
           │LLM: HTML +   │
           │copy review   │
           │GitHub:       │
           │PR comments   │
           └──────┬───────┘
                  │ verdict
                  ▼
           CEO: if fail → revision_request → Engineer
           CEO: post final Slack summary
```

**Message flow:** All agents communicate via a JSON file message bus. Every message has `message_id`, `from_agent`, `to_agent`, `message_type`, `payload`, `timestamp`.

**Feedback loops:**
1. CEO → reviews Product spec with LLM → sends `revision_request` if not GEO-specific enough
2. CEO → reviews QA verdict → sends `revision_request` to Engineer if QA fails

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/your-username/launchmind-geo
cd launchmind-geo
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env with your real credentials
```

Required variables:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) — needs `repo` scope |
| `GITHUB_REPO` | `your-username/launchmind-geo` (create this public repo first) |
| `SLACK_BOT_TOKEN` | [api.slack.com/apps](https://api.slack.com/apps) — Bot OAuth Token (`xoxb-...`) |
| `SLACK_CHANNEL` | `#launches` (create and invite the bot) |
| `SENDGRID_API_KEY` | [app.sendgrid.com](https://app.sendgrid.com/settings/api_keys) |
| `FROM_EMAIL` | Verified sender in SendGrid |
| `TO_EMAIL` | Your test inbox |

### 3. Run

```bash
python main.py
```

---

## Platform Integrations

| Platform | Agent | Action |
|---|---|---|
| **GitHub** | Engineer | Creates issue "Initial landing page", commits `index.html` to new branch, opens PR |
| **GitHub** | QA | Posts 2+ review comments on the PR (HTML review + copy review) |
| **Slack** | Marketing | Posts Block Kit launch announcement to `#launches` |
| **Slack** | CEO | Posts final pipeline summary to `#launches` |
| **SendGrid** | Marketing | Sends cold outreach email (HTML + plain text) |
| **Anthropic Claude** | CEO, Product, Engineer, Marketing, QA | LLM reasoning at every stage |

---

## Links

- **GitHub PR:** _(fill in after first run)_
- **Slack workspace:** _(add invite link)_

---

## Group Members

| Name | Agent |
|---|---|
| Ali | CEO Agent + Marketing + QA Agents |
| Saamer | Product + Engineer Agents |

