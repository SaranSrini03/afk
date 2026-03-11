"""
WhatsApp Web automation via Selenium: QR login and real-time message reading.
"""

import os
import random
import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


WA_URL = "https://web.whatsapp.com"
QR_TIMEOUT = 120
PAGE_LOAD_TIMEOUT = 30
POLL_INTERVAL = 3
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wa-chrome-profile")
OLLAMA_MODEL = "gemma3:1b"
AUTO_REPLY = True
TEST_MODE = True


def create_driver() -> webdriver.Chrome:
    """Build Chrome driver with options suitable for WhatsApp Web."""
    opts = Options()
    opts.add_argument("--user-data-dir=" + PROFILE_DIR)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=opts)


def wait_for_qr_scan(driver: webdriver.Chrome, timeout: int = QR_TIMEOUT) -> bool:
    """Block until user scans QR. Returns True when main app loads."""
    selectors = [
        "[data-testid='chat-list']",
        "[data-testid='default-user']",
        "div[role='grid']",
    ]
    for sel in selectors:
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            return True
        except Exception:
            continue
    return False


def get_recent_messages(driver: webdriver.Chrome, limit: int = 30) -> list[dict]:
    """
    Read recent messages from the open chat.
    Tries multiple selector strategies since WhatsApp Web DOM changes frequently.
    """
    messages = []
    text_selectors = [
        "span.selectable-text",
        "span.copyable-text",
        "span[data-lexical-text='true']",
        "span.copyable-text.selectable-text",
        "span[dir='ltr']",
    ]

    text_spans = []
    try:
        for sel in text_selectors:
            text_spans = driver.find_elements(By.CSS_SELECTOR, sel)
            if text_spans:
                break
        if not text_spans:
            text_spans = driver.find_elements(By.XPATH, "//span[contains(@class, 'selectable-text') or contains(@class, 'copyable-text')]")
    except Exception:
        pass

    if not text_spans:
        return messages

    seen = set()
    skip_texts = {"type a message", "search", "search or start new chat", ""}
    for span in text_spans[-limit * 2:]:
        try:
            text = (span.text or "").strip()
            if not text or text.lower() in skip_texts or text in seen:
                continue
            seen.add(text)
            meta = ""
            parent = span
            for _ in range(8):
                try:
                    parent = parent.find_element(By.XPATH, "..")
                    meta_el = parent.find_element(By.CSS_SELECTOR, "span[data-testid='msg-meta'], span[data-pre-plain-text]")
                    meta = meta_el.get_attribute("data-pre-plain-text") or meta_el.text or ""
                    meta = (meta or "").strip()
                    if meta:
                        break
                except Exception:
                    continue
            messages.append({"text": text, "meta": meta or "(no meta)"})
            if len(messages) >= limit:
                break
        except Exception:
            continue
    return messages[-limit:]


def _msg_key(m: dict) -> tuple:
    return (m.get("text", ""), m.get("meta", ""))


def _is_from_me(meta: str) -> bool:
    """Return True if message was sent by us."""
    return "you" in (meta or "").lower()


def ollama_reply(incoming: str) -> str:
    """Generate a short chat reply via local Ollama."""
    try:
        import ollama
        prompt = f"Reply briefly and naturally to this message in 1-2 sentences:\n{incoming}"
        out = ollama.generate(model=OLLAMA_MODEL, prompt=prompt, stream=False)
        reply = (out.get("response") or "").strip()
        if "\n" in reply:
            reply = reply.split("\n")[0]
        return reply[:500]
    except Exception as e:
        print(f"[OLLAMA ERR] {e}")
        return ""


def send_whatsapp_message(driver: webdriver.Chrome, text: str) -> bool:
    """Type text into chat input and send. Returns True if sent."""
    selectors = [
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true'][data-tab='1']",
        "footer div[contenteditable='true']",
        "div[contenteditable='true']",
    ]
    inp = None
    for sel in selectors:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    inp = el
                    break
            if inp:
                break
        except Exception:
            continue
    if not inp:
        return False
    for attempt in range(3):
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", inp)
            time.sleep(0.1)
            ActionChains(driver).move_to_element(inp).click().perform()
            time.sleep(0.3)
            for char in text:
                ActionChains(driver).send_keys(char).perform()
                time.sleep(random.uniform(0.03, 0.1))
            time.sleep(0.2)
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run() -> None:
    print("[1/5] Starting browser (Chrome)...")
    driver = create_driver()
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    print("[1/5] Browser ready.")
    seen: set[tuple] = set()
    stop = threading.Event()
    poll_thread: threading.Thread | None = None

    sent_texts: list[str] = []

    def _is_our_reply(t: str) -> bool:
        t = (t or "").strip()
        if not t:
            return False
        for s in sent_texts:
            if t == s or (len(t) > 5 and len(s) > 5 and (t in s or s in t)):
                return True
        return False

    def poll_messages() -> None:
        nonlocal seen, sent_texts
        while not stop.is_set():
            try:
                msgs = get_recent_messages(driver, limit=50)
                for m in msgs:
                    k = _msg_key(m)
                    if k not in seen:
                        seen.add(k)
                        txt = m["text"] or m["meta"] or ""
                        meta = m.get("meta", "")
                        snippet = txt[:80] + ("..." if len(txt) > 80 else "")
                        print(f"[NEW] {meta}: {snippet}")
                        from_me = _is_from_me(meta)
                        if _is_our_reply(txt):
                            continue
                        should_reply = AUTO_REPLY and txt
                        if not TEST_MODE:
                            should_reply = should_reply and not from_me
                        if should_reply:
                            print("[OLLAMA] Generating reply...")
                            reply = ollama_reply(txt)
                            if reply:
                                sent_texts = (sent_texts + [reply.strip()])[-5:]
                                print("[SEND] Typing into chat...")
                                if send_whatsapp_message(driver, reply):
                                    snip = reply[:60] + ("..." if len(reply) > 60 else "")
                                    print(f"[REPLIED] {snip}")
                                else:
                                    print("[REPLY FAIL] Could not type into chat input.")
                            else:
                                print("[REPLY SKIP] Ollama returned empty. Is Ollama running?")
            except Exception:
                pass
            stop.wait(timeout=POLL_INTERVAL)

    try:
        print("[2/5] Loading WhatsApp Web...")
        driver.get(WA_URL)
        print("[2/5] Waiting for chat list (scan QR if first time)...")
        if not wait_for_qr_scan(driver):
            print("[FAIL] QR scan timeout or not detected.")
            return
        print("[3/5] Logged in. Finding chat list...")
        time.sleep(2)
        try:
            chat_list = driver.find_element(By.CSS_SELECTOR, "[data-testid='chat-list']")
            print("[3/5] Clicking first chat...")
            first_chat = chat_list.find_element(By.CSS_SELECTOR, "[data-testid='cell-frame-container']")
            first_chat.click()
            print("[3/5] Chat opened.")
        except Exception:
            print("[3/5] Open a chat manually in the left panel.")
        time.sleep(2)
        print("[4/5] Reading messages from chat...")
        initial = get_recent_messages(driver, limit=10)
        for m in initial:
            seen.add(_msg_key(m))
        tm = " TEST MODE (reply to self)" if TEST_MODE else ""
        ar_status = f"Auto-reply ON (Ollama {OLLAMA_MODEL}){tm}" if AUTO_REPLY else "Auto-reply OFF"
        print(f"[5/5] Latest {len(initial)} messages. Listening (every {POLL_INTERVAL}s). {ar_status}. Press Enter to exit.")
        if initial:
            for i, m in enumerate(initial, 1):
                txt = m["text"] or m["meta"] or ""
                snippet = txt[:80] + ("..." if len(txt) > 80 else "")
                print(f"  {i}. {m['meta']}: {snippet}")
        else:
            print("  (none yet)")
        poll_thread = threading.Thread(target=poll_messages)
        poll_thread.start()
        input()
    finally:
        stop.set()
        if poll_thread is not None:
            poll_thread.join(timeout=2)
        driver.quit()


if __name__ == "__main__":
    run()
