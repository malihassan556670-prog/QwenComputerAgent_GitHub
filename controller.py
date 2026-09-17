import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import pyautogui
import pyperclip
import requests
from playwright.sync_api import sync_playwright

MODEL = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
BASE_DIR = Path(__file__).resolve().parent
SCREENSHOT_DIR = BASE_DIR / "screenshots"
MAX_STEPS = 10
MAX_HISTORY_MESSAGES = 6
MAX_RESULT_CHARS = 5000
SCREENSHOT_DIR.mkdir(exist_ok=True)

browser = None
page = None
playwright = None

SYSTEM_PROMPT = r"""
You are a local Windows computer-use agent.
Return ONLY valid JSON. No Markdown and no explanation outside JSON.
Do not claim success unless the tool result says success=true.

Tools:
OPEN_WEBSITE {"tool":"OPEN_WEBSITE","args":{"url":"https://example.com"}}
SEARCH_WEB {"tool":"SEARCH_WEB","args":{"query":"python"}}
READ_PAGE {"tool":"READ_PAGE","args":{}}
CLICK_TEXT {"tool":"CLICK_TEXT","args":{"text":"Sign in"}}
TYPE_TEXT {"tool":"TYPE_TEXT","args":{"text":"hello"}}
BROWSER_BACK {"tool":"BROWSER_BACK","args":{}}
BROWSER_FORWARD {"tool":"BROWSER_FORWARD","args":{}}
NEW_TAB {"tool":"NEW_TAB","args":{"url":"https://example.com"}}
BROWSER_TASK {"tool":"BROWSER_TASK","args":{"task":"search Google for YouTube"}}
LIST_FILES {"tool":"LIST_FILES","args":{"path":"."}}
READ_FILE {"tool":"READ_FILE","args":{"path":"file.txt"}}
WRITE_FILE {"tool":"WRITE_FILE","args":{"path":"file.txt","content":"Hello"}}
CREATE_FOLDER {"tool":"CREATE_FOLDER","args":{"path":"folder"}}
RUN_COMMAND {"tool":"RUN_COMMAND","args":{"command":"python app.py"}}
OPEN_APP {"tool":"OPEN_APP","args":{"app":"notepad"}}
SCREENSHOT {"tool":"SCREENSHOT","args":{}}
MOUSE_POSITION {"tool":"MOUSE_POSITION","args":{}}
MOUSE_MOVE {"tool":"MOUSE_MOVE","args":{"x":500,"y":400}}
MOUSE_CLICK {"tool":"MOUSE_CLICK","args":{"x":500,"y":400,"button":"left"}}
KEY_PRESS {"tool":"KEY_PRESS","args":{"key":"ENTER"}}
TYPE_KEYBOARD {"tool":"TYPE_KEYBOARD","args":{"text":"hello"}}
CLIPBOARD_COPY {"tool":"CLIPBOARD_COPY","args":{}}
CLIPBOARD_PASTE {"tool":"CLIPBOARD_PASTE","args":{}}
MULTI_ACTION {"tool":"MULTI_ACTION","args":{"actions":[{"tool":"OPEN_WEBSITE","args":{"url":"https://google.com"}}]}}

Allowed Windows apps: notepad, calculator, paint, explorer, cmd, powershell.
"""

def ok(message):
    return {"success": True, "message": str(message)[:MAX_RESULT_CHARS]}

def fail(message):
    return {"success": False, "message": str(message)[:MAX_RESULT_CHARS]}

def safe_path(value):
    p = (BASE_DIR / value).resolve()
    try:
        p.relative_to(BASE_DIR.resolve())
    except ValueError:
        raise ValueError("Path is outside the project folder.")
    return p

def dangerous(command):
    patterns = [
        "format ", "diskpart", "shutdown", "restart-computer",
        "remove-item", "del /s", "rd /s", "rmdir /s",
        "reg delete", "cipher /w", "takeown", "bcdedit"
    ]
    low = command.lower()
    return any(x in low for x in patterns)

def confirm(command):
    print("\nWARNING: potentially destructive/system-changing command:")
    print(command)
    return input("Type YES to continue: ").strip() == "YES"

def extract_json(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    decoder = json.JSONDecoder()
    objs = []
    pos = 0
    while pos < len(text):
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            break
        try:
            obj, end = decoder.raw_decode(text, pos)
            objs.append(obj)
            pos = end
        except json.JSONDecodeError:
            nxt = text.find("{", pos + 1)
            if nxt == -1:
                break
            pos = nxt

    if len(objs) == 1:
        return objs[0]
    if len(objs) > 1:
        return {"tool": "MULTI_ACTION", "args": {
            "actions": [{"tool": x.get("tool", ""), "args": x.get("args", {})}
                        for x in objs if isinstance(x, dict)]
        }}
    return None

def ask_qwen(messages):
    if len(messages) > MAX_HISTORY_MESSAGES + 1:
        messages = [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "10m",
        "options": {"temperature": 0.1, "num_ctx": 4096}
    }
    start = time.time()
    response = requests.post(OLLAMA_URL, json=payload, timeout=180)
    response.raise_for_status()
    data = response.json()
    print(f"[Qwen response time: {time.time() - start:.1f}s]")
    content = data.get("message", {}).get("content")
    if not content:
        raise RuntimeError("Ollama returned no model message.")
    return content

def ensure_browser():
    global browser, page, playwright
    if page is not None:
        return
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=False, channel="chrome")
    except Exception:
        browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()

def open_web(args):
    try:
        ensure_browser()
        url = args.get("url", "").strip()
        if not url:
            return fail("No URL supplied.")
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return ok(f"Opened {page.url}\nTitle: {page.title()}")
    except Exception as e:
        return fail(f"OPEN_WEBSITE failed: {e}")

def search_web(args):
    q = args.get("query", "").strip()
    if not q:
        return fail("No search query supplied.")
    return open_web({"url": "https://www.google.com/search?q=" + quote_plus(q)})

def read_page(args):
    try:
        ensure_browser()
        return ok(f"URL: {page.url}\nTITLE: {page.title()}\n\n{page.locator('body').inner_text(timeout=10000)}")
    except Exception as e:
        return fail(f"READ_PAGE failed: {e}")

def click_text(args):
    try:
        ensure_browser()
        text = args.get("text", "").strip()
        if not text:
            return fail("No text supplied.")
        loc = page.get_by_text(text, exact=True).first
        if loc.count() == 0:
            loc = page.get_by_text(text, exact=False).first
        loc.click(timeout=10000)
        return ok(f"Clicked: {text}")
    except Exception as e:
        return fail(f"CLICK_TEXT failed: {e}")

def type_text(args):
    try:
        ensure_browser()
        text = args.get("text", "")
        active = page.locator(":focus")
        if active.count():
            try:
                active.fill(text)
                return ok("Typed into focused browser element.")
            except Exception:
                pass
        page.keyboard.type(text)
        return ok("Typed text.")
    except Exception as e:
        return fail(f"TYPE_TEXT failed: {e}")

def browser_nav(method):
    try:
        ensure_browser()
        getattr(page, method)(wait_until="domcontentloaded", timeout=20000)
        return ok(page.url)
    except Exception as e:
        return fail(f"{method} failed: {e}")

def new_tab(args):
    global page
    try:
        ensure_browser()
        page = browser.new_page()
        url = args.get("url", "").strip()
        if url:
            if not re.match(r"^https?://", url, re.I):
                url = "https://" + url
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return ok(f"New tab: {page.url}")
    except Exception as e:
        return fail(f"NEW_TAB failed: {e}")

def browser_task(args):
    task = args.get("task", "").strip()
    match = re.search(r"search(?: for)?\s+(.+)", task, re.I)
    if match:
        return search_web({"query": match.group(1).strip()})
    return fail("BROWSER_TASK could not convert this task safely.")

def list_files(args):
    try:
        p = safe_path(args.get("path", "."))
        if not p.exists() or not p.is_dir():
            return fail(f"Folder does not exist: {p}")
        items = []
        for x in sorted(p.iterdir(), key=lambda z: (not z.is_dir(), z.name.lower())):
            items.append(("DIR " if x.is_dir() else "FILE") + "  " + x.name)
        return ok("\n".join(items) or "(empty)")
    except Exception as e:
        return fail(f"LIST_FILES failed: {e}")

def read_file(args):
    try:
        p = safe_path(args.get("path", ""))
        if not p.is_file():
            return fail(f"File does not exist: {p}")
        return ok(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return fail(f"READ_FILE failed: {e}")

def write_file(args):
    try:
        p = safe_path(args.get("path", ""))
        content = args.get("content", "")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ok(f"Wrote {len(content)} characters to {p}")
    except Exception as e:
        return fail(f"WRITE_FILE failed: {e}")

def create_folder(args):
    try:
        p = safe_path(args.get("path", ""))
        p.mkdir(parents=True, exist_ok=True)
        return ok(f"Folder created: {p}")
    except Exception as e:
        return fail(f"CREATE_FOLDER failed: {e}")

def run_command(args):
    command = args.get("command", "").strip()
    if not command:
        return fail("No command supplied.")
    if dangerous(command) and not confirm(command):
        return fail("Command cancelled by user.")
    try:
        cp = subprocess.run(command, shell=True, cwd=str(BASE_DIR),
                            capture_output=True, text=True, timeout=120)
        output = (cp.stdout or "") + (cp.stderr or "")
        if cp.returncode != 0:
            return fail(f"Exit code: {cp.returncode}\n{output}")
        return ok(f"Exit code: 0\n{output}")
    except subprocess.TimeoutExpired:
        return fail("Command timed out after 120 seconds.")
    except Exception as e:
        return fail(f"RUN_COMMAND failed: {e}")

def open_app(args):
    allowed = {
        "notepad": "notepad.exe", "calculator": "calc.exe",
        "paint": "mspaint.exe", "explorer": "explorer.exe",
        "cmd": "cmd.exe", "powershell": "powershell.exe"
    }
    app = args.get("app", "").lower().strip()
    if app not in allowed:
        return fail(f"App not allowed: {app}")
    try:
        subprocess.Popen([allowed[app]])
        return ok(f"Opened {app}")
    except Exception as e:
        return fail(f"OPEN_APP failed: {e}")

def screenshot(args):
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = SCREENSHOT_DIR / f"screenshot_{stamp}.png"
        pyautogui.screenshot().save(p)
        return ok(f"Screenshot saved to {p}")
    except Exception as e:
        return fail(f"SCREENSHOT failed: {e}")

def mouse_position(args):
    try:
        x, y = pyautogui.position()
        return ok(f"x={x}, y={y}")
    except Exception as e:
        return fail(f"MOUSE_POSITION failed: {e}")

def mouse_move(args):
    try:
        x, y = int(args["x"]), int(args["y"])
        pyautogui.moveTo(x, y, duration=0.15)
        return ok(f"Moved to x={x}, y={y}")
    except Exception as e:
        return fail(f"MOUSE_MOVE failed: {e}")

def mouse_click(args):
    try:
        x, y = int(args["x"]), int(args["y"])
        button = args.get("button", "left")
        if button not in {"left", "right", "middle"}:
            return fail("Invalid mouse button.")
        pyautogui.click(x=x, y=y, button=button)
        return ok(f"Clicked {button} at x={x}, y={y}")
    except Exception as e:
        return fail(f"MOUSE_CLICK failed: {e}")

def key_press(args):
    try:
        key = args.get("key", "").strip()
        if not key:
            return fail("No key supplied.")
        pyautogui.press(key)
        return ok(f"Pressed {key}")
    except Exception as e:
        return fail(f"KEY_PRESS failed: {e}")

def type_keyboard(args):
    try:
        pyautogui.write(args.get("text", ""), interval=0.01)
        return ok("Keyboard text typed.")
    except Exception as e:
        return fail(f"TYPE_KEYBOARD failed: {e}")

def clipboard_copy(args):
    try:
        return ok(pyperclip.paste())
    except Exception as e:
        return fail(f"CLIPBOARD_COPY failed: {e}")

def clipboard_paste(args):
    try:
        pyperclip.hotkey("ctrl", "v")
        return ok("Clipboard pasted.")
    except Exception as e:
        return fail(f"CLIPBOARD_PASTE failed: {e}")

TOOLS = {
    "OPEN_WEBSITE": open_web, "SEARCH_WEB": search_web, "READ_PAGE": read_page,
    "CLICK_TEXT": click_text, "TYPE_TEXT": type_text,
    "BROWSER_BACK": lambda a: browser_nav("go_back"),
    "BROWSER_FORWARD": lambda a: browser_nav("go_forward"),
    "NEW_TAB": new_tab, "BROWSER_TASK": browser_task,
    "LIST_FILES": list_files, "READ_FILE": read_file,
    "WRITE_FILE": write_file, "CREATE_FOLDER": create_folder,
    "RUN_COMMAND": run_command, "OPEN_APP": open_app,
    "SCREENSHOT": screenshot, "MOUSE_POSITION": mouse_position,
    "MOUSE_MOVE": mouse_move, "MOUSE_CLICK": mouse_click,
    "KEY_PRESS": key_press, "TYPE_KEYBOARD": type_keyboard,
    "CLIPBOARD_COPY": clipboard_copy, "CLIPBOARD_PASTE": clipboard_paste,
}

def execute(tool, args):
    if tool == "MULTI_ACTION":
        actions = args.get("actions", [])
        if not isinstance(actions, list) or not actions:
            return fail("MULTI_ACTION has no actions.")
        for i, action in enumerate(actions, 1):
            if not isinstance(action, dict):
                return fail(f"Action {i} is invalid.")
            name = action.get("tool", "")
            if name not in TOOLS:
                return fail(f"Action {i}: unknown tool {name}")
            print(f"  -> Action {i}: {name}")
            r = TOOLS[name](action.get("args", {}))
            if not r["success"]:
                return fail(f"Action {i} ({name}) failed: {r['message']}")
        return ok("All multi-actions completed.")
    if tool not in TOOLS:
        return fail(f"Unknown tool: {tool}")
    return TOOLS[tool](args)

def direct_command(text):
    if not text.startswith("!"):
        return False
    command = text[1:].strip()
    if not command:
        print("Usage: !<command>")
        return True
    print(f"\n[DIRECT COMMAND] {command}")
    r = run_command({"command": command})
    print(r["message"])
    return True

def run_agent(task):
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task}]
    print("\n" + "=" * 42)
    print("STARTING TASK")
    print("=" * 42)
    print("Task:", task)

    for step in range(1, MAX_STEPS + 1):
        print(f"\n[Agent step {step}/{MAX_STEPS}]")
        try:
            text = ask_qwen(messages)
        except KeyboardInterrupt:
            print("\nTASK TERMINATED\nReason: Ctrl+C")
            return
        except Exception as e:
            print("\nTASK TERMINATED\nReason:", e)
            return

        print("Qwen:")
        print(text)

        action = extract_json(text)
        if not action:
            print("\nTASK TERMINATED\nReason: Qwen returned invalid JSON.")
            return

        tool = action.get("tool")
        if not tool:
            print("\nTASK TERMINATED\nReason: JSON has no tool name.")
            return

        print("Executing:", tool)
        try:
            r = execute(tool, action.get("args", {}))
        except KeyboardInterrupt:
            print("\nTASK TERMINATED\nReason: Ctrl+C")
            return
        except Exception as e:
            r = fail(f"Unhandled tool error: {e}")

        if not r["success"]:
            print("Status: FAILED")
            print(r["message"])
            print("\n" + "=" * 42)
            print("TASK TERMINATED")
            print("Failed step:", tool)
            print("What happened:", r["message"])
            print("=" * 42)
            return

        print("Status: SUCCESS")
        print(r["message"])

        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content":
            f"Tool result for {tool}: {json.dumps(r, ensure_ascii=False)}\n"
            "Continue the task. Return only valid JSON."})

    print("\n" + "=" * 42)
    print("TASK TERMINATED")
    print(f"Reason: Maximum of {MAX_STEPS} agent steps reached.")
    print("=" * 42)

def cleanup():
    global browser, playwright
    try:
        if browser:
            browser.close()
    except Exception:
        pass
    try:
        if playwright:
            playwright.stop()
    except Exception:
        pass

def main():
    print("=" * 42)
    print("QWEN COMPUTER AGENT")
    print("=" * 42)
    print("Model:", MODEL)
    print("Project:", BASE_DIR)
    print("Direct command example: !ollama ps")
    print("Press Ctrl+C to stop.")

    while True:
        try:
            text = input("\nYou > ").strip()
            if not text:
                continue
            if text.lower() in {"exit", "quit"}:
                break
            if direct_command(text):
                continue
            run_agent(text)
        except KeyboardInterrupt:
            print("\nAgent stopped with Ctrl+C.")
            break
        except EOFError:
            break
    cleanup()

if __name__ == "__main__":
    try:
        main()
    finally:
        cleanup()
