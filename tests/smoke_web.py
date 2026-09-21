"""Browser smoke test for web/: serves the page locally with an in-memory stand-in for Supabase (fake_supabase.js)
and walks through sign-in, add, duplicate detection, filters, detail view, edit, check now, Telegram states, delete.
Run: .venv/bin/python tests/smoke_web.py   (needs: playwright install chromium). Screenshots land in .smoke-*.png."""
import os, subprocess, sys, time
from playwright.sync_api import sync_playwright
SCR = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(SCR)
fake = open(SCR + "/fake_supabase.js").read()
cfg = 'window.PW_CONFIG={supabaseUrl:"https://x.supabase.co",supabaseAnonKey:"k",telegramBot:"sid_watch_bot",checkIntervalHours:6,maxItems:100,cronMinutes:[7,22,37,52]};'
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765", "--bind", "127.0.0.1"], cwd=ROOT + "/web", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(0.8)
errors = []
def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg); errors.append(msg) if not cond else None
try:
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={"width": 1100, "height": 900}, permissions=["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        page.route("**/supabase.js", lambda r: r.fulfill(body=fake, content_type="application/javascript"))
        page.route("**/config.js*", lambda r: r.fulfill(body=cfg, content_type="application/javascript"))
        page.on("dialog", lambda d: d.accept())
        page.on("console", lambda m: print("  console." + m.type + ":", m.text) if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: (print("  PAGEERROR:", e), errors.append(str(e))))
        page.goto("http://127.0.0.1:8765/")
        page.wait_for_selector("#signin:not([hidden])")
        check(page.is_visible("#steps") and page.is_visible("#stores"), "signed-out: hero, steps and stores visible")
        check(page.is_visible("#nav") and page.is_visible("#how") and page.is_visible("#features") and page.is_visible("#faq") and page.is_visible(".demo"),
              "landing: nav, how-it-works, features, FAQ and demo card visible")
        check(page.locator("#features .feat").count() == 6 and page.locator("#faq details").count() == 6, "landing: 6 feature cards and 6 FAQ entries")
        page.locator("#faq details summary").first.click(); check(page.locator("#faq details p").first.is_visible(), "FAQ entry expands")
        check(page.is_hidden("#app") and page.is_hidden("#who"), "app and account menu hidden while signed out")
        page.fill("#magic input", "sid@example.com"); page.click("#magic button")
        page.wait_for_selector("#toast", state="visible")
        check("Check your email" in page.text_content("#toast"), "magic link toast")
        page.screenshot(path=SCR + "/../.smoke-signin.png")

        page.evaluate("window.__fake.signIn('sid@example.com')")
        page.wait_for_selector("#app:not([hidden])")
        page.wait_for_selector(".empty:has-text('Nothing tracked yet')")
        check(page.is_hidden("#landing") and page.is_hidden("#nav"), "landing hidden once signed in")
        check(page.is_visible("#start") and page.locator("#start .st.done").count() == 0, "getting-started checklist shown with nothing done")
        check(page.is_hidden("#stats") and page.is_hidden("#tabs"), "stats strip and tabs hidden with no items")
        check(page.is_visible("#tg") and "Connect Telegram" in page.text_content("#tg"), "telegram notice shown when not linked")
        check(page.is_hidden("#toolbar"), "toolbar hidden with no items")

        # add an item, with tracking junk in the url
        page.fill("#add input[name=url]", "https://www.nike.com/t/dunk-low-retro-mens-shoes-76KnBL/DD1391-100?utm_source=ig&fbclid=abc")
        page.wait_for_function("document.querySelector('#hint').textContent.includes('Nike')")
        check("Nike: Dunk Low Retro Mens Shoes" in page.text_content("#hint"), "hint guesses store + name from link: " + page.text_content("#hint"))
        page.fill("#add input[name=size]", "M"); page.fill("#add input[name=target]", "90"); page.check("#add input[name=restock]")
        page.click("#add button[type=submit]")
        page.wait_for_selector(".item")
        row = page.locator(".item").first
        check("Dunk Low Retro Mens Shoes" in row.text_content(), "row shows guessed name before first check")
        check("check queued in ~" in row.text_content(), "row says check is queued with countdown")
        check(row.locator("button[data-act=check]").is_disabled(), "check-now button disabled while queued")
        stored = page.evaluate("window.__fake.state.tables.items[0]")
        check(stored["url"] == "https://www.nike.com/t/dunk-low-retro-mens-shoes-76KnBL/DD1391-100", "tracking params stripped: " + stored["url"])
        check(stored["check_requested"] == 1 and stored["size"] == "M" and stored["target_price"] == 90 and stored["notify_restock"] == 1, "stored fields correct")

        # duplicate
        page.fill("#add input[name=url]", "https://www.nike.com/t/dunk-low-retro-mens-shoes-76KnBL/DD1391-100?utm_medium=x")
        page.wait_for_function("document.querySelector('#hint').textContent.includes('Already')")
        page.fill("#add input[name=size]", "M"); page.click("#add button[type=submit]")
        page.wait_for_function("document.querySelector('#toast').textContent.includes('already tracking')")
        check(page.evaluate("window.__fake.state.tables.items.length") == 1, "duplicate link+size rejected")
        page.fill("#add input[name=url]", ""); page.fill("#add input[name=size]", "")

        # search page rejected
        page.fill("#add input[name=url]", "https://www.google.com/search?q=nike+dunk"); page.click("#add button[type=submit]")
        page.wait_for_function("document.querySelector('#toast').textContent.includes('search page')")
        check(True, "search page rejected"); page.fill("#add input[name=url]", "")

        # simulate a cron run: name, image, sizes, history with a sale, plus a second item
        page.evaluate("""window.__fake.cron((T, S) => {
          const it = T.items[0]; Object.assign(it, { name: "Nike Dunk Low Retro", store: "nike", currency: "USD", image_url: "", check_requested: 0,
            sizes_json: JSON.stringify({ "S": true, "M": false, "L": true, "XL": true }) });
          const day = 86400000, now = Date.now();
          [[5,125,null,1],[4,125,null,1],[3,110,125,1],[2,110,125,0],[1,95,125,0],[0,95,125,0]].forEach(([d,p,o,s]) =>
            T.price_history.push({ item_id: it.id, price: p, original_price: o, in_stock: s, checked_at: new Date(now - d*day).toISOString() }));
          T.alerts.push({ item_id: it.id, type: "price_drop", old_price: 125, new_price: 110, sent_at: new Date(now - 3*day).toISOString() });
          T.items.push({ id: S.seq++, user_id: it.user_id, url: "https://www.zara.com/us/en/ribbed-knit-sweater-p04938200.html", size: null, target_price: null,
            notify_restock: 0, active: 1, check_requested: 0, created_at: new Date(now - 10*day).toISOString(), fail_count: 3,
            last_error: "http: HTTP 403; browser: no price in rendered HTML", sizes_json: null, name: null, image_url: null, store: null, currency: null });
          T.price_history.push({ item_id: S.seq - 1, price: null, original_price: null, in_stock: null, checked_at: new Date(now - 1*day).toISOString() });
        })""")
        page.reload(); page.wait_for_selector(".item"); page.wait_for_function("document.querySelectorAll('.item').length === 2")
        check(page.is_visible("#toolbar"), "toolbar visible with 2 items")
        st = page.text_content("#stats")
        check(page.is_visible("#stats") and "Tracked2" in st.replace("\n", "") and "On sale1" in st.replace("\n", "") and "$30.00" in st, "stats strip: counts and savings vs first seen: " + st.replace("\n", " "))
        page.click("#stats [data-filter=sale]"); check(page.locator(".item").count() == 1 and page.locator("#stats .stat.on").count() == 1, "stat tile filters the list")
        page.click("#stats [data-filter=all]")
        check(page.locator("#start .st.done").count() == 1, "checklist ticks 'first item' once one exists")
        page.click("#start [data-start=dismiss]"); check(page.is_hidden("#start"), "checklist dismisses")
        page.click("#tabs [data-tab=activity]")
        act = page.text_content("#activity")
        check(page.is_visible("#activity") and page.is_hidden("#list") and page.is_hidden("#toolbar"), "activity tab swaps the list out")
        check("Nike Dunk Low Retro" in act and "price dropped" in act and "$125.00 → $110.00" in act, "activity feed lists the alert with prices: " + act.strip()[:80])
        check("Activity 1" in page.text_content("#tabs"), "activity tab shows alert count")
        page.click("#activity [data-open]")
        page.wait_for_selector(".detail")
        check(page.is_visible("#list") and "History" in page.text_content(".detail"), "clicking an activity entry opens that item")
        page.locator(".item", has_text="Nike Dunk Low Retro").locator(".meta").first.click(); page.wait_for_selector(".detail", state="detached")
        page.click("#checkAll"); page.wait_for_function("document.querySelector('#toast').textContent.includes('Queued 2')")
        check(all(i["check_requested"] == 1 for i in page.evaluate("window.__fake.state.tables.items")) and page.is_hidden("#checkAll"), "check all queues every active item and hides itself")
        page.evaluate("window.__fake.cron((T) => T.items.forEach((i) => i.check_requested = 0))"); page.reload(); page.wait_for_selector(".item")
        check(page.locator("#sort option[value=store]").count() == 1, "sort by store available")
        page.keyboard.press("n"); check(page.evaluate("document.activeElement === document.querySelector('#add input[name=url]')"), "'n' focuses the add field")
        page.keyboard.press("Escape"); page.evaluate("document.activeElement.blur()")
        page.keyboard.press("/"); check(page.evaluate("document.activeElement === document.querySelector('#q')"), "'/' focuses search")
        page.evaluate("document.activeElement.blur()")
        nike = page.locator(".item", has_text="Nike Dunk Low Retro")
        t = nike.text_content()
        check("$95.00" in t and "$125.00" in t and "24% off" in t, "price, was-price and % off badge")
        check("sold out" in t and "low $95.00" in t and "price drop" in t, "sold-out badge, low, last alert")
        check(nike.locator("svg").count() == 1, "sparkline drawn")
        zara = page.locator(".item", has_text="Ribbed Knit Sweater")
        check("blocking automated checks" in zara.text_content(), "friendly failure hint for 403")
        check("Needs attention 1" in page.text_content("#filters") and "On sale 1" in page.text_content("#filters"), "filter chips with counts: " + page.text_content("#filters"))
        page.click("#filters [data-filter=failing]")
        check(page.locator(".item").count() == 1 and "Ribbed" in page.locator(".item").first.text_content(), "filter to failing works")
        page.click("#filters [data-filter=all]")
        page.fill("#q", "dunk"); check(page.locator(".item").count() == 1, "search filters list"); page.fill("#q", "")
        page.select_option("#sort", "price"); check("Nike" in page.locator(".item").first.text_content(), "sort by price puts priced item first"); page.select_option("#sort", "new")

        # expand detail
        nike.locator(".meta").first.click()
        page.wait_for_selector(".detail")
        d = page.locator(".detail").text_content()
        check("History" in d and "Alerts" in d and "first seen" in d and "6 checks" in d, "detail shows stats, history, alerts")
        check("avg" in d and "24% below high" in d and "tracked" in d, "detail shows average, % below high and days tracked")
        check(page.locator(".detail [data-pick]").count() == 4 and page.locator(".detail [data-pick='M'].on").count() == 1, "size chips shown, M highlighted")
        check(page.locator("#bigchart-" + str(stored["id"]) + " svg").count() == 1, "big chart in detail")
        page.screenshot(path=SCR + "/../.smoke-desktop.png", full_page=True)

        # edit: size to XL (not matched? it is on page), target 80
        nike.locator("button[data-act=edit]").click()
        page.wait_for_selector("form.edit")
        page.click("form.edit [data-size='XL']")
        check(page.input_value("form.edit input[name=size]") == "XL", "size chip fills the size field")
        check(page.locator("form.edit [data-tq]").count() == 3, "quick target buttons offered (10%, 20%, half original)")
        page.click("form.edit [data-tq='85']"); check(page.input_value("form.edit input[name=target]") == "85", "quick target fills the target field")
        page.fill("form.edit input[name=size]", "XXL"); page.fill("form.edit input[name=target]", "80")
        page.click("form.edit button[type=submit]")
        page.wait_for_function("document.querySelector('#toast').textContent.includes('Saved')")
        it = page.evaluate("window.__fake.state.tables.items.find(i => i.name)")
        check(it["size"] == "XXL" and it["target_price"] == 80 and it["check_requested"] == 1, "edit saved and re-check queued")
        check('size "XXL" not on page' in page.locator(".item", has_text="Nike").text_content(), "warns when size isn't on the page")

        # check now on the zara item
        zara.locator("button[data-act=check]").click()
        page.wait_for_function("document.querySelector('#toast').textContent.includes('Queued')")
        check(page.evaluate("window.__fake.state.tables.items.find(i => !i.name).check_requested") == 1, "check now sets the flag")
        check(zara.locator("button[data-act=check]").is_disabled(), "check now button becomes 'queued'")

        # pause / resume
        zara.locator("button[data-act=toggle]").click(); page.wait_for_function("document.querySelector('#toast').textContent.includes('Paused')")
        check(page.locator(".item.paused").count() == 1, "pause greys the row")
        zara.locator("button[data-act=toggle]").click(); page.wait_for_function("document.querySelector('#toast').textContent.includes('Resumed')")

        # share copies the link
        nike.locator("button[data-act=share]").click()
        page.wait_for_function("document.querySelector('#toast').textContent.includes('copied')")
        check(page.evaluate("navigator.clipboard.readText()") == "https://www.nike.com/t/dunk-low-retro-mens-shoes-76KnBL/DD1391-100", "share copies the product link")

        # exports
        page.click("#acct")
        with page.expect_download() as dl: page.click("#exportCsv")
        csv = open(dl.value.path()).read()
        check(dl.value.suggested_filename.startswith("pricewatch-") and csv.startswith("name,store,url") and "Nike Dunk Low Retro,Nike," in csv and "https://www.zara.com" in csv, "CSV export has header and both items")
        page.click("#acct")
        with page.expect_download() as dl: page.click("#exportJson")
        js = open(dl.value.path()).read()
        check('"price_history"' in js and '"alerts"' in js and '"user_id"' not in js, "JSON export includes history and alerts, omits user id")

        # theme
        page.click("#acct"); page.select_option("#theme", "dark")
        check(page.evaluate("document.documentElement.dataset.theme") == "dark", "theme switch applies")
        page.reload(); page.wait_for_selector(".item")
        check(page.evaluate("document.documentElement.dataset.theme") == "dark" and page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(17, 18, 20)", "theme persists across reload")
        page.screenshot(path=SCR + "/../.smoke-dark.png", full_page=True)
        page.click("#acct"); page.select_option("#theme", ""); page.keyboard.press("Escape")
        check(page.evaluate("document.documentElement.dataset.theme") is None, "theme back to system")

        # pasting several links at once
        page.evaluate("""(() => { const dt = new DataTransfer(); dt.setData("text/plain", "look at these https://www.uniqlo.com/us/en/products/E455365-000?utm_source=x and https://www.endclothing.com/us/nike-air-max-1-cz1145-100.html");
          document.querySelector('#add input[name=url]').dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })); })()""")
        page.wait_for_function("document.querySelectorAll('.item').length === 4")
        urls = [i["url"] for i in page.evaluate("window.__fake.state.tables.items")]
        check("https://www.uniqlo.com/us/en/products/E455365-000" in urls and "https://www.endclothing.com/us/nike-air-max-1-cz1145-100.html" in urls, "pasting two links tracks both (tracking params stripped)")
        page.evaluate("window.__fake.cron((T) => { T.items = T.items.filter((i) => !/uniqlo|endclothing/.test(i.url)); })"); page.reload(); page.wait_for_selector(".item")
        zara = page.locator(".item", has_text="Ribbed Knit Sweater")

        # telegram waiting state
        page.click("#tg [data-tg=on]")
        page.wait_for_selector("#tg .spin")
        check("Waiting for Telegram" in page.text_content("#tg"), "waiting state after connect click")
        page.evaluate("window.__fake.cron((T) => { T.profiles[0].telegram_chat_id = '123'; T.profiles[0].telegram_name = '@sid'; })")
        page.click("#acct"); page.wait_for_selector("#menu:not([hidden])")
        check("2 of 100 tracked" in page.text_content("#menuCount"), "menu shows item count")
        page.click("#tg [data-tg=cancel]"); check(page.is_hidden("#tg .spin"), "cancel returns to connect state")

        # mobile layout
        page.set_viewport_size({"width": 390, "height": 800}); page.reload(); page.wait_for_selector(".item")
        check(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "no horizontal scroll on phone width")
        check("connected as @sid" in (page.click("#acct") or page.text_content("#menuTg")), "menu shows telegram connected name after link")
        check(page.is_hidden("#tg"), "telegram notice hidden once linked")
        page.keyboard.press("Escape")
        page.screenshot(path=SCR + "/../.smoke-mobile.png", full_page=True)

        # delete my data
        page.click("#acct"); page.click("#deleteData")
        page.wait_for_selector("#signin:not([hidden])", timeout=8000)
        check(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "landing page has no horizontal scroll on phone width")
        page.screenshot(path=SCR + "/../.smoke-landing-mobile.png", full_page=True)
        s = page.evaluate("window.__fake.state.tables")
        check(len(s["items"]) == 0 and len(s["price_history"]) == 0 and len(s["profiles"]) == 0, "delete my data clears everything and signs out")

        # remove item after re-sign-in and cap message
        page.evaluate("window.__fake.signIn('sid@example.com')"); page.wait_for_selector("#app:not([hidden])")
        # a link handed over via ?add= (bookmarklet / share sheet) lands in the add field
        page.goto("http://127.0.0.1:8765/?add=https%3A%2F%2Fwww.nike.com%2Ft%2Fair-max-1%2FCZ1145-100%3Futm_source%3Dshare"); page.wait_for_selector("#app:not([hidden])")
        page.wait_for_function("document.querySelector('#add input[name=url]').value.length > 0")
        check(page.input_value("#add input[name=url]") == "https://www.nike.com/t/air-max-1/CZ1145-100?utm_source=share" and page.evaluate("location.search") == "", "?add= prefills the link and cleans the address bar")
        page.fill("#add input[name=url]", "")
        page.evaluate("window.__fake.state.cap = 1; window.__fake.save()")
        page.fill("#add input[name=url]", "https://www.ssense.com/en-us/men/product/x/y/123"); page.click("#add button[type=submit]")
        page.wait_for_selector(".item")
        page.fill("#add input[name=url]", "https://www.uniqlo.com/us/en/products/E455365-000"); page.click("#add button[type=submit]")
        page.wait_for_function("document.querySelector('#toast').textContent.includes('limit')")
        check(True, "cap violation from the database gets a friendly message")
        page.locator(".item button[data-act=remove]").first.click()
        page.wait_for_function("document.querySelector('#toast').textContent.includes('Removed')")
        check(page.evaluate("window.__fake.state.tables.items.length") == 0, "remove deletes the item")
        br.close()
finally:
    srv.terminate()
print("\n%d failure(s)" % len(errors)); sys.exit(1 if errors else 0)
