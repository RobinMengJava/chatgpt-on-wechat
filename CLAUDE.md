# CLAUDE.md

This project is **CowAgent** (chatgpt-on-wechat) — a self-hosted AI assistant framework built on top of the open-source [zhayujie/chatgpt-on-wechat](https://github.com/zhayujie/chatgpt-on-wechat). Robin maintains a custom fork of this project long-term.

## Project Structure

```
app.py                  # Entry point — initializes ChannelManager
config.py               # 150+ config options, read config.json at runtime
config-template.json    # Template for user config.json (not committed)
bridge/                 # Routes messages between channels and models
  agent_bridge.py       # Core agent integration
  agent_initializer.py  # Agent setup
  bridge.py             # Message routing
agent/                  # Agent framework
  chat/                 # Conversation handling
  memory/               # Long-term & short-term memory
  tools/                # System tools (bash, browser, file I/O, web search, etc.)
  skills/               # Skill creation & execution engine
  protocol/             # Agent protocol definitions
  prompt/               # Prompt templates
channel/                # Communication channel adapters
  weixin/               # Personal WeChat
  wechatmp/             # WeChat Official Account
  feishu/               # Feishu (Lark)
  dingtalk/             # DingTalk
  web/                  # Web interface
  terminal/             # Terminal channel (for local testing)
models/                 # LLM integrations (21 models)
plugins/                # Plugin system
common/                 # Shared utilities, logging, token bucket
voice/                  # Voice processing
translate/              # Translation support
```

## Tech Stack

- **Language:** Python 3.7+
- **Key deps:** `openai`, `anthropic`, `aiohttp`, `agentmesh-sdk`, `linkai`, `web.py`
- **Channel SDKs:** `wechatpy`, `lark-oapi`, `dingtalk_stream`
- **Config:** `config.json` (from `config-template.json`), managed via `config.py`

## Running Locally

```bash
pip install -r requirements.txt
# Copy and fill in config-template.json -> config.json
python app.py
```

For quick management (start/stop/config):
```bash
bash run.sh
```

Docker:
```bash
docker-compose -f docker/docker-compose.yml up
```

## Configuration

User config lives in `config.json` (not committed). Key fields:
- `channel_type` — which channel to use (e.g. `terminal` for local testing)
- `model` — default LLM model
- `agent` — enable agent mode
- API keys for each model and channel

## Development Notes

- The `terminal` channel is useful for local testing without WeChat/Feishu setup
- Plugins in `plugins/` can be enabled/disabled via config
- Model integrations follow a consistent interface defined in `models/`
- The agent framework supports multi-step task execution with tools and memory
- `config.py` is the canonical reference for all available config options
