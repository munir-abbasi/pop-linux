import json
import os
import stat

from pop_linux.config import COOKIES_FILE, DEFAULT_USER_AGENT, ensure_config_dir


def load_cookies() -> dict[str, str]:
    """Loads saved Google Scholar cookies from ~/.config/pop_linux/cookies.json."""
    ensure_config_dir()
    if not COOKIES_FILE.exists():
        return {}
    try:
        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cookies(cookies: dict[str, str]) -> None:
    """Saves cookie key-value dict to ~/.config/pop_linux/cookies.json with restricted 0600 permissions."""
    ensure_config_dir()
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    try:
        os.chmod(COOKIES_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Best-effort hardening; not fatal if the filesystem rejects it.


async def solve_google_scholar_captcha(target_url: str = "https://scholar.google.com") -> dict[str, str]:
    """
    Launches a headful Chromium window via Playwright to let the user solve a Google Scholar CAPTCHA.
    Captures updated cookies after successful navigation and saves them to cookies.json.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError("Playwright is not installed. Please run 'playwright install chromium' to enable CAPTCHA solving.")

    print("\n[!] Google Scholar CAPTCHA / Rate-Limit detected.")
    print("[!] Launching Chromium browser window. Please solve the CAPTCHA challenge in the window...")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception as e:
            # Fallback for headless environments or display missing
            raise RuntimeError(f"Could not launch headful Chromium browser for CAPTCHA solve: {e}")

        context = await browser.new_context(user_agent=DEFAULT_USER_AGENT)
        page = await context.new_page()

        # Load existing cookies if any
        existing = load_cookies()
        if existing:
            cookie_objects = [
                {"name": k, "value": v, "domain": ".scholar.google.com", "path": "/"}
                for k, v in existing.items()
            ]
            try:
                await context.add_cookies(cookie_objects)  # type: ignore[arg-type]
            except Exception:
                pass  # Invalid/stale cookies are harmless; they are simply not replayed.

        try:
            await page.goto(target_url, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[!] Initial navigation warning: {e}")

        # Wait up to 120 seconds for user to solve CAPTCHA and land on Scholar results/main page
        print("[!] Waiting for user to solve CAPTCHA (timeout 120s)...")
        for _ in range(60):
            try:
                content = await page.content()
                url = page.url
                if "sorry/index" not in url and "recaptcha" not in content.lower() and "scholar.google.com" in url:
                    print("[+] CAPTCHA challenge passed successfully!")
                    break
                await page.wait_for_timeout(2000)
            except Exception:
                # Browser or target page closed by user
                print("[!] Browser or tab closed by user.")
                break

        # Extract context cookies safely
        extracted_cookies = {}
        try:
            cookies_list = await context.cookies("https://scholar.google.com")
            extracted_cookies = {c["name"]: c["value"] for c in cookies_list}
            await browser.close()
        except Exception:
            pass  # Cookie extraction is best-effort; load_cookies() is the fallback.

        if extracted_cookies:
            save_cookies(extracted_cookies)
            return extracted_cookies
        return load_cookies()

