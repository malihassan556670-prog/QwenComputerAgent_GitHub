# Qwen Computer Agent

A local Windows computer-agent prototype powered by **Qwen3 8B + Ollama**.

## Features
- Browser automation with Playwright + Google Chrome
- Terminal commands
- File listing, reading, writing, and folder creation
- Mouse and keyboard control
- Clipboard support
- Screenshot capture
- Multi-action execution
- Immediate failure reporting
- Basic confirmation for destructive/system-changing commands
- Local-only inference through Ollama

> **Status:** v0.1 / Work in Progress. This is a text/tool-based agent. Screenshot capture is implemented, but Qwen3 8B does not directly interpret screenshot pixels.

## Requirements
- Windows 10/11
- Python 3.10+
- Ollama
- Qwen3 8B
- Google Chrome

## Install

```powershell
ollama pull qwen3:8b

cd "$HOME\Desktop\QwenComputerAgent"
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
```

Run:

```powershell
.\venv\Scripts\python.exe controller.py
```

Or double-click `start_ai.bat`.

## Examples

```text
Open Google
```

```text
Search Google for Python cybersecurity projects
```

```text
Create a file called test.txt and write Hello World
```

```text
Run python app.py
```

For a command that should execute immediately without waiting for Qwen, use `!`:

```text
!ollama ps
```

## Architecture

```text
User
  |
  v
Controller
  |
  +--> Ollama --> Qwen3 8B
  |
  +--> Tool Executor
         +-- Browser / Chrome
         +-- Terminal
         +-- Files
         +-- Mouse / Keyboard
         +-- Clipboard
         +-- Screenshots
```

## Safety

System-changing commands such as formatting disks, shutdown/restart, registry deletion, recursive deletion, boot configuration changes, and ownership changes require confirmation.

Review commands before confirming them.

## Limitations
- Qwen3 8B can be slow when CPU/GPU memory is shared.
- This is not yet a full visual computer-use system.
- Screenshots are saved but are not interpreted by the text model.
- Browser tasks work best with accessible page text/DOM.
- Autonomous coding/debugging remains a prototype and should be supervised.

## Roadmap
- [x] Local Qwen3 + Ollama
- [x] Browser automation
- [x] Terminal tools
- [x] File tools
- [x] Mouse/keyboard tools
- [x] Clipboard
- [x] Screenshots
- [x] Multi-action execution
- [x] Failure-aware execution
- [ ] Vision-capable screenshot understanding
- [ ] Better planning
- [ ] Faster context management
- [ ] Persistent memory
- [ ] Stronger coding/debugging workflow

## License
MIT License. See `LICENSE`.
