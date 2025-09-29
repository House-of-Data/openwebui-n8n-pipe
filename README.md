# N8N AI Agent Connector Pipe for Open WebUI

This repository provides a custom pipe for [Open WebUI](https://github.com/open-webui/open-webui) 
that connects directly to an [n8n](https://n8n.io) workflow.

The pipe sends the user’s current message and metadata from Open WebUI to n8n, 
where an AI Agent node handles orchestration with any LLM backend (OpenAI, Ollama, local models, etc.), 
and then returns the generated result.

---

## ✨ Features
- **Direct n8n integration** – replaces the model call in Open WebUI with a call to your n8n workflow.
- **Metadata-rich** – chat, message, session, and user IDs always included for memory management; optional user details configurable via valves.
- **Configurable** – server address, webhook path, auth headers, timeout, and debugging toggles.
- **Non-streaming** – responses are returned as a single message (no SSE).
- **Clean contract** – expects the default n8n behaviour of *“Respond with first item”* from a Respond to Webhook node.

---

## 🛠 Installation
### Option 1
Get the pipe from Open WebUI [N8N AI Agent Connector Pipe](https://openwebui.com/f/colinwheeler/n8n_ai_agent_connector_pipe)
### Option 2
1. Copy the code from (`N8N_AI_Agent_Connector.openwebui.py`) into your new function window in the Open WebUI UI (Admin Panel-Functions) and save it.
2. In the Open WebUI UI, configure the pipe valves:
   - `SERVER_ADDRESS`: e.g. `http://n8n:5678`
   - `WEBHOOK_PATH`: your n8n webhook ID
   - `WEBHOOK_ENV`: `production` or `test`
   - `AUTH_HEADER_KEY`: defaults to `Authorization`
   - `AUTH_HEADER_VALUE`: set if your n8n webhook requires it
   - `TIMEOUT_SECONDS`: increase if your agent takes longer to reply
   - Metadata toggles (user name, timezone, etc.) as needed

---

## ⚙️ n8n Setup
An example workflow is provided in the file openwebui-n8n-pipe.json
1. Create a workflow with a **Webhook (Trigger)** node and an **AI Agent** node.
2. End with a **Respond to Webhook** node set to *“Respond with first item”*.
3. The pipe expects the response shape:
```json
{
  "output": "Hello world",
  "intermediateSteps": []
}
```
---

## 📌 Versioning
- **v1.0.0** – Baseline release.

**Tested with:**
- Open WebUI **v0.6.32**
- n8n **v1.110.1**

---

## 📂 Repository
- GitHub: [House-of-Data/openwebui-n8n-pipe](https://github.com/House-of-Data/openwebui-n8n-pipe)
- Open WebUI: [N8N AI Agent Connector Pipe](https://openwebui.com/f/colinwheeler/n8n_ai_agent_connector_pipe)

---

## 👤 Authors
- **Colin Wheeler**, House of Data GmbH, Switzerland  
- **ChatGPT**, collaborative development and review
