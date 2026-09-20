import os
import sys
import time
import re
import random
import base64
import subprocess
import io
import socket
import urllib.request
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

def is_port_in_use(port: int) -> bool:
    """Checks if a TCP port (CDP debugging port) is currently listening on localhost."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            return s.connect_ex(('127.0.0.1', int(port))) == 0
    except Exception:
        return False

def parse_prompt_metadata(prompt_text, default_idx=1):
    """
    Extracts prompt number, duration, and clean prompt text.
    Handles formats like:
      - '(01-0:4) Prompt text'
      - '01-0:4 Prompt text'
      - '1) 0:4 Prompt text'
      - '1. (0:04) Prompt text'
      - 'Prompt text (0:4)'
    Returns:
      (num: int, dur: str, clean_prompt: str, filename_base: str)
      where filename_base is e.g. '01-0.4' or '01-0-4' with NO other text.
    """
    raw = prompt_text.strip()
    
    # Check 1: Starts with (01-0:4) or 01-0:4 or [01-0:4]
    m = re.match(r'^[\[\(]?\s*(\d+)\s*[-_]\s*([0-9]+[:\-_.]?[0-9]*s?)[\]\)]?\s*[:\-\)]?\s*(.*)', raw, re.DOTALL)
    if m and (':' in m.group(2) or '.' in m.group(2) or '-' in m.group(2) or len(m.group(2)) > 0):
        num = int(m.group(1))
        dur = m.group(2).strip().replace(':', '.')
        clean_prompt = m.group(3).strip()
        filename_base = f"{num:02d}-{dur}" if dur else f"{num:02d}"
        return num, dur, clean_prompt, filename_base

    # Check 2: Starts with numbering like 1) or 1. or Scene 1:
    m_num = re.match(r'^(?:Prompt\s*|Scene\s*)?(\d+)[\)\.\:\-_]\s*(.*)', raw, re.IGNORECASE | re.DOTALL)
    clean_prompt = raw
    num = default_idx
    if m_num:
        num = int(m_num.group(1))
        clean_prompt = m_num.group(2).strip()

    # Check 3: Extract duration anywhere in prompt (e.g. (0:4), [0:4], 0:4, 0:04, 0-4, 0.4s)
    m_dur = re.search(r'[\[\(]?\b(\d+[:\.]\d+s?)\b[\]\)]?', clean_prompt)
    dur = ''
    if m_dur:
        dur = m_dur.group(1).strip().replace(':', '.')
        clean_prompt = clean_prompt[:m_dur.start()] + clean_prompt[m_dur.end():]
        clean_prompt = re.sub(r'\s+', ' ', clean_prompt).strip(' -:,()[]')
    else:
        m_range = re.search(r'\b\d+[:\.]\d+\s*[-_]\s*(\d+[:\.]\d+)\b', clean_prompt)
        if m_range:
            dur = m_range.group(1).strip().replace(':', '.')
            clean_prompt = clean_prompt[:m_range.start()] + clean_prompt[m_range.end():]
            clean_prompt = re.sub(r'\s+', ' ', clean_prompt).strip(' -:,()[]')

    filename_base = f"{num:02d}-{dur}" if dur else f"{num:02d}"
    return num, dur, clean_prompt, filename_base


def is_valid_generated_image(data: bytes) -> bool:
    """
    Validates that captured image data is an actual full-color generated image,
    and NOT Google Flow's 1000x1000 grayscale loading noise / shimmer texture.
    """
    if not data or len(data) < 30000:
        return False
    # Exactly 57725 bytes is the known Google Flow placeholder noise texture
    if len(data) == 57725:
        return False
    try:
        im = Image.open(io.BytesIO(data))
        # The loading skeleton is single-channel grayscale (Mode 'L')
        if im.mode == "L":
            return False
        # Valid AI generated images are RGB or RGBA
        if im.mode not in ("RGB", "RGBA"):
            return False
        w, h = im.size
        if w < 400 or h < 400:
            return False
        return True
    except Exception:
        return False

def find_chrome_path():
    """Locates Google Chrome or Edge executable on Windows."""
    paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "chrome"

class GoogleFlowBot:
    def __init__(self, profile_dir, output_dir, profile_id=1, cdp_port=9222, profile_label="", log_callback=None, progress_callback=None):
        self.profile_id = profile_id
        self.profile_label = profile_label
        self.cdp_port = cdp_port
        self.profile_dir = Path(profile_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_callback = log_callback or print
        self.progress_callback = progress_callback or (lambda cur, total: None)
        self.is_running = False
        self.is_paused = False
        self.chrome_process = None

    def log(self, message):
        if self.log_callback:
            prefix = f"[Profile {self.profile_id}] " if getattr(self, 'profile_id', None) else ""
            self.log_callback(f"{prefix}{message}")

    def is_chrome_running(self) -> bool:
        """Returns True if the remote debugging port for this profile is active."""
        return is_port_in_use(self.cdp_port)

    def launch_browser(self, target_url="https://flow.google.com"):
        """Launches standard Chrome with real user profile and assigned CDP port."""
        chrome_exe = find_chrome_path()
        label_text = f" ({self.profile_label})" if self.profile_label else ""
        self.log(f"🌐 Launching Chrome for Profile {self.profile_id}{label_text} on port {self.cdp_port}...")
        self.log(f"📁 Profile folder: {self.profile_dir.name}")
        
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={str(self.profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized",
            target_url
        ]
        
        try:
            self.chrome_process = subprocess.Popen(cmd)
            self.log(f"✅ Chrome launched safely on port {self.cdp_port}!")
            self.log("👉 Open your Google Flow Project in this browser window.")
        except Exception as e:
            self.log(f"❌ Failed to launch Chrome: {e}")

    def sanitize_filename(self, text, max_len=40):
        clean = re.sub(r'[^a-zA-Z0-9_\- ]', '', text)
        clean = clean.strip().replace(' ', '_')
        return clean[:max_len] if clean else "image"

    def find_best_project_tab(self, browser, target_url="https://flow.google.com"):
        """Finds the open Google Flow project tab without reloading, or navigates."""
        if not browser.contexts:
            return None
        for context in browser.contexts:
            for page in context.pages:
                url = page.url
                if "flow.google.com/p/" in url or "flow.google.com/project" in url:
                    return page
            for page in context.pages:
                if "flow.google" in page.url or "labs.google" in page.url:
                    return page
        page = browser.contexts[0].pages[0] if browser.contexts[0].pages else browser.contexts[0].new_page()
        if "flow.google" not in page.url and "labs.google" not in page.url:
            try:
                page.goto(target_url)
            except Exception:
                pass
        return page

    def human_type(self, page, text):
        """Types text with natural human speed."""
        for char in text:
            page.keyboard.type(char, delay=random.randint(10, 25))

    def run_batch(self, prompts, target_url="https://flow.google.com", delay_seconds=5, timeout_per_image=60, character_tag=""):
        """
        Fast direct-download batch automation:
        - Intercepts full-resolution image responses over the network instantly.
        - No full-window screenshots.
        - Moves to next prompt immediately when image is saved.
        """
        self.is_running = True
        self.is_paused = False
        total = len(prompts)
        label_text = f" ({self.profile_label})" if self.profile_label else ""
        self.log(f"🚀 Starting automation for Profile {self.profile_id}{label_text} [{total} prompts]...")

        with sync_playwright() as p:
            browser = None
            try:
                self.log(f"🔗 Connecting strictly to Chrome on port {self.cdp_port}...")
                browser = p.chromium.connect_over_cdp(f"http://localhost:{self.cdp_port}")
            except Exception:
                self.log(f"⚠️ Chrome not detected on port {self.cdp_port}. Launching Chrome...")
                self.launch_browser(target_url)
                time.sleep(4)
                try:
                    browser = p.chromium.connect_over_cdp(f"http://localhost:{self.cdp_port}")
                except Exception as e:
                    self.log(f"❌ Could not connect: {e}")
                    self.log("👉 Click 'Launch Chrome' button, open your project, then click Start Batch.")
                    self.is_running = False
                    return

            page = self.find_best_project_tab(browser, target_url)
            if not page:
                self.log("❌ Could not find or create a browser page.")
                self.is_running = False
                return

            self.log(f"🎯 Attached to Project Tab: {page.url}")

            # Set up network response sniffer to catch generated images in real time
            captured_images = []

            def on_response(response):
                try:
                    ct = response.headers.get("content-type", "")
                    url = response.url.lower()
                    # Filter for actual generated image streams
                    if "image" in ct or "octet-stream" in ct:
                        # Exclude UI assets, avatars, icons, noises, placeholders
                        excluded = ["avatar", "icon", "favicon", "noise", "skeleton", "placeholder", "shimmer", "loader", "logo"]
                        if any(x in url for x in excluded):
                            return
                        try:
                            body = response.body()
                            if is_valid_generated_image(body):
                                captured_images.append(body)
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", on_response)

            for idx, prompt in enumerate(prompts, start=1):
                if not self.is_running:
                    self.log("⏹ Automation stopped by user.")
                    break

                while self.is_paused:
                    time.sleep(1)
                    if not self.is_running:
                        break

                p_num, p_dur, clean_prompt, file_base = parse_prompt_metadata(prompt, idx)
                file_name = f"{file_base}.png"

                self.progress_callback(idx, total)
                preview = clean_prompt.replace('\n', ' ')[:75]
                self.log(f"\n==========================================")
                self.log(f"🎬 Shot [{idx}/{total}] [{file_name}]: \"{preview}...\"")
                self.log(f"==========================================")

                try:
                    # Clear previous network captured queue
                    captured_images.clear()

                    # Record existing images in DOM to prevent downloading previous shots
                    existing_img_srcs = set()
                    try:
                        for el in page.query_selector_all("img, div[style*='background-image']"):
                            s = el.get_attribute("src") or ""
                            if not s and "background-image" in (el.get_attribute("style") or ""):
                                m = re.search(r'url\(["\']?(.*?)["\']?\)', el.get_attribute("style") or "")
                                if m:
                                    s = m.group(1)
                            if s:
                                existing_img_srcs.add(s)
                    except Exception:
                        pass

                    # 1. Close any accidental modals
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    time.sleep(0.2)

                    # 2. Formulate Prompt
                    final_prompt = clean_prompt if clean_prompt else prompt.strip()
                    if character_tag and character_tag.strip():
                        if character_tag not in final_prompt:
                            final_prompt = f"{character_tag.strip()} {final_prompt}"

                    # 3. Locate prompt input box
                    selectors = [
                        '[placeholder*="What do you want to create" i]',
                        '[placeholder*="create" i]',
                        'textarea[placeholder*="Ask" i]',
                        'textarea[placeholder*="Prompt" i]',
                        'div[contenteditable="true"]',
                        'textarea',
                        'div[role="textbox"]'
                    ]

                    input_elem = None
                    for sel in selectors:
                        elements = page.query_selector_all(sel)
                        for elem in reversed(elements):
                            if elem.is_visible():
                                input_elem = elem
                                break
                        if input_elem:
                            break

                    injected = False
                    if input_elem:
                        try:
                            input_elem.click(timeout=1000)
                        except Exception:
                            pass

                        # DOM-level injection: zero focus fighting across windows!
                        try:
                            js_inject = """
                            (el, text) => {
                                el.focus();
                                if (el.isContentEditable) {
                                    el.innerText = text;
                                } else {
                                    el.value = text;
                                }
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                            """
                            input_elem.evaluate(js_inject, final_prompt)
                            injected = True
                        except Exception:
                            pass

                        if not injected:
                            try:
                                input_elem.fill(final_prompt)
                                injected = True
                            except Exception:
                                pass

                        if not injected:
                            try:
                                input_elem.press_sequentially(final_prompt, delay=15)
                                injected = True
                            except Exception:
                                pass

                    if not injected:
                        try:
                            page.keyboard.press("Control+A")
                            page.keyboard.press("Backspace")
                        except Exception:
                            pass
                        self.human_type(page, final_prompt)

                    time.sleep(0.4)
                    if input_elem:
                        try:
                            input_elem.press("Enter")
                        except Exception:
                            page.keyboard.press("Enter")
                    else:
                        page.keyboard.press("Enter")
                    self.log("✅ Prompt submitted! Generating image...")

                    # Click send button as fallback
                    send_btn_selectors = [
                        'div:has([placeholder*="create" i]) button',
                        'button[aria-label*="Send" i]',
                        'button[aria-label*="Generate" i]',
                        'button[aria-label*="Submit" i]',
                        'button[type="submit"]'
                    ]
                    for btn_sel in send_btn_selectors:
                        btns = page.query_selector_all(btn_sel)
                        for btn in reversed(btns):
                            if btn and btn.is_visible() and btn.is_enabled():
                                try:
                                    btn.click(timeout=1000)
                                    break
                                except Exception:
                                    pass

                    # 4. FAST DETECTION & DIRECT DOWNLOAD
                    profile_out_dir = self.output_dir / f"Profile_{self.profile_id}" if f"Profile_{self.profile_id}" not in str(self.output_dir) else self.output_dir
                    profile_out_dir.mkdir(parents=True, exist_ok=True)
                    save_path = profile_out_dir / file_name

                    img_saved = False
                    start_time = time.time()
                    time.sleep(5) # Initial wait for Google Flow to start generation

                    last_log_time = 0
                    while time.time() - start_time < timeout_per_image:
                        if not self.is_running:
                            break

                        elapsed = int(time.time() - start_time)
                        if elapsed - last_log_time >= 10:
                            self.log(f"⏳ Generating image... ({elapsed}s / {timeout_per_image}s)")
                            last_log_time = elapsed

                        # Check 1: Real-time network response interceptor (Instant lossless download!)
                        if captured_images:
                            latest_bytes = captured_images[-1]
                            if is_valid_generated_image(latest_bytes):
                                with open(save_path, "wb") as f:
                                    f.write(latest_bytes)
                                size_kb = os.path.getsize(save_path) // 1024
                                self.log(f"⚡ ✅ DIRECT DOWNLOAD COMPLETE: {file_name} ({size_kb} KB)")
                                img_saved = True
                                break

                        # Check 2: DOM image elements / high-res canvas
                        try:
                            # Look for media card image elements in Google Flow
                            img_elements = page.query_selector_all("img, div[style*='background-image']")
                            for el in reversed(img_elements):
                                src = el.get_attribute("src") or ""
                                if not src and "background-image" in (el.get_attribute("style") or ""):
                                    style = el.get_attribute("style")
                                    m = re.search(r'url\(["\']?(.*?)["\']?\)', style)
                                    if m:
                                        src = m.group(1)

                                # Ignore images that were already on page before this prompt
                                if not src or src in existing_img_srcs:
                                    continue

                                if "googleusercontent" in src or "blob:" in src or "labs" in src or "data:image" in src:
                                    box = el.bounding_box()
                                    if box and box["width"] > 200 and box["height"] > 200:
                                        data = None
                                        if src.startswith("data:image"):
                                            _, enc = src.split(",", 1)
                                            data = base64.b64decode(enc)
                                        elif src.startswith("http"):
                                            # Download direct URL
                                            req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0'})
                                            with urllib.request.urlopen(req, timeout=10) as resp:
                                                data = resp.read()

                                        if data and is_valid_generated_image(data):
                                            with open(save_path, "wb") as f:
                                                f.write(data)
                                            size_kb = os.path.getsize(save_path) // 1024
                                            self.log(f"💾 ✅ Downloaded from element: {file_name} ({size_kb} KB)")
                                            img_saved = True
                                            break
                        except Exception:
                            pass

                        if img_saved:
                            break

                        time.sleep(2)

                    if not img_saved:
                        self.log(f"⚠️ Direct download timed out. Saving clean card render: {file_name}")
                        # Screenshot only the specific last media card (never full window screenshot)
                        try:
                            cards = page.query_selector_all("div[class*='media'], div[class*='card'], img")
                            saved_card = False
                            for card in reversed(cards):
                                box = card.bounding_box()
                                if box and box["width"] > 250 and box["height"] > 250:
                                    card.screenshot(path=str(save_path))
                                    self.log(f"📸 Card saved: {file_name}")
                                    saved_card = True
                                    break
                            if not saved_card:
                                page.screenshot(path=str(save_path))
                        except Exception as e:
                            self.log(f"❌ Could not save: {e}")

                    # Fast human delay before next prompt
                    cooldown = delay_seconds + random.uniform(0.5, 2.0)
                    self.log(f"⏱ Cooldown {cooldown:.1f}s before next shot...")
                    time.sleep(cooldown)

                except Exception as e:
                    self.log(f"❌ Error on shot #{idx}: {e}")
                    time.sleep(2)

            self.log("\n🎉✨ ALL SHOTS COMPLETED & DOWNLOADED! Check your output folder.")
            self.progress_callback(total, total)
            self.is_running = False

    def stop(self):
        self.is_running = False
        self.log("🛑 Stopping automation...")

    def pause(self):
        self.is_paused = not self.is_paused
        status = "Paused ⏸" if self.is_paused else "Resumed ▶️"
        self.log(f"Bot {status}")

    def _submit_prompt_to_flow(self, page, prompt_text, character_tag=""):
        """Submits a single prompt into Flow via DOM injection and Enter/Send dispatch."""
        final_prompt = prompt_text.strip()
        if character_tag and character_tag.strip():
            if character_tag not in final_prompt:
                final_prompt = f"{character_tag.strip()} {final_prompt}"

        selectors = [
            '[placeholder*="What do you want to create" i]',
            '[placeholder*="create" i]',
            'textarea[placeholder*="Ask" i]',
            'textarea[placeholder*="Prompt" i]',
            'div[contenteditable="true"]',
            'textarea',
            'div[role="textbox"]'
        ]

        input_elem = None
        for sel in selectors:
            elements = page.query_selector_all(sel)
            for elem in reversed(elements):
                if elem.is_visible():
                    input_elem = elem
                    break
            if input_elem:
                break

        injected = False
        if input_elem:
            try:
                input_elem.click(timeout=1000)
            except Exception:
                pass

            try:
                js_inject = """
                (el, text) => {
                    el.focus();
                    if (el.isContentEditable) {
                        el.innerText = text;
                    } else {
                        el.value = text;
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """
                input_elem.evaluate(js_inject, final_prompt)
                injected = True
            except Exception:
                pass

            if not injected:
                try:
                    input_elem.fill(final_prompt)
                    injected = True
                except Exception:
                    pass

            if not injected:
                try:
                    input_elem.press_sequentially(final_prompt, delay=15)
                    injected = True
                except Exception:
                    pass

        if not injected:
            try:
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
            except Exception:
                pass
            self.human_type(page, final_prompt)

        time.sleep(0.4)
        if input_elem:
            try:
                input_elem.press("Enter")
            except Exception:
                page.keyboard.press("Enter")
        else:
            page.keyboard.press("Enter")

        send_btn_selectors = [
            'div:has([placeholder*="create" i]) button',
            'button[aria-label*="Send" i]',
            'button[aria-label*="Generate" i]',
            'button[aria-label*="Submit" i]',
            'button[type="submit"]'
        ]
        for btn_sel in send_btn_selectors:
            btns = page.query_selector_all(btn_sel)
            for btn in reversed(btns):
                if btn and btn.is_visible() and btn.is_enabled():
                    try:
                        btn.click(timeout=1000)
                        break
                    except Exception:
                        pass
        return True

    def run_bulk_agent_pipeline(self, prompts, target_url="https://flow.google.com", 
                                concurrency=3, queue_delay=3.0, timeout_per_image=90, 
                                character_tag="", status_callback=None):
        """
        Bulk Agent Mode Pipeline:
        - Maintains up to `concurrency` active rendering slots in Google Flow.
        - Sequentially injects prompts into Flow's queue with a safe natural delay.
        - Intercepts incoming completed images and matches them to in-flight prompts.
        - Guarantees strict filename sequence: [number]-[duration].png (e.g. 01-0.4.png).
        - Auto-replenishes queue slots as images finish until the entire batch is complete.
        """
        self.is_running = True
        self.is_paused = False

        self.log(f"\n=======================================================")
        self.log(f"🚀 [BULK AGENT MODE] Starting Fast Queue Pipeline on Profile {self.profile_id}")
        self.log(f"🎯 Total Prompts: {len(prompts)} | Concurrency Slots: {concurrency}")
        self.log(f"=======================================================")

        parsed_items = []
        for i, p in enumerate(prompts):
            num, dur, clean_prompt, filename_base = parse_prompt_metadata(p, default_idx=i + 1)
            parsed_items.append({
                "idx": i + 1,
                "num": num,
                "dur": dur,
                "prompt": clean_prompt,
                "filename_base": filename_base,
                "file_name": f"{filename_base}.png",
                "raw": p,
                "status": "PENDING"
            })

        total = len(parsed_items)
        pending_queue = list(parsed_items)
        in_flight = []
        completed = []

        if status_callback:
            status_callback(total, 0, 0, len(pending_queue))
        self.progress_callback(0, total)

        profile_out_dir = self.output_dir / f"Profile_{self.profile_id}" if f"Profile_{self.profile_id}" not in str(self.output_dir) else self.output_dir
        profile_out_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            endpoint_url = f"http://127.0.0.1:{self.cdp_port}"
            self.log(f"Connecting to Chrome on {endpoint_url}...")
            browser = None
            try:
                browser = p.chromium.connect_over_cdp(endpoint_url)
            except Exception as e:
                self.log(f"❌ Could not connect to Chrome on port {self.cdp_port}: {e}")
                self.log(f"💡 Please click '▶ Launch (P{self.profile_id})' in the side panel first!")
                self.is_running = False
                return

            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = None
            for pg in context.pages:
                if "flow.google.com" in pg.url or "imagefx" in pg.url:
                    page = pg
                    break
            if not page:
                page = context.pages[0] if context.pages else context.new_page()

            if "flow.google.com" not in page.url:
                self.log(f"Navigating to {target_url}...")
                page.goto(target_url, timeout=60000)
                page.wait_for_load_state("domcontentloaded")

            # Network image interceptor
            captured_images = []
            def handle_response(response):
                try:
                    ct = response.headers.get("content-type", "").lower()
                    url = response.url.lower()
                    if ("image/" in ct or "googleusercontent" in url or "blob:" in url) and response.status == 200:
                        body = response.body()
                        if is_valid_generated_image(body):
                            captured_images.append(body)
                except Exception:
                    pass
            page.on("response", handle_response)

            last_status_time = time.time()

            while (pending_queue or in_flight) and self.is_running:
                while self.is_paused and self.is_running:
                    time.sleep(0.5)

                if not self.is_running:
                    break

                # 1. Pipeline Feeding: Keep active in_flight slots filled up to `concurrency`
                while len(in_flight) < concurrency and pending_queue and self.is_running:
                    item = pending_queue.pop(0)
                    self.log(f"📥 [Agent Queue] Pushing Prompt #{item['num']} ({item['file_name']}) into Flow...")
                    try:
                        self._submit_prompt_to_flow(page, item['prompt'], character_tag)
                        item['submitted_at'] = time.time()
                        item['status'] = 'IN_FLIGHT'
                        in_flight.append(item)
                        if status_callback:
                            status_callback(total, len(in_flight), len(completed), len(pending_queue))
                    except Exception as e:
                        self.log(f"⚠️ Error submitting prompt #{item['num']}: {e}")
                        item['status'] = 'ERROR'
                        completed.append(item)
                    
                    # Safe spacing between submissions so Flow does not drop them
                    time.sleep(queue_delay)

                # 2. Check for newly captured images
                if captured_images and in_flight:
                    # An image has arrived from Flow!
                    img_bytes = captured_images.pop(0)
                    # Assign to the earliest in_flight prompt (FIFO matching)
                    item = in_flight.pop(0)
                    save_path = profile_out_dir / item['file_name']
                    try:
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        size_kb = os.path.getsize(save_path) // 1024
                        self.log(f"⚡ ✅ [Agent Saved #{item['num']}] -> {item['file_name']} ({size_kb} KB) | Active: {len(in_flight)} | Left: {len(pending_queue)}")
                        item['status'] = 'COMPLETED'
                        completed.append(item)
                        self.progress_callback(len(completed), total)
                        if status_callback:
                            status_callback(total, len(in_flight), len(completed), len(pending_queue))
                    except Exception as e:
                        self.log(f"❌ Error writing file {item['file_name']}: {e}")

                # 3. Check for in-flight timeouts (if image takes too long, fallback to DOM search)
                now = time.time()
                for item in list(in_flight):
                    elapsed = now - item.get('submitted_at', now)
                    if elapsed > timeout_per_image:
                        self.log(f"⏳ Prompt #{item['num']} timed out ({int(elapsed)}s). Attempting DOM capture fallback...")
                        save_path = profile_out_dir / item['file_name']
                        try:
                            cards = page.query_selector_all("div:has(img), [role='article'], div[class*='card' i]")
                            saved = False
                            for c in reversed(cards):
                                box = c.bounding_box()
                                if box and box["width"] > 250 and box["height"] > 250:
                                    c.screenshot(path=str(save_path))
                                    self.log(f"📸 Saved fallback screenshot: {item['file_name']}")
                                    saved = True
                                    break
                            if not saved:
                                page.screenshot(path=str(save_path))
                        except Exception as e:
                            self.log(f"Could not fallback capture: {e}")
                        
                        in_flight.remove(item)
                        item['status'] = 'TIMEOUT'
                        completed.append(item)
                        self.progress_callback(len(completed), total)
                        if status_callback:
                            status_callback(total, len(in_flight), len(completed), len(pending_queue))

                # Periodic status log
                if time.time() - last_status_time >= 15 and in_flight:
                    self.log(f"📊 [Agent Status] Active in Flow: {len(in_flight)} | Completed: {len(completed)}/{total} | In Queue: {len(pending_queue)}")
                    last_status_time = time.time()

                time.sleep(0.8)

            self.log(f"\n🎉✨ [BULK AGENT FINISHED] All {len(completed)} prompts processed! Check: {profile_out_dir}")
            self.progress_callback(total, total)
            self.is_running = False
            if status_callback:
                status_callback(total, 0, len(completed), 0)
