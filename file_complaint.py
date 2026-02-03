#!/usr/bin/env python3
"""
FCC Complaint Filer - Laptop Client

This script runs on your laptop, fetches speed test data from your Pi,
and opens a browser to file the complaint. You solve the Cloudflare captcha
manually, and the script handles the rest.

Setup:
    pip install playwright playwright-stealth
    playwright install chromium

Usage:
    python file_complaint.py                    # Uses defaults
    python file_complaint.py --pi-host pihole   # Custom Pi hostname
    python file_complaint.py --dry-run          # Preview only

Schedule with cron (Mac/Linux) or Task Scheduler (Windows) to run at 9am daily.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import mean

# Configuration - edit these for your setup
DEFAULT_PI_HOST = "dietpi"  # SSH hostname for your Pi
DEFAULT_PI_USER = "dietpi"  # SSH username
DEFAULT_PI_PATH = "/home/dietpi/ISPFCCComplainer"  # Path on Pi


def fetch_data_from_pi(host: str, user: str, pi_path: str, date: str | None = None) -> dict:
    """SSH to Pi and fetch speed test data as JSON."""
    cmd = f"cd {pi_path} && ./venv/bin/python -m src.export_daily_data"
    if date:
        cmd += f" --date {date}"

    ssh_cmd = ["ssh", f"{user}@{host}", cmd]

    print(f"Fetching data from {user}@{host}...")
    result = subprocess.run(ssh_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"SSH failed: {result.stderr}")

    return json.loads(result.stdout)


def generate_complaint_text(data: dict) -> str:
    """Generate complaint text from Pi data."""
    config = data["config"]
    tests = data["tests"]
    report_date = data["date"]

    if not tests:
        return None

    downloads = [t["download_mbps"] for t in tests]
    uploads = [t["upload_mbps"] for t in tests]
    pings = [t["ping_ms"] for t in tests]

    avg_download = mean(downloads)
    min_download = min(downloads)
    max_download = max(downloads)
    avg_upload = mean(uploads)
    avg_ping = mean(pings)

    threshold = config["threshold_speed_mbps"]
    failed_tests = [t for t in tests if t["download_mbps"] < threshold]
    failed_count = len(failed_tests)
    total_count = len(tests)
    failure_rate = (failed_count / total_count) * 100 if total_count > 0 else 0
    avg_percent = (avg_download / config["advertised_speed_mbps"]) * 100

    # Build compact test summary (only show failed tests to save space)
    failed_samples = failed_tests[:10]  # Show up to 10 worst examples
    test_samples = []
    for t in sorted(failed_samples, key=lambda x: x["download_mbps"]):
        ts = datetime.fromisoformat(t["timestamp"])
        percent = (t["download_mbps"] / config["advertised_speed_mbps"]) * 100
        test_samples.append(f"{ts.strftime('%H:%M')} - {t['download_mbps']:.0f} Mbps ({percent:.0f}%)")

    sample_list = ", ".join(test_samples) if test_samples else "N/A"

    return f"""Complaint: Inadequate internet service from {config['isp_name']}.

ACCOUNT: {config['isp_account_number']}
ADDRESS: {config['service_address']}
ADVERTISED: {config['advertised_speed_mbps']} Mbps | THRESHOLD ({config['threshold_percent']}%): {threshold:.0f} Mbps

SUMMARY FOR {report_date}:
- Tests: {total_count} | Failed: {failed_count} ({failure_rate:.0f}%)
- Avg Download: {avg_download:.0f} Mbps ({avg_percent:.0f}% of advertised)
- Min/Max: {min_download:.0f} / {max_download:.0f} Mbps
- Avg Upload: {avg_upload:.0f} Mbps | Avg Ping: {avg_ping:.0f} ms

WORST RESULTS: {sample_list}

On {report_date}, {failed_count} of {total_count} speed tests ({failure_rate:.0f}%) fell below {config['threshold_percent']}% of my advertised {config['advertised_speed_mbps']} Mbps service. Average speed was {avg_download:.0f} Mbps ({avg_percent:.0f}% of paid rate).

I request the FCC investigate this underperformance and require {config['isp_name']} to deliver advertised speeds or adjust billing accordingly.

[Automated complaint from verified speed test data]"""


def file_complaint_with_browser(data: dict, complaint_text: str, dry_run: bool = False, auto_submit: bool = False) -> bool:
    """Open browser and file complaint. User solves captcha manually."""
    from playwright.sync_api import sync_playwright

    config = data["config"]

    if dry_run:
        print("\n" + "=" * 60)
        print("DRY RUN - Would file complaint with this text:")
        print("=" * 60)
        print(complaint_text)
        print("=" * 60 + "\n")
        return True

    # Use persistent context for session storage
    state_path = Path.home() / ".fcc_complaint_session"
    state_path.mkdir(exist_ok=True)

    with sync_playwright() as p:
        print("Opening browser (Microsoft Edge)...")
        context = p.chromium.launch_persistent_context(
            str(state_path),
            headless=False,  # Visible browser for captcha solving
            channel="msedge",  # Use system Microsoft Edge
        )

        # Try to apply stealth if available
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.apply_stealth_sync(context)
        except ImportError:
            print("Note: playwright-stealth not installed, continuing without stealth")

        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(120000)  # 2 minute timeout

        try:
            def wait_for_cloudflare(page, timeout_mins=5):
                """Wait for Cloudflare challenge to be solved."""
                if "moment" in page.title().lower() or "just a moment" in page.content().lower():
                    print("\n" + "=" * 60)
                    print("CLOUDFLARE CAPTCHA DETECTED")
                    print("Please solve the captcha in the browser window!")
                    print("=" * 60 + "\n")
                    for i in range(timeout_mins * 12):
                        time.sleep(5)
                        if "moment" not in page.title().lower():
                            print("Cloudflare passed!")
                            time.sleep(2)
                            return True
                        if i % 6 == 0 and i > 0:
                            print(f"Still waiting for captcha... ({i*5}s)")
                    raise RuntimeError("Cloudflare not solved in time")
                return False

            # Try going directly to complaint form first (may already be logged in)
            print("Navigating to complaint form...")
            page.goto("https://consumercomplaints.fcc.gov/hc/en-us/requests/new?ticket_form_id=38824")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            wait_for_cloudflare(page)

            # Check if redirected to login
            if "signin" in page.url.lower():
                print("Not logged in, redirecting to login...")
                time.sleep(2)
                wait_for_cloudflare(page)

                print("Logging in...")
                # Try multiple selectors for email field
                email_filled = False
                for selector in ['[data-testid="email-input"]', 'input[type="email"]', 'input[name="email"]', '#user_email']:
                    try:
                        if page.locator(selector).is_visible(timeout=2000):
                            page.fill(selector, config["fcc_username"])
                            email_filled = True
                            break
                    except:
                        continue

                if not email_filled:
                    raise RuntimeError("Could not find email input field")

                page.fill('input[type="password"]', config["fcc_password"])
                page.click('button[type="submit"], input[type="submit"]')
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                wait_for_cloudflare(page)

                # Verify login - check if still on signin or redirected
                if "signin" in page.url.lower() and "requests/new" not in page.url.lower():
                    raise RuntimeError("Login failed - check credentials")
                print("Login successful!")

                # Navigate back to complaint form
                print("Navigating to complaint form...")
                page.goto("https://consumercomplaints.fcc.gov/hc/en-us/requests/new?ticket_form_id=38824")
                page.wait_for_load_state("domcontentloaded")
                time.sleep(3)
                wait_for_cloudflare(page)
            else:
                print("Already logged in from previous session")

            # Parse address (format: "123 Main St, City, ST 12345")
            def parse_address(addr):
                parts = addr.split(',')
                if len(parts) >= 2:
                    street = parts[0].strip()
                    city_state_zip = parts[-1].strip()
                    city = parts[1].strip() if len(parts) > 2 else ""
                    # Parse "ST 12345" or "State 12345"
                    csz_parts = city_state_zip.split()
                    if len(csz_parts) >= 2:
                        zip_code = csz_parts[-1]
                        state = csz_parts[-2] if len(csz_parts) >= 2 else ""
                        if not city:
                            city = ' '.join(csz_parts[:-2])
                    else:
                        state = ""
                        zip_code = city_state_zip
                    return street, city, state, zip_code
                return addr, "", "", ""

            street, city, state, zip_code = parse_address(config["service_address"])

            # Format phone number
            phone = config["phone_number"].replace("-", "").replace(" ", "")
            if len(phone) == 10:
                phone_formatted = f"{phone[:3]}-{phone[3:6]}-{phone[6:]}"
            else:
                phone_formatted = phone

            # Fill form
            print("Filling complaint form...")

            # Helper to select dropdown by clicking and choosing option
            def select_dropdown(field_id, option_text):
                try:
                    # Find the nesty-input (custom dropdown trigger)
                    dropdown = page.locator(f'#{field_id}').locator('..').locator('a.nesty-input')
                    if dropdown.is_visible(timeout=2000):
                        dropdown.click()
                        time.sleep(0.5)
                        # Find and click the option
                        option = page.locator(f'li:has-text("{option_text}")').first
                        if option.is_visible(timeout=2000):
                            option.click()
                            time.sleep(0.3)
                            return True
                except Exception:
                    pass
                # Try standard select
                try:
                    page.select_option(f'#{field_id}', label=option_text)
                    return True
                except Exception:
                    pass
                return False

            # Basic fields
            subject = f"Internet Speed Below Advertised - {config['isp_name']}"
            page.fill('#request_subject', subject)

            # Truncate description if too long (FCC has ~3000 char limit)
            max_desc = 2900
            if len(complaint_text) > max_desc:
                complaint_text = complaint_text[:max_desc] + "\n\n[Full data available upon request]"
            page.fill('#request_description', complaint_text)

            # Email
            try:
                page.fill('input[name="request[anonymous_requester_email]"]', config["email"])
            except Exception:
                pass

            # Dropdown selections - find by label text and click nesty dropdown
            print("Selecting dropdown options...")

            def select_nesty_by_label(label_text, option_text):
                """Find a nesty dropdown by its label and select an option."""
                try:
                    # Find the label
                    label = page.locator(f'label:has-text("{label_text}")').first
                    if not label.is_visible(timeout=2000):
                        print(f"  Label not found: {label_text}")
                        return False

                    # Find the dropdown container (parent or sibling)
                    container = label.locator('..')

                    # Find the nesty-input trigger
                    nesty = container.locator('a.nesty-input').first
                    if not nesty.is_visible(timeout=2000):
                        # Try finding in the next sibling div
                        nesty = label.locator('xpath=following-sibling::*//a[contains(@class, "nesty-input")]').first

                    if nesty.is_visible(timeout=2000):
                        # Scroll into view and click
                        nesty.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        nesty.click()
                        time.sleep(0.5)

                        # Find and click the option
                        option = page.locator(f'ul.nesty-panel li:has-text("{option_text}")').first
                        if option.is_visible(timeout=2000):
                            option.click()
                            print(f"  Selected {label_text}: {option_text}")
                            time.sleep(0.3)
                            return True
                        else:
                            # Try partial match
                            options = page.locator('ul.nesty-panel li').all()
                            for opt in options:
                                if option_text.lower() in opt.text_content().lower():
                                    opt.click()
                                    print(f"  Selected {label_text}: {opt.text_content()}")
                                    time.sleep(0.3)
                                    return True
                            print(f"  Option not found: {option_text}")
                            # Click elsewhere to close dropdown
                            page.locator('body').click(position={"x": 10, "y": 10})
                except Exception as e:
                    print(f"  Error selecting {label_text}: {e}")
                return False

            # First, select Internet Issues = Speed (this reveals other fields)
            print("Selecting Internet Issues...")
            # Get only visible nesty dropdowns
            all_dropdowns = page.locator('a.nesty-input').all()
            visible_dropdowns = []
            for d in all_dropdowns:
                try:
                    if d.is_visible(timeout=500):
                        visible_dropdowns.append(d)
                except:
                    pass
            print(f"  Found {len(visible_dropdowns)} visible dropdowns (of {len(all_dropdowns)} total)")

            # Find the first dropdown showing "-" (Internet Issues)
            for i, nesty in enumerate(visible_dropdowns):
                try:
                    current_text = nesty.text_content().strip()
                    print(f"  Dropdown {i}: '{current_text}'")

                    if current_text == "-":
                        nesty.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        nesty.click()
                        time.sleep(0.5)

                        # Look for Speed option in the dropdown - try multiple approaches
                        panel = page.locator('ul.nesty-panel:visible, div.nesty-panel:visible').first
                        if panel.is_visible(timeout=2000):
                            # Get all options and find Speed
                            options = panel.locator('li').all()
                            print(f"  Found {len(options)} options in dropdown")
                            for opt in options:
                                try:
                                    opt_text = opt.text_content().strip()
                                    opt_id = opt.get_attribute('id') or ''
                                    if 'speed' in opt_text.lower() or 'speed' in opt_id.lower():
                                        opt.scroll_into_view_if_needed()
                                        time.sleep(0.1)
                                        opt.click(force=True)
                                        print(f"  Selected: {opt_text}")
                                        time.sleep(1)
                                        break
                                except Exception as e2:
                                    continue
                            else:
                                print("  Speed option not found, pressing Escape")
                                page.keyboard.press("Escape")
                        break
                except Exception as e:
                    print(f"  Error on dropdown {i}: {e}")

            # Re-scan dropdowns after Internet Issues is selected
            time.sleep(1)
            print("Filling remaining dropdowns...")

            # Values to select (in order: Sub Issue, Internet Method, Company, Relationship, Contacted, On Behalf)
            dropdown_values = [
                ("Less than Advertised", "Sub Issue"),
                ("Fiber", "Internet Method"),
                ("Verizon", "Company"),
                ("Current", "Relationship"),
                ("Yes", "Contacted"),
                # "Filing on Behalf" is handled separately after form fill
            ]

            # Get fresh list of visible dropdowns
            all_dropdowns = page.locator('a.nesty-input').all()
            visible_dropdowns = []
            for d in all_dropdowns:
                try:
                    if d.is_visible(timeout=300):
                        visible_dropdowns.append(d)
                except:
                    pass
            print(f"  Now have {len(visible_dropdowns)} visible dropdowns")

            value_index = 0
            for i, nesty in enumerate(visible_dropdowns):
                try:
                    current_text = nesty.text_content().strip()
                    # Skip dropdowns already filled
                    if current_text != "-":
                        continue

                    if value_index >= len(dropdown_values):
                        break

                    value, desc = dropdown_values[value_index]
                    value_index += 1

                    nesty.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    nesty.click()
                    time.sleep(0.4)

                    # Find option containing the value text in visible panel
                    panel = page.locator('ul.nesty-panel:visible, div.nesty-panel:visible').first
                    found = False
                    if panel.is_visible(timeout=1000):
                        options = panel.locator('li').all()
                        for opt in options:
                            try:
                                opt_text = opt.text_content().strip()
                                if value.lower() in opt_text.lower():
                                    opt.scroll_into_view_if_needed()
                                    time.sleep(0.1)
                                    opt.click(force=True)
                                    print(f"  Selected {desc}: {opt_text}")
                                    time.sleep(0.3)
                                    found = True
                                    break
                            except:
                                pass
                    if not found:
                        # Close dropdown if no match
                        page.keyboard.press("Escape")
                        print(f"  Could not find option for {desc}: {value}")
                        time.sleep(0.2)
                except Exception as e:
                    print(f"  Error on dropdown {i}: {e}")

            # Contact information - find fields by label text
            print("Filling contact information...")

            def fill_field_by_label(label_text, value, is_select=False):
                """Find input field by its label text and fill it."""
                if not value:
                    return False
                try:
                    # Try to find label and get the associated input
                    label = page.locator(f'label:has-text("{label_text}")').first
                    if label.is_visible(timeout=2000):
                        label.scroll_into_view_if_needed()
                        time.sleep(0.1)

                        # Get the 'for' attribute
                        for_attr = label.get_attribute('for')
                        if for_attr:
                            target = page.locator(f'#{for_attr}')
                            if target.is_visible(timeout=1000):
                                if is_select:
                                    # For nesty dropdowns
                                    nesty = target.locator('..').locator('a.nesty-input')
                                    if nesty.is_visible(timeout=500):
                                        nesty.click()
                                        time.sleep(0.3)
                                        opt = page.locator(f'ul.nesty-panel li:has-text("{value}")').first
                                        if opt.is_visible(timeout=1000):
                                            opt.click()
                                            print(f"  Filled {label_text}: {value}")
                                            return True
                                    # Standard select
                                    page.select_option(f'#{for_attr}', label=value)
                                else:
                                    target.fill(value)
                                print(f"  Filled {label_text}: {value}")
                                return True

                        # Try finding input in parent container
                        container = label.locator('..')
                        input_elem = container.locator('input:not([type="hidden"]), textarea').first
                        if input_elem.is_visible(timeout=1000):
                            input_elem.fill(value)
                            print(f"  Filled {label_text}: {value}")
                            return True
                except Exception as e:
                    print(f"  Could not fill {label_text}: {e}")
                return False

            # Fill all contact fields by label
            fill_field_by_label("Account Number", config.get("isp_account_number", ""))
            fill_field_by_label("Your First Name", config.get('first_name', ''))
            fill_field_by_label("Your Last Name", config.get('last_name', ''))
            fill_field_by_label("Address 1", street)
            fill_field_by_label("City", city)
            fill_field_by_label("State", state, is_select=True)
            fill_field_by_label("Zip Code", zip_code)
            fill_field_by_label("Phone", phone_formatted)

            # Fallback: try common input patterns if labels didn't work
            fallback_fields = [
                ('input[id*="22623424"]', config.get("isp_account_number", "")),  # Account
                ('input[id*="22623434"]', config.get('first_name', '')),     # First name
                ('input[id*="22623444"]', config.get('last_name', '')),    # Last name
                ('input[id*="22623454"]', street),                                   # Address
                ('input[id*="22609454"]', city),                                     # City
                ('input[id*="22609474"]', zip_code),                                 # Zip
                ('input[id*="22609484"]', phone_formatted),                          # Phone
            ]
            for selector, value in fallback_fields:
                if value:
                    try:
                        elem = page.locator(selector).first
                        if elem.is_visible(timeout=1000):
                            tag = elem.evaluate('el => el.tagName')
                            if tag == 'SELECT':
                                page.select_option(selector, label=value)
                            else:
                                page.fill(selector, value)
                            print(f"  Filled {selector}")
                    except Exception:
                        pass

            # JavaScript-based form filling as final fallback
            print("Running JS-based form fill...")
            form_data = {
                "Account Number": config.get("isp_account_number", ""),
                "First Name": config.get('first_name', ''),
                "Last Name": config.get('last_name', ''),
                "Address 1": street,
                "City": city,
                "Zip": zip_code,
                "Phone": phone_formatted,
            }
            js_fill = """
            (formData) => {
                const results = [];
                // Find all labels and their associated inputs
                document.querySelectorAll('label').forEach(label => {
                    const labelText = label.textContent.trim().replace('*', '').trim();
                    for (const [key, value] of Object.entries(formData)) {
                        if (labelText.toLowerCase().includes(key.toLowerCase()) && value) {
                            const forId = label.getAttribute('for');
                            let input = forId ? document.getElementById(forId) : null;
                            if (!input) {
                                input = label.parentElement.querySelector('input, select, textarea');
                            }
                            if (input && !input.value) {
                                if (input.tagName === 'SELECT') {
                                    // For select, find matching option
                                    for (const opt of input.options) {
                                        if (opt.text.includes(value) || opt.value === value) {
                                            input.value = opt.value;
                                            input.dispatchEvent(new Event('change', { bubbles: true }));
                                            results.push(`Selected ${key}: ${value}`);
                                            break;
                                        }
                                    }
                                } else {
                                    input.value = value;
                                    input.dispatchEvent(new Event('input', { bubbles: true }));
                                    input.dispatchEvent(new Event('change', { bubbles: true }));
                                    results.push(`Filled ${key}: ${value}`);
                                }
                            }
                        }
                    }
                });
                return results;
            }
            """
            try:
                results = page.evaluate(js_fill, form_data)
                for r in results:
                    print(f"  {r}")
            except Exception as e:
                print(f"  JS fill error: {e}")

            # Handle State dropdown specially (often a custom nesty dropdown)
            # Map state abbreviations to full names
            state_names = {
                "PA": "Pennsylvania", "CA": "California", "NY": "New York", "TX": "Texas",
                "FL": "Florida", "IL": "Illinois", "OH": "Ohio", "GA": "Georgia",
                "NC": "North Carolina", "MI": "Michigan", "NJ": "New Jersey", "VA": "Virginia",
                "WA": "Washington", "AZ": "Arizona", "MA": "Massachusetts", "TN": "Tennessee",
                "IN": "Indiana", "MO": "Missouri", "MD": "Maryland", "WI": "Wisconsin",
                "CO": "Colorado", "MN": "Minnesota", "SC": "South Carolina", "AL": "Alabama",
                "LA": "Louisiana", "KY": "Kentucky", "OR": "Oregon", "OK": "Oklahoma",
                "CT": "Connecticut", "UT": "Utah", "IA": "Iowa", "NV": "Nevada",
                "AR": "Arkansas", "MS": "Mississippi", "KS": "Kansas", "NM": "New Mexico",
                "NE": "Nebraska", "WV": "West Virginia", "ID": "Idaho", "HI": "Hawaii",
                "NH": "New Hampshire", "ME": "Maine", "MT": "Montana", "RI": "Rhode Island",
                "DE": "Delaware", "SD": "South Dakota", "ND": "North Dakota", "AK": "Alaska",
                "DC": "District of Columbia", "VT": "Vermont", "WY": "Wyoming",
            }
            state_full = state_names.get(state.upper(), state)
            try:
                # Use the specific field ID to avoid matching "State (on behalf of)"
                state_dropdown = page.locator('a.nesty-input[aria-labelledby="request_custom_fields_22540114_label"]')
                if not state_dropdown.is_visible(timeout=1000):
                    # Fallback: get the first State label's nesty-input
                    state_dropdown = page.locator('label:text-is("State")').locator('..').locator('a.nesty-input').first
                if state_dropdown.is_visible(timeout=1000):
                    state_dropdown.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    state_dropdown.click()
                    time.sleep(0.4)
                    # Find the state option in the visible panel
                    panel = page.locator('ul.nesty-panel:visible, div.nesty-panel:visible').first
                    if panel.is_visible(timeout=1000):
                        options = panel.locator('li').all()
                        for opt in options:
                            opt_text = opt.text_content().strip()
                            if state_full.lower() in opt_text.lower() or state.upper() in opt_text.upper():
                                opt.scroll_into_view_if_needed()
                                time.sleep(0.1)
                                opt.click(force=True)
                                print(f"  Selected State: {opt_text}")
                                break
                        else:
                            page.keyboard.press("Escape")
                            print(f"  State not found: {state_full}")
            except Exception as e:
                print(f"  State dropdown error: {e}")

            # Select "Filing on Behalf of Someone" = "No"
            print("Selecting 'Filing on Behalf of Someone'...")
            filing_selected = False
            try:
                # Find by label text
                label = page.locator('label:has-text("Filing on Behalf of Someone")').first
                if label.is_visible(timeout=2000):
                    container = label.locator('..')
                    nesty = container.locator('a.nesty-input').first
                    if nesty.is_visible(timeout=2000):
                        nesty.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        nesty.click()
                        time.sleep(0.5)
                        panel = page.locator('ul.nesty-panel:visible, div.nesty-panel:visible').first
                        if panel.is_visible(timeout=2000):
                            options = panel.locator('li').all()
                            for opt in options:
                                opt_text = opt.text_content().strip()
                                if opt_text.lower().startswith("no"):
                                    opt.click(force=True)
                                    print(f"  Selected: {opt_text}")
                                    filing_selected = True
                                    time.sleep(0.3)
                                    break
                            if not filing_selected:
                                page.keyboard.press("Escape")
            except Exception as e:
                print(f"  Error selecting Filing on Behalf: {e}")

            if not filing_selected:
                # Fallback: try by field ID
                try:
                    select_dropdown('request_custom_fields_22623494', 'No')
                    filing_selected = True
                except Exception:
                    pass

            if not filing_selected:
                print("  WARNING: Could not select 'Filing on Behalf of Someone'. You may need to select it manually.")

            print("Form filled!")

            # Screenshot before submit
            page.screenshot(path=str(state_path / "before_submit.png"))
            print(f"Screenshot saved: {state_path / 'before_submit.png'}")

            # Submit
            if not auto_submit:
                print("\n" + "=" * 60)
                print("READY TO SUBMIT")
                print("Review the form in the browser window.")
                print("Press Enter here to submit, or Ctrl+C to cancel...")
                print("=" * 60)
                input()
            else:
                print("\nAuto-submitting in 3 seconds...")
                time.sleep(3)

            submit = page.locator('input[type="submit"][value="Submit"]')
            if not submit.is_visible(timeout=3000):
                submit = page.locator('input[type="submit"]').first
            submit.click()

            print("Clicked submit...")
            time.sleep(5)
            page.wait_for_load_state("domcontentloaded")

            # Screenshot after submit
            page.screenshot(path=str(state_path / "after_submit.png"))
            print(f"Screenshot saved: {state_path / 'after_submit.png'}")

            # Check for success
            if "new" not in page.url.lower():
                print("\nCOMPLAINT SUBMITTED SUCCESSFULLY!")
                return True
            else:
                print("\nWarning: May still be on form page. Check screenshots.")
                return False

        finally:
            print("\nClosing browser (session saved for next time)...")
            context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="File FCC complaint from laptop using Pi data")
    parser.add_argument("--pi-host", default=DEFAULT_PI_HOST, help=f"Pi hostname (default: {DEFAULT_PI_HOST})")
    parser.add_argument("--pi-user", default=DEFAULT_PI_USER, help=f"Pi username (default: {DEFAULT_PI_USER})")
    parser.add_argument("--pi-path", default=DEFAULT_PI_PATH, help=f"Path on Pi (default: {DEFAULT_PI_PATH})")
    parser.add_argument("--date", help="Date to report (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--dry-run", action="store_true", help="Show complaint text without filing")
    parser.add_argument("--auto-submit", action="store_true", help="Auto-submit without confirmation")
    parser.add_argument("--min-failures", type=int, default=1, help="Minimum failures to file (default: 1)")
    args = parser.parse_args()

    print("=" * 60)
    print("FCC Complaint Filer - Laptop Client")
    print("=" * 60 + "\n")

    # Fetch data from Pi
    try:
        data = fetch_data_from_pi(args.pi_host, args.pi_user, args.pi_path, args.date)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return 1

    if data.get("error"):
        print(f"Error from Pi: {data['error']}")
        return 1

    tests = data.get("tests", [])
    config = data.get("config", {})

    print(f"Date: {data['date']}")
    print(f"Tests found: {len(tests)}")

    if not tests:
        print("No tests for this date. Nothing to file.")
        return 0

    # Calculate failures
    threshold = config.get("threshold_speed_mbps", 700)
    failed = [t for t in tests if t["download_mbps"] < threshold]
    failure_rate = (len(failed) / len(tests)) * 100

    print(f"Failed tests: {len(failed)} ({failure_rate:.1f}%)")
    print(f"Threshold: {threshold:.1f} Mbps")
    print()

    if len(failed) < args.min_failures:
        print(f"Only {len(failed)} failures (minimum: {args.min_failures}). Skipping.")
        return 0

    # Generate complaint
    complaint_text = generate_complaint_text(data)

    if not complaint_text:
        print("Could not generate complaint text.")
        return 1

    # File it
    try:
        success = file_complaint_with_browser(data, complaint_text, args.dry_run, args.auto_submit)
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        return 1
    except Exception as e:
        print(f"Error filing complaint: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
