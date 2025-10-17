#!/usr/bin/env python3
"""
Debug JavaScript transitions and form submission behavior.

This script provides detailed analysis of what happens during form submission,
including monitoring page transitions, JavaScript execution, and network requests.
"""

import argparse
import json
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager


def monitor_page_transitions(driver, duration_seconds=30):
    """Monitor page transitions and JavaScript activity."""
    print(f"🔍 Monitoring page transitions for {duration_seconds} seconds...")

    states = []
    start_time = time.time()

    while time.time() - start_time < duration_seconds:
        try:
            current_time = time.time() - start_time
            url = driver.current_url
            title = driver.title

            # Get JavaScript state
            js_state = driver.execute_script("""
                return {
                    readyState: document.readyState,
                    url: window.location.href,
                    title: document.title,
                    activeTimers: (function() {
                        // Count setTimeout/setInterval calls
                        var count = 0;
                        for (var i = 1; i < 10000; i++) {
                            try {
                                if (window.clearTimeout.toString().indexOf(i) > -1 ||
                                    window.clearInterval.toString().indexOf(i) > -1) {
                                    count++;
                                }
                            } catch(e) {}
                        }
                        return count;
                    })(),
                    formElements: document.forms.length,
                    hasProgressIndicators: document.querySelector('.progress, .loading, .spinner') !== null,
                    bodyContent: document.body ? document.body.innerHTML.substring(0, 200) : 'No body'
                };
            """)

            state = {"time": round(current_time, 1), "url": url, "title": title, "js_state": js_state}

            states.append(state)

            # Print significant changes
            if len(states) == 1 or states[-1]["title"] != states[-2]["title"]:
                print(f"   {current_time:.1f}s: {title}")
                if js_state["hasProgressIndicators"]:
                    print(f"     🔄 Progress indicators detected")
                if js_state["activeTimers"] > 0:
                    print(f"     ⏰ {js_state['activeTimers']} active timers")

            time.sleep(1)

        except Exception as e:
            print(f"   Error monitoring: {e}")
            break

    return states


def analyze_form_submission_behavior(rpi_ip: str, visible=False):
    """Analyze the complete form submission behavior."""
    print(f"🔍 Analyzing form submission behavior on {rpi_ip}")
    print(f"   Visible browser: {visible}")

    driver = None
    try:
        # Setup Firefox
        firefox_service = FirefoxService(GeckoDriverManager().install())
        firefox_options = webdriver.FirefoxOptions()

        if not visible:
            firefox_options.add_argument("--headless")

        firefox_options.add_argument("--no-sandbox")
        firefox_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Firefox(service=firefox_service, options=firefox_options)
        driver.set_page_load_timeout(30)

        print("✓ Browser started")

        # Navigate to setup page
        print(f"📄 Loading http://{rpi_ip}/setup...")
        driver.get(f"http://{rpi_ip}/setup")

        # Analyze initial page
        initial_state = driver.execute_script("""
            return {
                url: window.location.href,
                title: document.title,
                forms: document.forms.length,
                scripts: document.scripts.length,
                inlineScripts: Array.from(document.scripts).filter(s => s.innerHTML.trim()).length,
                formAction: document.forms[0] ? document.forms[0].action : null,
                formMethod: document.forms[0] ? document.forms[0].method : null,
                submitButtons: document.querySelectorAll('input[type="submit"], button[type="submit"]').length
            };
        """)

        print(f"📊 Initial Page State:")
        print(f"   URL: {initial_state['url']}")
        print(f"   Title: {initial_state['title']}")
        print(f"   Forms: {initial_state['forms']}")
        print(f"   Scripts: {initial_state['scripts']} total, {initial_state['inlineScripts']} inline")
        print(f"   Form action: {initial_state['formAction']}")
        print(f"   Form method: {initial_state['formMethod']}")
        print(f"   Submit buttons: {initial_state['submitButtons']}")

        if visible:
            input("Press Enter to continue with form filling...")

        # Fill the form
        print("\n📝 Filling form...")
        wait = WebDriverWait(driver, 10)

        # Fill form fields
        site_name_input = wait.until(EC.presence_of_element_located((By.ID, "site_name")))
        site_name_input.clear()
        site_name_input.send_keys("automated test site")

        lat_input = driver.find_element(By.ID, "lat")
        lat_input.clear()
        lat_input.send_keys("45.48")

        lon_input = driver.find_element(By.ID, "lon")
        lon_input.clear()
        lon_input.send_keys("-122.66")

        alt_input = driver.find_element(By.ID, "alt")
        alt_input.clear()
        alt_input.send_keys("30")

        # Click ADSB checkbox with better scrolling
        adsb_checkbox = driver.find_element(By.ID, "is_adsb_feeder")

        # Scroll to element with offset to avoid navbar
        driver.execute_script(
            """
            arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});
            // Scroll up a bit to avoid navbar
            window.scrollBy(0, -100);
        """,
            adsb_checkbox,
        )
        time.sleep(2)

        # Try to click, fallback to JavaScript click if needed
        try:
            adsb_checkbox.click()
        except Exception:
            driver.execute_script("arguments[0].click();", adsb_checkbox)

        print("✓ Form filled")

        if visible:
            input("Press Enter to submit form and watch the magic...")

        # Analyze form before submission
        pre_submit_state = driver.execute_script("""
            var form = document.forms[0];
            var submitBtn = document.querySelector('button[type="submit"]');
            return {
                formOnSubmit: form ? form.onsubmit : null,
                submitOnClick: submitBtn ? submitBtn.onclick : null,
                formData: form ? new FormData(form).entries() : null
            };
        """)

        print(f"\n🔍 Pre-submission Analysis:")
        print(f"   Form onsubmit: {pre_submit_state['formOnSubmit']}")
        print(f"   Submit onclick: {pre_submit_state['submitOnClick']}")

        # Submit the form
        print(f"\n🚀 Submitting form...")
        submit_button = driver.find_element(By.XPATH, "//button[@type='submit'][@name='submit'][@value='go']")
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)
        submit_button.click()

        # Monitor what happens after submission
        print(f"\n📊 Monitoring post-submission behavior...")
        transitions = monitor_page_transitions(driver, 30)

        # Analyze the results
        print(f"\n📈 Transition Analysis:")
        print(f"   Total state changes: {len(transitions)}")

        unique_titles = set(state["title"] for state in transitions)
        print(f"   Unique page titles: {len(unique_titles)}")
        for title in unique_titles:
            print(f"     - {title}")

        unique_urls = set(state["url"] for state in transitions)
        print(f"   Unique URLs: {len(unique_urls)}")
        for url in unique_urls:
            print(f"     - {url}")

        # Check for JavaScript timers
        timer_states = [state for state in transitions if state["js_state"]["activeTimers"] > 0]
        if timer_states:
            print(f"   ⏰ JavaScript timers detected at: {[s['time'] for s in timer_states]}s")

        # Check for progress indicators
        progress_states = [state for state in transitions if state["js_state"]["hasProgressIndicators"]]
        if progress_states:
            print(f"   🔄 Progress indicators at: {[s['time'] for s in progress_states]}s")

        # Final state
        final_state = transitions[-1] if transitions else None
        if final_state:
            print(f"\n🎯 Final State:")
            print(f"   Title: {final_state['title']}")
            print(f"   URL: {final_state['url']}")
            print(f"   Ready state: {final_state['js_state']['readyState']}")

        # Save detailed log
        log_file = f"js_transition_log_{int(time.time())}.json"
        with open(log_file, "w") as f:
            json.dump(
                {
                    "rpi_ip": rpi_ip,
                    "visible_browser": visible,
                    "initial_state": initial_state,
                    "pre_submit_state": pre_submit_state,
                    "transitions": transitions,
                    "final_state": final_state,
                },
                f,
                indent=2,
            )

        print(f"\n💾 Detailed log saved to: {log_file}")

        return True

    except Exception as e:
        print(f"✗ Error during analysis: {e}")
        return False
    finally:
        if driver:
            if visible:
                input("Press Enter to close browser...")
            driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Debug JavaScript transitions during form submission")
    parser.add_argument("rpi_ip", help="IP address of the Raspberry Pi")
    parser.add_argument("--visible", action="store_true", help="Use visible browser for manual observation")
    parser.add_argument("--headless", action="store_true", help="Use headless browser (default)")

    args = parser.parse_args()

    visible = args.visible and not args.headless

    print("🔍 JavaScript Transition Debugger")
    print("This tool will analyze what happens during form submission")
    print()

    success = analyze_form_submission_behavior(args.rpi_ip, visible)

    if success:
        print("\n🎉 Analysis completed successfully!")
        print("\nNext steps:")
        print("1. Check the generated JSON log file for detailed transition data")
        print("2. Compare headless vs visible browser behavior")
        print("3. Look for patterns in page transitions and JavaScript timers")
    else:
        print("\n❌ Analysis failed!")


if __name__ == "__main__":
    main()
