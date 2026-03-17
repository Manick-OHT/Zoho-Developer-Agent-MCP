# 🤖 Zoho Creator MCP Browser Agent

Control your Chrome browser from Claude Desktop to build Zoho Creator applications using natural language.

```
You (Claude Desktop) → MCP Server (Python) → Playwright (Chrome) → Zoho Creator
```

## ⚡ Quick Setup (Windows)

### 1. Prerequisites
- **Python 3.10+** — [Download](https://www.python.org/downloads/)
- **Claude Desktop** — [Download](https://claude.ai/download)

### 2. Install Dependencies
```batch
cd "M:\Creator Agent"
setup.bat
```

### 3. Configure Claude Desktop

Open Claude Desktop → **Settings** → **Developer** → **Edit Config**

This opens `%APPDATA%\Claude\claude_desktop_config.json`. Paste this:

```json
{
  "mcpServers": {
    "zoho-creator-agent": {
      "command": "M:\\Creator Agent\\venv\\Scripts\\python.exe",
      "args": ["M:\\Creator Agent\\server.py"]
    }
  }
}
```

> ⚠️ If you already have other MCP servers configured, add the `"zoho-creator-agent"` entry inside the existing `"mcpServers"` object.

### 4. Restart Claude Desktop
Close and reopen Claude Desktop. You should see a **🔨 hammer icon** near the chat input — this means the MCP server is connected!

## 🚀 Usage

Just chat naturally in Claude Desktop. Examples:

| Prompt | What Happens |
|--------|-------------|
| "Launch the browser and go to Zoho Creator" | Opens Chrome, navigates to creator.zoho.com |
| "Take a screenshot" | Shows you the current browser state |
| "Click on Create Application" | Clicks the button in Chrome |
| "Create a CRM app with Customers and Contacts" | Multi-step: creates app, forms, fields |
| "Add fields: Name, Email, Phone to Customers" | Adds fields to the form |

### First Time — Zoho Login
The first time, you'll need to log into Zoho:
1. Say: *"Launch browser and go to Zoho Creator"*
2. Say: *"Type my email user@example.com in the login field"*
3. Complete any 2FA manually in the Chrome window
4. After login, **your session persists** — no re-login needed!

## 🛠️ Available Tools

| Tool | Description |
|------|-------------|
| `launch_browser` | Open Chrome with persistent profile |
| `navigate` | Go to any URL |
| `screenshot` | See current page state |
| `click` | Click by text, selector, or coordinates |
| `type_text` | Type into input fields |
| `select_option` | Select from dropdowns |
| `press_key` | Press keyboard keys (Enter, Tab, etc.) |
| `scroll` | Scroll up or down |
| `drag_drop` | Drag and drop between coordinates |
| `hover` | Hover over elements |
| `fill_form` | Fill multiple fields at once |
| `execute_js` | Run JavaScript on the page |
| `get_page_info` | Read page content |
| `get_clickable_elements` | List all interactive elements |
| `zoho_open_creator` | Quick-open Zoho Creator |
| `zoho_get_page_state` | Get Creator-specific page state |

## 📁 Project Structure

```
Creator Agent/
├── server.py          # MCP server with all tools
├── requirements.txt   # Python dependencies
├── setup.bat          # Windows setup script
├── run.bat            # Run the server manually
├── .env               # Your API key & config
└── README.md          # This file
```

## ❓ Troubleshooting

**Hammer icon not showing in Claude Desktop?**
- Make sure the path in `claude_desktop_config.json` uses `\\` (double backslash)
- Restart Claude Desktop completely
- Check the MCP server logs in Claude Desktop developer console

**Browser not opening?**
- Say `launch_browser` first before any other browser commands
- Make sure Playwright Chromium is installed: `playwright install chromium`

**Zoho login not persisting?**
- The agent uses a persistent browser profile at `~/.zoho-creator-agent/browser-profile/`
- Make sure you complete the full login flow once

## 📄 License
MIT — Built for productivity.
