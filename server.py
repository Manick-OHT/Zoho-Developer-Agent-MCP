

import asyncio
import base64
import os
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

# Load environment
load_dotenv()

# ─── MCP Server ──────────────────────────────────────────────────────────────

mcp = FastMCP(
    "zoho-creator-agent",
    instructions="""You are a browser automation agent that controls Chrome to manage 
    Zoho applications. You can launch a browser, navigate pages, click elements, 
    type text, take screenshots, and perform complex UI interactions.
    
    MULTI-TAB SUPPORT:
    - Each Zoho app opens in its OWN dedicated tab (Creator, CRM, Books, Projects, etc.)
    - Use zoho_open_creator, zoho_open_crm, zoho_open_books, zoho_open_projects to open apps
    - Use zoho_open_app for any other Zoho app (Desk, Analytics, Mail, etc.)
    - Use list_tabs to see all open tabs
    - Use switch_tab to switch between tabs
    - Use close_tab to close a specific tab
    - If the user asks to open a Zoho app, ALWAYS use the dedicated zoho_open_* tool
    
    WORKFLOW:
    1. Always launch_browser first
    2. Open Zoho apps using zoho_open_* tools (each opens in its own tab)
    3. Take a screenshot to see the current state
    4. Use get_page_info to understand page structure
    5. Perform actions (click, type, navigate, etc.)
    6. Take screenshots after actions to verify results
    
    TIPS:
    - Always take a screenshot after performing actions to verify they worked
    - Use get_clickable_elements to find interactive elements on the page
    - For Zoho Creator, login first, then navigate to the app builder
    - When creating forms, add fields one at a time and verify each
    - If an action fails, try alternative selectors or approaches
    - Use switch_tab to move between Zoho apps without losing your place
    """
)

# ─── Browser State ───────────────────────────────────────────────────────────

_playwright = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None
_tabs: dict[str, Page] = {}  # name -> Page mapping for multi-tab support
_tab_counter: int = 0

PROFILE_DIR = str(Path.home() / ".zoho-creator-agent" / "browser-profile")


async def _ensure_browser():
    """Ensure browser is launched and return the active page."""
    global _playwright, _browser, _context, _page
    if _page is None or _page.is_closed():
        raise RuntimeError(
            "Browser is not launched. Call 'launch_browser' first."
        )
    return _page


async def _open_new_tab(name: str, url: str = "about:blank") -> Page:
    """Open a new tab with the given name and navigate to URL."""
    global _context, _page, _tabs, _tab_counter
    if _context is None:
        raise RuntimeError("Browser is not launched. Call 'launch_browser' first.")
    
    new_page = await _context.new_page()
    if url and url != "about:blank":
        await new_page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await new_page.wait_for_timeout(1000)
    
    _tabs[name] = new_page
    _page = new_page  # Switch active tab to the new one
    return new_page


# ─── Browser Lifecycle Tools ────────────────────────────────────────────────

@mcp.tool()
async def launch_browser(url: str = "about:blank") -> str:
    """Launch Chrome browser with persistent profile (keeps login sessions).
    Optionally navigate to a URL immediately.
    
    Args:
        url: Starting URL to navigate to (default: about:blank)
    """
    global _playwright, _browser, _context, _page, _tabs, _tab_counter

    # Close existing if any
    if _browser and _browser.is_connected():
        await _browser.close()
    if _playwright:
        await _playwright.stop()

    # Reset tab tracking
    _tabs = {}
    _tab_counter = 0

    headless = os.getenv("BROWSER_HEADLESS", "false").lower() == "true"
    slow_mo = int(os.getenv("BROWSER_SLOW_MO", "100"))

    _playwright = await async_playwright().start()

    # Use persistent context to keep login sessions
    os.makedirs(PROFILE_DIR, exist_ok=True)

    _context = await _playwright.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR,
        headless=headless,
        slow_mo=slow_mo,
        viewport={"width": 1366, "height": 768},
        args=[
            "--start-maximized",
            "--disable-blink-features=AutomationControlled",
        ],
        ignore_default_args=["--enable-automation"],
    )

    # Get the first page or create one
    if _context.pages:
        _page = _context.pages[0]
    else:
        _page = await _context.new_page()

    _tabs["main"] = _page

    if url and url != "about:blank":
        await _page.goto(url, wait_until="domcontentloaded", timeout=30000)

    return f"✅ Browser launched. Active tab: 'main'. Navigated to: {_page.url}"


@mcp.tool()
async def close_browser() -> str:
    """Close the browser and clean up resources."""
    global _playwright, _browser, _context, _page, _tabs, _tab_counter

    if _context:
        await _context.close()
        _context = None
        _page = None
        _tabs = {}
        _tab_counter = 0
    if _playwright:
        await _playwright.stop()
        _playwright = None

    return "✅ Browser closed."


# ─── Tab Management Tools ───────────────────────────────────────────────────

@mcp.tool()
async def open_new_tab(url: str = "about:blank", tab_name: str = "") -> str:
    """Open a new browser tab and navigate to a URL.
    The new tab becomes the active tab.
    
    Args:
        url: URL to open in the new tab (default: about:blank)
        tab_name: Optional name for the tab (auto-generated if not provided)
    """
    global _tab_counter
    
    if not tab_name:
        _tab_counter += 1
        tab_name = f"tab-{_tab_counter}"
    
    new_page = await _open_new_tab(tab_name, url)
    title = await new_page.title()
    
    return f"✅ New tab '{tab_name}' opened. URL: {new_page.url} | Title: {title}\nActive tab is now: '{tab_name}'"


@mcp.tool()
async def list_tabs() -> str:
    """List all open browser tabs with their names, URLs, and which one is active."""
    global _page, _tabs
    await _ensure_browser()
    
    if not _tabs:
        return f"📑 1 tab open (untracked): {_page.url}"
    
    lines = [f"📑 **{len(_tabs)}** tab(s) open:\n"]
    for name, page in _tabs.items():
        if page.is_closed():
            lines.append(f"  ❌ '{name}' — CLOSED")
            continue
        is_active = " ◄ ACTIVE" if page == _page else ""
        try:
            title = await page.title()
        except Exception:
            title = "(unknown)"
        indicator = '👉' if page == _page else '  '
        lines.append(f"  {indicator} '{name}' — {page.url} | {title}{is_active}")
    
    return "\n".join(lines)


@mcp.tool()
async def switch_tab(tab_name: str) -> str:
    """Switch the active browser tab to the specified tab.
    Use list_tabs to see available tab names.
    
    Args:
        tab_name: Name of the tab to switch to
    """
    global _page, _tabs
    await _ensure_browser()
    
    if tab_name not in _tabs:
        available = ", ".join(f"'{n}'" for n in _tabs.keys())
        return f"❌ Tab '{tab_name}' not found. Available tabs: {available}"
    
    target_page = _tabs[tab_name]
    if target_page.is_closed():
        del _tabs[tab_name]
        return f"❌ Tab '{tab_name}' was closed. It has been removed."
    
    _page = target_page
    await _page.bring_to_front()
    title = await _page.title()
    
    return f"✅ Switched to tab '{tab_name}'. URL: {_page.url} | Title: {title}"


@mcp.tool()
async def close_tab(tab_name: str) -> str:
    """Close a specific browser tab by name.
    If the closed tab was active, switches to another open tab.
    
    Args:
        tab_name: Name of the tab to close
    """
    global _page, _tabs
    await _ensure_browser()
    
    if tab_name not in _tabs:
        available = ", ".join(f"'{n}'" for n in _tabs.keys())
        return f"❌ Tab '{tab_name}' not found. Available tabs: {available}"
    
    target_page = _tabs[tab_name]
    was_active = (target_page == _page)
    
    if not target_page.is_closed():
        await target_page.close()
    del _tabs[tab_name]
    
    # If we closed the active tab, switch to another
    if was_active and _tabs:
        next_name = list(_tabs.keys())[-1]
        _page = _tabs[next_name]
        await _page.bring_to_front()
        return f"✅ Closed tab '{tab_name}'. Switched to tab '{next_name}' ({_page.url})"
    elif was_active:
        return f"✅ Closed tab '{tab_name}'. No other tabs open."
    
    return f"✅ Closed tab '{tab_name}'."


# ─── Navigation Tools ───────────────────────────────────────────────────────

@mcp.tool()
async def navigate(url: str, new_tab: bool = False, tab_name: str = "") -> str:
    """Navigate to a URL. Can open in the current tab or a new tab.
    
    Args:
        url: Full URL to navigate to (e.g., 'https://creator.zoho.com')
        new_tab: If True, open the URL in a new tab instead of the current one
        tab_name: Name for the new tab (only used when new_tab=True)
    """
    global _tab_counter
    
    if new_tab:
        if not tab_name:
            _tab_counter += 1
            tab_name = f"tab-{_tab_counter}"
        page = await _open_new_tab(tab_name, url)
        title = await page.title()
        return f"✅ Opened in new tab '{tab_name}': {page.url} | Title: {title}"
    
    page = await _ensure_browser()
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(1000)
    return f"✅ Navigated to: {page.url} | Title: {await page.title()}"


@mcp.tool()
async def go_back() -> str:
    """Go back to the previous page."""
    page = await _ensure_browser()
    await page.go_back(wait_until="domcontentloaded", timeout=15000)
    return f"✅ Went back. Now at: {page.url}"


@mcp.tool()
async def go_forward() -> str:
    """Go forward to the next page."""
    page = await _ensure_browser()
    await page.go_forward(wait_until="domcontentloaded", timeout=15000)
    return f"✅ Went forward. Now at: {page.url}"


@mcp.tool()
async def reload_page() -> str:
    """Reload the current page."""
    page = await _ensure_browser()
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    return f"✅ Reloaded: {page.url}"


# ─── Observation Tools ──────────────────────────────────────────────────────

@mcp.tool()
async def screenshot() -> str:
    """Take a screenshot of the current page. Returns the image as base64 
    that Claude can see and understand."""
    page = await _ensure_browser()
    
    screenshot_bytes = await page.screenshot(full_page=False)
    b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
    
    return f"data:image/png;base64,{b64}"


@mcp.tool()
async def get_page_info() -> str:
    """Get current page URL, title, and a summary of visible text content."""
    page = await _ensure_browser()
    
    title = await page.title()
    url = page.url
    
    # Get visible text content (limited to avoid token overflow)
    text = await page.evaluate("""
        () => {
            const body = document.body;
            if (!body) return '';
            
            // Get visible text, excluding scripts and styles
            const walker = document.createTreeWalker(
                body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: function(node) {
                        const parent = node.parentElement;
                        if (!parent) return NodeFilter.FILTER_REJECT;
                        const tag = parent.tagName.toLowerCase();
                        if (['script', 'style', 'noscript'].includes(tag)) 
                            return NodeFilter.FILTER_REJECT;
                        if (parent.offsetParent === null && tag !== 'body') 
                            return NodeFilter.FILTER_REJECT;
                        const text = node.textContent.trim();
                        if (text.length === 0) return NodeFilter.FILTER_REJECT;
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );
            
            const texts = [];
            let node;
            while (node = walker.nextNode()) {
                const t = node.textContent.trim();
                if (t) texts.push(t);
            }
            return texts.join(' | ').substring(0, 5000);
        }
    """)
    
    return f"URL: {url}\nTitle: {title}\n\nVisible Text:\n{text}"


@mcp.tool()
async def get_clickable_elements() -> str:
    """Get all clickable/interactive elements on the page with their text and selectors.
    Useful for understanding what actions you can take on the current page."""
    page = await _ensure_browser()
    
    elements = await page.evaluate("""
        () => {
            const results = [];
            const selectors = 'a, button, input, select, textarea, [role="button"], [onclick], [tabindex], [role="link"], [role="menuitem"], [role="tab"]';
            const elements = document.querySelectorAll(selectors);
            
            for (const el of elements) {
                if (el.offsetParent === null && el.tagName.toLowerCase() !== 'body') continue;
                
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type') || '';
                const text = (el.textContent || '').trim().substring(0, 100);
                const placeholder = el.getAttribute('placeholder') || '';
                const ariaLabel = el.getAttribute('aria-label') || '';
                const id = el.id || '';
                const name = el.getAttribute('name') || '';
                const value = el.value || '';
                const role = el.getAttribute('role') || '';
                
                let label = text || placeholder || ariaLabel || name || id;
                if (!label && tag === 'input') label = `${type} input`;
                if (!label) continue;
                
                let selector = '';
                if (id) selector = `#${id}`;
                else if (ariaLabel) selector = `[aria-label="${ariaLabel}"]`;
                else if (name) selector = `[name="${name}"]`;
                else if (text && ['button', 'a'].includes(tag)) selector = `text="${text.substring(0, 50)}"`;
                
                results.push({
                    tag, type, label: label.substring(0, 100), 
                    selector, role, value: value.substring(0, 50)
                });
                
                if (results.length >= 50) break;
            }
            return JSON.stringify(results, null, 2);
        }
    """)
    
    return f"Clickable elements on {page.url}:\n{elements}"


# ─── Interaction Tools ──────────────────────────────────────────────────────

@mcp.tool()
async def click(
    selector: str = "",
    text: str = "",
    x: int = 0,
    y: int = 0,
    double_click: bool = False,
    right_click: bool = False,
) -> str:
    """Click an element on the page.
    
    Provide ONE of these to identify what to click:
    - selector: CSS selector or Playwright selector (e.g., '#submit-btn', 'text="Login"')
    - text: Visible text of the element to click (e.g., 'Create Application')
    - x, y: Exact pixel coordinates to click
    
    Args:
        selector: CSS or Playwright selector
        text: Visible text to find and click
        x: X coordinate (use with y)
        y: Y coordinate (use with x)
        double_click: Double-click instead of single
        right_click: Right-click instead of left
    """
    page = await _ensure_browser()
    
    try:
        if text:
            target = page.get_by_text(text, exact=False).first
            if double_click:
                await target.dblclick(timeout=10000)
            elif right_click:
                await target.click(button="right", timeout=10000)
            else:
                await target.click(timeout=10000)
            desc = f"text '{text}'"
        elif selector:
            if double_click:
                await page.dblclick(selector, timeout=10000)
            elif right_click:
                await page.click(selector, button="right", timeout=10000)
            else:
                await page.click(selector, timeout=10000)
            desc = f"selector '{selector}'"
        elif x > 0 and y > 0:
            if double_click:
                await page.mouse.dblclick(x, y)
            elif right_click:
                await page.mouse.click(x, y, button="right")
            else:
                await page.mouse.click(x, y)
            desc = f"coordinates ({x}, {y})"
        else:
            return "❌ Error: Provide selector, text, or x/y coordinates."
        
        await page.wait_for_timeout(500)
        return f"✅ Clicked {desc}"
        
    except Exception as e:
        return f"❌ Click failed: {str(e)}"


@mcp.tool()
async def type_text(
    text: str,
    selector: str = "",
    label: str = "",
    placeholder: str = "",
    clear_first: bool = True,
    press_enter: bool = False,
) -> str:
    """Type text into an input field.
    
    Identify the field using ONE of:
    - selector: CSS selector (e.g., '#email', 'input[name="username"]')
    - label: Visible label text near the input
    - placeholder: Placeholder text of the input
    
    Args:
        text: Text to type
        selector: CSS selector for the input
        label: Label text associated with the input
        placeholder: Placeholder text of the input
        clear_first: Clear existing text before typing (default: True)
        press_enter: Press Enter after typing (default: False)
    """
    page = await _ensure_browser()
    
    try:
        if label:
            target = page.get_by_label(label).first
        elif placeholder:
            target = page.get_by_placeholder(placeholder).first
        elif selector:
            target = page.locator(selector).first
        else:
            return "❌ Error: Provide selector, label, or placeholder."
        
        if clear_first:
            await target.clear(timeout=10000)
        
        await target.fill(text, timeout=10000)
        
        if press_enter:
            await target.press("Enter")
        
        desc = label or placeholder or selector
        return f"✅ Typed '{text}' into '{desc}'"
        
    except Exception as e:
        return f"❌ Type failed: {str(e)}"


@mcp.tool()
async def select_option(selector: str, value: str = "", label: str = "") -> str:
    """Select an option from a dropdown/select element.
    
    Args:
        selector: CSS selector for the <select> element
        value: Option value to select
        label: Visible option text to select
    """
    page = await _ensure_browser()
    
    try:
        if label:
            await page.select_option(selector, label=label, timeout=10000)
        elif value:
            await page.select_option(selector, value=value, timeout=10000)
        else:
            return "❌ Error: Provide value or label."
        
        return f"✅ Selected '{label or value}' in '{selector}'"
        
    except Exception as e:
        return f"❌ Select failed: {str(e)}"


@mcp.tool()
async def press_key(key: str) -> str:
    """Press a keyboard key or key combination.
    
    Args:
        key: Key to press (e.g., 'Enter', 'Tab', 'Escape', 'Control+a', 'Control+c', 'Control+v', 'ArrowDown', 'Backspace')
    """
    page = await _ensure_browser()
    await page.keyboard.press(key)
    return f"✅ Pressed '{key}'"


@mcp.tool()
async def scroll(direction: str = "down", amount: int = 500) -> str:
    """Scroll the page.
    
    Args:
        direction: 'up' or 'down'
        amount: Pixels to scroll (default: 500)
    """
    page = await _ensure_browser()
    
    delta = amount if direction == "down" else -amount
    await page.mouse.wheel(0, delta)
    await page.wait_for_timeout(500)
    
    return f"✅ Scrolled {direction} by {amount}px"


@mcp.tool()
async def drag_drop(
    source_x: int, source_y: int,
    target_x: int, target_y: int
) -> str:
    """Drag from one position to another (useful for Zoho Creator form builder).
    
    Args:
        source_x: Starting X coordinate
        source_y: Starting Y coordinate
        target_x: Ending X coordinate
        target_y: Ending Y coordinate
    """
    page = await _ensure_browser()
    
    await page.mouse.move(source_x, source_y)
    await page.mouse.down()
    await page.wait_for_timeout(200)
    
    # Move in steps for smoother drag
    steps = 10
    for i in range(1, steps + 1):
        ix = source_x + (target_x - source_x) * i // steps
        iy = source_y + (target_y - source_y) * i // steps
        await page.mouse.move(ix, iy)
        await page.wait_for_timeout(50)
    
    await page.mouse.up()
    await page.wait_for_timeout(300)
    
    return f"✅ Dragged from ({source_x},{source_y}) to ({target_x},{target_y})"


@mcp.tool()
async def hover(selector: str = "", text: str = "", x: int = 0, y: int = 0) -> str:
    """Hover over an element (useful for revealing menus and tooltips).
    
    Args:
        selector: CSS or Playwright selector
        text: Visible text of element to hover
        x: X coordinate (use with y)
        y: Y coordinate (use with x)
    """
    page = await _ensure_browser()
    
    try:
        if text:
            await page.get_by_text(text, exact=False).first.hover(timeout=10000)
            return f"✅ Hovering over text '{text}'"
        elif selector:
            await page.hover(selector, timeout=10000)
            return f"✅ Hovering over '{selector}'"
        elif x > 0 and y > 0:
            await page.mouse.move(x, y)
            return f"✅ Hovering at ({x}, {y})"
        else:
            return "❌ Error: Provide selector, text, or coordinates."
    except Exception as e:
        return f"❌ Hover failed: {str(e)}"


@mcp.tool()
async def wait_for(seconds: float = 2.0, selector: str = "") -> str:
    """Wait for a specified time or until an element appears.
    
    Args:
        seconds: Time to wait in seconds (default: 2)
        selector: Optional CSS selector to wait for
    """
    page = await _ensure_browser()
    
    if selector:
        try:
            await page.wait_for_selector(selector, timeout=int(seconds * 1000))
            return f"✅ Element '{selector}' appeared"
        except Exception:
            return f"⚠️ Element '{selector}' did not appear within {seconds}s"
    else:
        await page.wait_for_timeout(int(seconds * 1000))
        return f"✅ Waited {seconds} seconds"


@mcp.tool()
async def execute_js(code: str) -> str:
    """Execute JavaScript code on the current page. 
    Returns the result as a string.
    
    Args:
        code: JavaScript code to execute
    """
    page = await _ensure_browser()
    
    try:
        result = await page.evaluate(code)
        return f"✅ JS Result: {str(result)[:3000]}"
    except Exception as e:
        return f"❌ JS Error: {str(e)}"


@mcp.tool()
async def copy_paste(text: str) -> str:
    """Copy text to clipboard and paste it at the current cursor position.
    
    Args:
        text: Text to paste
    """
    page = await _ensure_browser()
    
    await page.evaluate(f"navigator.clipboard.writeText({repr(text)})")
    await page.keyboard.press("Control+v")
    await page.wait_for_timeout(300)
    
    return f"✅ Pasted: '{text[:100]}'"


@mcp.tool()
async def fill_form(fields: str) -> str:
    """Fill multiple form fields at once.
    
    Args:
        fields: JSON string of field mappings, e.g.:
                '[{"selector": "#name", "value": "My App"}, {"selector": "#email", "value": "test@example.com"}]'
                or
                '[{"label": "Name", "value": "My App"}, {"placeholder": "Email", "value": "test@example.com"}]'
    """
    import json
    page = await _ensure_browser()
    
    try:
        field_list = json.loads(fields)
    except json.JSONDecodeError:
        return "❌ Invalid JSON. Pass a JSON array of {selector/label/placeholder, value} objects."
    
    results = []
    for field in field_list:
        val = field.get("value", "")
        try:
            if "label" in field:
                target = page.get_by_label(field["label"]).first
            elif "placeholder" in field:
                target = page.get_by_placeholder(field["placeholder"]).first
            elif "selector" in field:
                target = page.locator(field["selector"]).first
            else:
                results.append(f"⚠️ Skipped field (no selector): {field}")
                continue
            
            await target.clear(timeout=5000)
            await target.fill(val, timeout=5000)
            results.append(f"✅ {field.get('label') or field.get('placeholder') or field.get('selector')}: '{val}'")
        except Exception as e:
            results.append(f"❌ Failed: {str(e)[:100]}")
    
    return "\n".join(results)



# ─── Zoho Creator Browser Tools ─────────────────────────────────────────────

@mcp.tool()
async def zoho_open_creator() -> str:
    """Open Zoho Creator home page in a NEW TAB. 
    Use this as the first step for any Zoho Creator task.
    Each Zoho app opens in its own tab for easy switching."""
    global _tabs, _page
    await _ensure_browser()
    
    # If Creator tab already exists, just switch to it
    if "creator" in _tabs and not _tabs["creator"].is_closed():
        _page = _tabs["creator"]
        await _page.bring_to_front()
        await _page.reload(wait_until="domcontentloaded", timeout=30000)
        return f"✅ Switched to existing Creator tab. URL: {_page.url}"
    
    # Open in a new tab
    page = await _open_new_tab("creator", "https://creator.zoho.com")
    await page.wait_for_timeout(2000)
    
    title = await page.title()
    url = page.url
    
    if "login" in url.lower() or "accounts.zoho" in url.lower():
        return f"⚠️ Zoho login page detected in tab 'creator'. URL: {url}\nPlease use type_text and click tools to enter credentials, or log in manually if 2FA is required."
    
    return f"✅ Zoho Creator opened in tab 'creator'. URL: {url} | Title: {title}"


@mcp.tool()
async def zoho_open_crm() -> str:
    """Open Zoho CRM home page in a NEW TAB.
    Each Zoho app opens in its own tab for easy switching."""
    global _tabs, _page
    await _ensure_browser()
    
    if "crm" in _tabs and not _tabs["crm"].is_closed():
        _page = _tabs["crm"]
        await _page.bring_to_front()
        await _page.reload(wait_until="domcontentloaded", timeout=30000)
        return f"✅ Switched to existing CRM tab. URL: {_page.url}"
    
    page = await _open_new_tab("crm", "https://crm.zoho.com")
    await page.wait_for_timeout(2000)
    
    title = await page.title()
    url = page.url
    
    if "login" in url.lower() or "accounts.zoho" in url.lower():
        return f"⚠️ Zoho login page detected in tab 'crm'. URL: {url}\nPlease login first."
    
    return f"✅ Zoho CRM opened in tab 'crm'. URL: {url} | Title: {title}"


@mcp.tool()
async def zoho_open_books() -> str:
    """Open Zoho Books home page in a NEW TAB.
    Each Zoho app opens in its own tab for easy switching."""
    global _tabs, _page
    await _ensure_browser()
    
    if "books" in _tabs and not _tabs["books"].is_closed():
        _page = _tabs["books"]
        await _page.bring_to_front()
        await _page.reload(wait_until="domcontentloaded", timeout=30000)
        return f"✅ Switched to existing Books tab. URL: {_page.url}"
    
    page = await _open_new_tab("books", "https://books.zoho.com")
    await page.wait_for_timeout(2000)
    
    title = await page.title()
    url = page.url
    
    if "login" in url.lower() or "accounts.zoho" in url.lower():
        return f"⚠️ Zoho login page detected in tab 'books'. URL: {url}\nPlease login first."
    
    return f"✅ Zoho Books opened in tab 'books'. URL: {url} | Title: {title}"


@mcp.tool()
async def zoho_open_projects() -> str:
    """Open Zoho Projects home page in a NEW TAB.
    Each Zoho app opens in its own tab for easy switching."""
    global _tabs, _page
    await _ensure_browser()
    
    if "projects" in _tabs and not _tabs["projects"].is_closed():
        _page = _tabs["projects"]
        await _page.bring_to_front()
        await _page.reload(wait_until="domcontentloaded", timeout=30000)
        return f"✅ Switched to existing Projects tab. URL: {_page.url}"
    
    page = await _open_new_tab("projects", "https://projects.zoho.com")
    await page.wait_for_timeout(2000)
    
    title = await page.title()
    url = page.url
    
    if "login" in url.lower() or "accounts.zoho" in url.lower():
        return f"⚠️ Zoho login page detected in tab 'projects'. URL: {url}\nPlease login first."
    
    return f"✅ Zoho Projects opened in tab 'projects'. URL: {url} | Title: {title}"


@mcp.tool()
async def zoho_open_app(app_name: str, url: str) -> str:
    """Open any Zoho application in a NEW TAB.
    Use this for Zoho apps that don't have a dedicated tool (Desk, Analytics, etc.)
    
    Args:
        app_name: Short name for the tab (e.g., 'desk', 'analytics', 'mail')
        url: Full URL of the Zoho app (e.g., 'https://desk.zoho.com')
    """
    global _tabs, _page
    await _ensure_browser()
    
    tab_key = app_name.lower().strip()
    
    if tab_key in _tabs and not _tabs[tab_key].is_closed():
        _page = _tabs[tab_key]
        await _page.bring_to_front()
        await _page.reload(wait_until="domcontentloaded", timeout=30000)
        return f"✅ Switched to existing '{tab_key}' tab. URL: {_page.url}"
    
    page = await _open_new_tab(tab_key, url)
    await page.wait_for_timeout(2000)
    
    title = await page.title()
    current_url = page.url
    
    if "login" in current_url.lower() or "accounts.zoho" in current_url.lower():
        return f"⚠️ Zoho login page detected in tab '{tab_key}'. URL: {current_url}\nPlease login first."
    
    return f"✅ Zoho {app_name} opened in tab '{tab_key}'. URL: {current_url} | Title: {title}"


@mcp.tool()
async def zoho_get_page_state() -> str:
    """Get the current Zoho Creator page state — what section you're in, 
    what's visible, and what actions are available. 
    More specific than generic get_page_info."""
    page = await _ensure_browser()
    
    state = await page.evaluate("""
        () => {
            const result = {
                url: window.location.href,
                title: document.title,
                section: '',
                forms: [],
                fields: [],
                buttons: [],
                modals: []
            };
            
            // Detect which section of Creator we're in
            if (result.url.includes('/app/')) result.section = 'App Builder';
            else if (result.url.includes('/form/')) result.section = 'Form Editor';
            else if (result.url.includes('/report/')) result.section = 'Report';
            else if (result.url.includes('creator.zoho.com')) result.section = 'Dashboard';
            
            // Get visible buttons
            document.querySelectorAll('button, [role="button"], .zc-btn, .btn').forEach(el => {
                const text = (el.textContent || '').trim();
                if (text && el.offsetParent !== null) {
                    result.buttons.push(text.substring(0, 60));
                }
            });
            
            // Get visible modals/dialogs
            document.querySelectorAll('[role="dialog"], .modal, .zc-modal, .zc-dialog').forEach(el => {
                if (el.offsetParent !== null) {
                    result.modals.push((el.textContent || '').trim().substring(0, 200));
                }
            });
            
            // Get form fields if in form editor
            document.querySelectorAll('.fieldLabel, .zc-formfield-label, label').forEach(el => {
                const text = (el.textContent || '').trim();
                if (text) result.fields.push(text);
            });
            
            return JSON.stringify(result, null, 2);
        }
    """)
    
    return f"Zoho Creator State:\n{state}"


# ─── Zoho Creator API Tools ─────────────────────────────────────────────────

import requests as _requests
import json as _json

# Token state
_zoho_access_token: Optional[str] = None
_zoho_token_expiry: float = 0


@mcp.tool()
async def zoho_setup_auth(grant_code: str) -> str:
    """Exchange a Zoho grant code for a refresh token and save it to .env.
    This is a one-time setup tool. 
    
    STEPS FOR THE USER:
    1. Go to https://api-console.zoho.com → Self Client
    2. Enter scope: ZohoCreator.meta.READ,ZohoCreator.data.READ,ZohoCreator.data.CREATE,ZohoCreator.form.CREATE,ZohoCreator.report.READ
    3. Click Create → Copy the generated code (valid for 10 minutes)
    4. Call this tool with that code
    
    Args:
        grant_code: The grant code from Zoho API Console (valid for 10 minutes only)
    """
    client_id = os.getenv("ZOHO_CLIENT_ID", "")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        return "❌ ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET must be set in .env first."

    # Try multiple Zoho domains automatically
    domains = ["accounts.zoho.com", "accounts.zoho.in", "accounts.zoho.eu", "accounts.zoho.com.au"]
    
    for domain in domains:
        try:
            url = f"https://{domain}/oauth/v2/token"
            data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": grant_code,
            }
            
            resp = _requests.post(url, data=data, timeout=15)
            result = resp.json()
            
            if "access_token" in result and "refresh_token" in result:
                refresh_token = result["refresh_token"]
                creator_domain = domain.replace("accounts.", "creator.")
                
                # Update .env file with the refresh token and correct domain
                env_path = Path(__file__).parent / ".env"
                if env_path.exists():
                    content = env_path.read_text()
                    
                    # Update refresh token
                    import re
                    content = re.sub(
                        r'ZOHO_REFRESH_TOKEN=.*', 
                        f'ZOHO_REFRESH_TOKEN={refresh_token}', 
                        content
                    )
                    content = re.sub(
                        r'ZOHO_ACCOUNTS_DOMAIN=.*', 
                        f'ZOHO_ACCOUNTS_DOMAIN={domain}', 
                        content
                    )
                    content = re.sub(
                        r'ZOHO_CREATOR_DOMAIN=.*', 
                        f'ZOHO_CREATOR_DOMAIN={creator_domain}', 
                        content
                    )
                    
                    env_path.write_text(content)
                    
                    # Also update os.environ so it works immediately
                    os.environ["ZOHO_REFRESH_TOKEN"] = refresh_token
                    os.environ["ZOHO_ACCOUNTS_DOMAIN"] = domain
                    os.environ["ZOHO_CREATOR_DOMAIN"] = creator_domain
                
                return (
                    f"✅ Authentication successful!\n\n"
                    f"📋 Domain: {domain}\n"
                    f"📋 Refresh Token: {refresh_token[:20]}...{refresh_token[-10:]}\n"
                    f"📋 Access Token obtained (expires in {result.get('expires_in', 3600)}s)\n\n"
                    f"✅ .env file updated automatically.\n"
                    f"✅ You can now use zoho_list_applications and other API tools!\n\n"
                    f"⚠️ NOTE: Restart Claude Desktop to reload the .env if API tools still fail."
                )
            else:
                error = result.get("error", "unknown")
                if error == "invalid_client":
                    continue  # Try next domain
                elif error == "invalid_code":
                    return (
                        f"❌ The grant code has expired or is invalid.\n"
                        f"Please generate a NEW code from https://api-console.zoho.com and try again.\n"
                        f"(Codes expire after 10 minutes)"
                    )
                    
        except Exception as e:
            continue
    
    return (
        "❌ Could not authenticate with any Zoho domain (.com, .in, .eu, .com.au).\n\n"
        "Please check:\n"
        "1. Client ID and Client Secret are correct in .env\n"
        "2. The grant code was just generated (expires in 10 min)\n"
        "3. The scope includes ZohoCreator permissions"
    )


async def _get_zoho_access_token() -> str:
    """Get a valid Zoho access token, refreshing if needed."""
    global _zoho_access_token, _zoho_token_expiry

    # Return cached token if still valid (with 60s buffer)
    if _zoho_access_token and time.time() < _zoho_token_expiry - 60:
        return _zoho_access_token

    client_id = os.getenv("ZOHO_CLIENT_ID", "")
    client_secret = os.getenv("ZOHO_CLIENT_SECRET", "")
    refresh_token = os.getenv("ZOHO_REFRESH_TOKEN", "")
    accounts_domain = os.getenv("ZOHO_ACCOUNTS_DOMAIN", "accounts.zoho.com")

    if not all([client_id, client_secret, refresh_token]) or refresh_token == "PASTE_YOUR_REFRESH_TOKEN_HERE":
        raise RuntimeError(
            "Zoho API not set up yet. Ask the user to: "
            "1) Generate a code at https://api-console.zoho.com (Self Client) "
            "2) Then call the zoho_setup_auth tool with that code."
        )

    url = f"https://{accounts_domain}/oauth/v2/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    resp = _requests.post(url, data=data, timeout=15)
    result = resp.json()

    if "access_token" not in result:
        raise RuntimeError(f"Failed to refresh Zoho token: {result}")

    _zoho_access_token = result["access_token"]
    _zoho_token_expiry = time.time() + result.get("expires_in", 3600)

    return _zoho_access_token


async def _zoho_api_get_async(endpoint: str, params: dict = None) -> dict:
    """Async wrapper for Zoho Creator API GET requests."""
    global _zoho_access_token

    token = await _get_zoho_access_token()
    creator_domain = os.getenv("ZOHO_CREATOR_DOMAIN", "creator.zoho.com")
    owner = os.getenv("ZOHO_OWNER_NAME", "")

    if not owner:
        raise RuntimeError(
            "ZOHO_OWNER_NAME not configured in .env. "
            "This is your Zoho account owner name (email prefix or org name)."
        )

    base_url = f"https://{creator_domain}/api/v2/{owner}"
    url = f"{base_url}/{endpoint}"

    headers = {"Authorization": f"Zoho-oauthtoken {token}"}
    resp = _requests.get(url, headers=headers, params=params or {}, timeout=30)

    if resp.status_code == 401:
        _zoho_access_token = None
        token = await _get_zoho_access_token()
        headers = {"Authorization": f"Zoho-oauthtoken {token}"}
        resp = _requests.get(url, headers=headers, params=params or {}, timeout=30)

    return resp.json()


@mcp.tool()
async def zoho_list_applications() -> str:
    """List all Zoho Creator applications in your account.
    Use this to answer questions like 'how many apps do I have?' or 
    'what applications are in my Creator?'
    
    Returns application names, link names, and creation dates.
    """
    try:
        result = await _zoho_api_get_async("applications")

        if "applications" not in result:
            return f"❌ API Error: {_json.dumps(result, indent=2)}"

        apps = result["applications"]
        count = len(apps)

        lines = [f"✅ You have **{count}** application(s) in Zoho Creator:\n"]
        for i, app in enumerate(apps, 1):
            name = app.get("application_name", "Unknown")
            link_name = app.get("link_name", "")
            created = app.get("created_time", "")
            status = app.get("application_status", "")
            lines.append(
                f"  {i}. **{name}** (link: {link_name}) — Status: {status}"
            )
            if created:
                lines.append(f"     Created: {created}")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing applications: {str(e)}"


@mcp.tool()
async def zoho_get_application_details(app_link_name: str) -> str:
    """Get detailed info about a specific Zoho Creator application,
    including its forms, reports, and pages.
    
    Args:
        app_link_name: The link name of the application (from zoho_list_applications)
    """
    try:
        result = await _zoho_api_get_async(f"applications/{app_link_name}")

        if "application" not in result:
            return f"❌ API Error: {_json.dumps(result, indent=2)}"

        app = result["application"]
        name = app.get("application_name", "Unknown")
        link = app.get("link_name", "")
        status = app.get("application_status", "")
        created = app.get("created_time", "")

        lines = [
            f"✅ Application: **{name}**",
            f"   Link Name: {link}",
            f"   Status: {status}",
            f"   Created: {created}",
        ]

        # List components if available
        for component_type in ["forms", "reports", "pages"]:
            components = app.get(component_type, [])
            if components:
                lines.append(f"\n   {component_type.title()} ({len(components)}):")
                for c in components:
                    c_name = c.get("display_name", c.get("component_name", "Unknown"))
                    c_link = c.get("link_name", "")
                    lines.append(f"     - {c_name} (link: {c_link})")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error getting application details: {str(e)}"


@mcp.tool()
async def zoho_list_forms(app_link_name: str) -> str:
    """List all forms in a Zoho Creator application.
    
    Args:
        app_link_name: The link name of the application
    """
    try:
        result = await _zoho_api_get_async(f"applications/{app_link_name}/forms")

        if "forms" not in result:
            return f"❌ API Error: {_json.dumps(result, indent=2)}"

        forms = result["forms"]
        count = len(forms)

        lines = [f"✅ Application '{app_link_name}' has **{count}** form(s):\n"]
        for i, form in enumerate(forms, 1):
            name = form.get("display_name", form.get("component_name", "Unknown"))
            link = form.get("link_name", "")
            lines.append(f"  {i}. **{name}** (link: {link})")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing forms: {str(e)}"


@mcp.tool()
async def zoho_list_reports(app_link_name: str) -> str:
    """List all reports in a Zoho Creator application.
    
    Args:
        app_link_name: The link name of the application
    """
    try:
        result = await _zoho_api_get_async(f"applications/{app_link_name}/reports")

        if "reports" not in result:
            return f"❌ API Error: {_json.dumps(result, indent=2)}"

        reports = result["reports"]
        count = len(reports)

        lines = [f"✅ Application '{app_link_name}' has **{count}** report(s):\n"]
        for i, report in enumerate(reports, 1):
            name = report.get("display_name", report.get("component_name", "Unknown"))
            link = report.get("link_name", "")
            report_type = report.get("type", "")
            lines.append(f"  {i}. **{name}** (link: {link}, type: {report_type})")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error listing reports: {str(e)}"


@mcp.tool()
async def zoho_get_records(
    app_link_name: str,
    report_link_name: str,
    criteria: str = "",
    max_records: int = 20,
) -> str:
    """Fetch records from a Zoho Creator report/form.
    
    Args:
        app_link_name: The link name of the application
        report_link_name: The link name of the report to fetch records from
        criteria: Optional Zoho criteria string to filter records 
                  (e.g., 'Status == \"Active\"')
        max_records: Maximum number of records to return (default: 20, max: 200)
    """
    try:
        params = {
            "limit": min(max_records, 200),
        }
        if criteria:
            params["criteria"] = criteria

        result = await _zoho_api_get_async(
            f"applications/{app_link_name}/reports/{report_link_name}",
            params=params,
        )

        if "data" not in result:
            return f"❌ API Error: {_json.dumps(result, indent=2)}"

        records = result["data"]
        count = len(records)

        lines = [f"✅ Found **{count}** record(s) in '{report_link_name}':\n"]

        for i, record in enumerate(records, 1):
            lines.append(f"  Record {i}:")
            for key, value in record.items():
                if key.startswith("ID") or key == "ID":
                    continue
                lines.append(f"    {key}: {value}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Error fetching records: {str(e)}"


# ─── Run Server ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")

