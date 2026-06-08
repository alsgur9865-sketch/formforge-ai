# FormForge AI

> **Adversarial Multi-Agent Workout Form Coach with Self-Improving Critique Loop**

Built with **Google Cloud Agent Builder** (via [Google ADK](https://google.github.io/adk-docs/) + Cloud Run), powered by **Gemini** (2.5 Pro / 2.5 Flash / 3.5 Flash), integrating the **Arize Phoenix MCP** partner server.

- 🎥 **Demo Video**: _coming soon_
- 🌐 **Live URL**: https://formforge-app-988838927510.us-central1.run.app
- 🏆 **Hackathon**: [Google Cloud Rapid Agent Hackathon](https://rapid-agent.devpost.com) — **Arize Track**

---

## Hackathon Compliance — Google Cloud Rapid Agent Hackathon

- **Agent Builder**: Built with **Google ADK** (the official open-source Agent Development Kit of Google Cloud Agent Builder), deployed on **Cloud Run** (an Agent Builder-supported runtime).
- **Powered by Gemini**: `gemini-2.5-pro` (multimodal video — Encourager / Scrutinizer / Mediator / PoseExtractor Stage 2), `gemini-2.5-flash` (auxiliary), `gemini-3.5-flash` (LLM-as-a-Judge).
- **Partner MCP**: **Arize Phoenix MCP** — custom `mcp/phoenix_mcp_server.py` (FastMCP) wrapping Phoenix REST API + Firestore + Vector Search; the Mediator agent calls `query_past_debates` and `query_similar_safety_flags` for self-introspection.
- **Track**: Arize.

---

## What It Does

Two AI coaches with opposing personalities — **The Encourager** (warm certified PT, 10 years) and **The Scrutinizer** (rigorous exercise physiologist, PhD) — analyze your workout video and **debate in real time** about your form. **The Mediator** synthesizes their arguments with your past training context (retrieved via Phoenix MCP) into a balanced verdict with action items.

Every user reaction (`too_harsh` / `too_soft` / `perfect` / etc.) is evaluated by an LLM-as-a-Judge that adjusts the personas bidirectionally. Over time, the two coaches **evolve into your personal critic pair**.

---

## Tech Stack

| Layer | Tech |
|---|---|
| Agent Runtime | Google ADK (Python) |
| Models | Gemini 2.5 Pro, 2.5 Flash, 3.5 Flash |
| Pose Extraction | MediaPipe Pose + Gemini Vision (2-stage) |
| Observability | Arize Phoenix Cloud (auto-instrumentation) |
| MCP | Custom FastMCP server (Python) |
| DB | Firestore |
| Vector Search | Vertex AI Vector Search |
| Embeddings | `multimodalembedding-001` |
| UI | Streamlit (polling-based, 1s refresh) |
| Deploy | Cloud Run (single container: app + in-process MCP stdio subprocess) |
| Storage | Cloud Storage |

---

## Architecture

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full system design including the 4-agent orchestration, the 2-stage pose pipeline (MediaPipe + Gemini), the Phoenix MCP custom wrapper, and the self-improvement loop.

---

## Setup

```bash
# 1. Clone
git clone https://github.com/<your-username>/formforge-ai
cd formforge-ai

# 2. Install (Python 3.11+)
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env: fill GOOGLE_CLOUD_PROJECT, GEMINI_API_KEY, PHOENIX_API_KEY, etc.

# 4. Run locally
streamlit run ui/streamlit_app.py
```

For Cloud Run deployment see [`deploy/`](./deploy/).

---

## Medical Disclaimer

⚠️ This tool provides **informational analysis only**. It is **not medical advice**. If you experience pain, injury, or persistent discomfort during exercise, consult a qualified healthcare or fitness professional before continuing.

---

## License

MIT — see [`LICENSE`](./LICENSE).
