# openwebui-n8n-pipe
This pipe connects Open WebUI to an external n8n workflow. It sends the user’s current message and metadata to n8n, which routes the request to an AI Agent node (backed by any model provider such as OpenAI, Ollama, or local LLMs) and returns the generated result.
