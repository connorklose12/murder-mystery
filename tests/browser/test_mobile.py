# Run with:  python tests/browser/test_mobile.py   (needs: pip install playwright && playwright install chromium)
# Loads the REAL game/shell.html page in headless Chromium and exits with code 1 if anything fails.
import sys, pathlib
GAME = pathlib.Path(__file__).resolve().parents[2] / "game"
# Tests the page on emulated phones (landscape + portrait) and a desktop, using the real shell.html
import asyncio, json, math
from playwright.async_api import async_playwright
HTML = open(GAME / 'shell.html').read().replace('{{{ SCRIPT }}}', '')
passed, failed = [], []
def check(name, cond, why=''): (passed if cond else failed).append(name + ((' [' + str(why) + ']') if (why and not cond) else ''))
BUTTONS = ['up', 'down', 'left', 'right', 'action', 'swing', 'guess', 'save', 'back', 'lookL', 'lookR', 'zoomIn', 'zoomOut']

async def page_for(b, w, h, mobile, path=''):
    ctx = await b.new_context(viewport={'width': w, 'height': h}, has_touch=mobile, is_mobile=mobile, device_scale_factor=2 if mobile else 1)
    page = await ctx.new_page(); errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    await page.route('https://shell.test/**', lambda r: r.fulfill(status=200, content_type='text/html', body=HTML))
    await page.route('https://generativelanguage.googleapis.com/**', lambda r: r.abort())
    await page.goto('https://shell.test/' + path)
    await page.evaluate("document.getElementById('buildinfo').textContent = 'build Oct  3 2026 14:30:00'")   # (the game fills this in at startup)
    # what raylib does at startup: the canvas is 960x540; paint it so screenshots show the game area
    await page.evaluate("() => { const c = document.getElementById('canvas'); c.width = 960; c.height = 540; const g = c.getContext('2d'); const gr = g.createLinearGradient(0,0,0,540); gr.addColorStop(0,'#5a3a8a'); gr.addColorStop(1,'#2a6a3a'); g.fillStyle = gr; g.fillRect(0,0,960,540); g.fillStyle='#fff'; g.font='24px sans-serif'; g.fillText('game picture 960x540', 330, 270); g.strokeStyle='#fff'; g.strokeRect(2,2,956,536); }")
    return page, ctx, errors

async def boxes(page, ids):
    return await page.evaluate("(ids) => Object.fromEntries(ids.map(i => { const r = document.getElementById(i).getBoundingClientRect(); return [i, [r.left, r.top, r.right, r.bottom]]; }))", ids)
def overlap(a, b): return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

async def layout_checks(page, label, portrait):
    vw, vh = await page.evaluate("[innerWidth, innerHeight]")
    bx = await boxes(page, BUTTONS + ['sndbtn', 'keybtn', 'keylink', 'canvas'])
    inside = all(b[0] >= 0 and b[1] >= 0 and b[2] <= vw and b[3] <= vh for k, b in bx.items() if k != 'canvas')
    check(f'{label}: every button is fully on screen', inside, {k: b for k, b in bx.items() if not (b[0] >= 0 and b[1] >= 0 and b[2] <= vw and b[3] <= vh) and k != 'canvas'})
    small = [k for k in BUTTONS if min(bx[k][2] - bx[k][0], bx[k][3] - bx[k][1]) < 38]
    check(f'{label}: every button is big enough to tap (>= 38 px)', not small, small)
    names = BUTTONS + ['sndbtn', 'keybtn', 'keylink']
    clash = [(a, c) for i, a in enumerate(names) for c in names[i + 1:] if overlap(bx[a], bx[c])]
    check(f'{label}: no two buttons overlap', not clash, clash)
    sw = await page.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight, innerWidth, innerHeight]")
    check(f'{label}: the page does not scroll or zoom sideways', sw[0] <= sw[2] and sw[1] <= sw[3], sw)
    tb = await boxes(page, ['keybtn', 'sndbtn', 'keylink', 'canvas'])
    one_line = max(tb[k][3] - tb[k][1] for k in ['keybtn', 'sndbtn', 'keylink']) < 32 and len({round(tb[k][1]) for k in ['keybtn', 'sndbtn', 'keylink']}) <= 2
    check(f'{label}: the top strip (API key, sound, link) is one short line', one_line, {k: tb[k] for k in ['keybtn', 'sndbtn', 'keylink']})
    if portrait: check(f'{label}: the strip sits below the game, not over its corner', all(tb[k][1] >= tb['canvas'][3] - 1 for k in ['keybtn', 'sndbtn', 'keylink']))
    else: check(f'{label}: the strip is within the top 30 px, clear of the right-hand HUD corner', all(tb[k][1] < 30 for k in ['keybtn', 'sndbtn', 'keylink']) and tb['keylink'][2] < vw * 0.78, {k: tb[k] for k in ['keybtn', 'sndbtn', 'keylink']})
    if portrait:
        hb = await boxes(page, ['rotate', 'soundhint', 'buildinfo'])
        stack = [hb['rotate'], [0, bx['keybtn'][1], vw, bx['keybtn'][3]], hb['soundhint'], hb['buildinfo']]
        clash2 = [(i, j) for i in range(len(stack)) for j in range(i + 1, len(stack)) if overlap(stack[i], stack[j])]
        check(f'{label}: the hint lines, the strip and the build time stack below the game without touching', not clash2 and await page.is_visible('#soundhint') and await page.is_visible('#buildinfo'), (stack, clash2))
        nb = [k for k in BUTTONS if any(overlap(bx[k], h) for h in (hb['rotate'], hb['soundhint'], hb['buildinfo']))]
        check(f'{label}: no button sits on top of a hint line', not nb, nb)
        cv = bx['canvas']
        check(f'{label}: the game fills the screen width and the buttons are below it', abs((cv[2] - cv[0]) - vw) < 2 and all(bx[k][1] >= cv[3] - 1 for k in BUTTONS), (cv, {k: bx[k][1] for k in BUTTONS if bx[k][1] < cv[3] - 1}))
        check(f'{label}: the "turn your phone sideways" hint is visible', await page.is_visible('#rotate'))
    else:
        cv = bx['canvas']
        if vh <= 300:
            pw_ = vh * 16 / 9; px0, px1 = (vw - pw_) / 2, (vw + pw_) / 2
            cover = [k for k in BUTTONS if bx[k][0] < px1 - 0.5 and bx[k][2] > px0 + 0.5 and bx[k][1] < vh]
            check(f'{label}: every control sits in the black side bars (picture is x {px0:.0f}..{px1:.0f}), none covers the game', not cover, {k: bx[k] for k in cover})
        check(f'{label}: the game fills the whole screen', abs((cv[2] - cv[0]) - vw) < 2 and abs((cv[3] - cv[1]) - vh) < 2)
        check(f'{label}: no rotate hint in landscape', not await page.is_visible('#rotate'))

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        # ---------- desktop is unchanged ----------
        page, ctx, errors = await page_for(b, 1280, 720, False)
        check('desktop: no touch buttons and no mobile class', not await page.evaluate("document.body.classList.contains('mobile')") and not await page.is_visible('#action'))
        tb = await boxes(page, ['sndbtn', 'keybtn']); check('desktop: the sound/API-key buttons stay in the top-right corner', tb['keybtn'][2] > 1260 and tb['keybtn'][1] < 20 and tb['sndbtn'][1] > tb['keybtn'][1] - 1)
        check('desktop: ?mobile=1 can force the touch layout (for testing)', True); await ctx.close()
        page, ctx, errors = await page_for(b, 1280, 720, False, '?mobile=1'); check('desktop with ?mobile=1: touch buttons appear', await page.is_visible('#action')); await ctx.close()
        # ---------- phones ----------
        for label, w, h in [('iPhone landscape, toolbars showing 844x280', 844, 280), ('iPhone landscape, full screen 852x393', 852, 393), ('phone landscape 844x390', 844, 390), ('small phone landscape 667x375', 667, 375), ('wide phone landscape 932x430', 932, 430), ('tablet landscape 1024x768', 1024, 768)]:
            page, ctx, errors = await page_for(b, w, h, True)
            check(f'{label}: detected as a touch device by itself (no ?mobile=1 needed)', await page.evaluate("Mobile.on") and await page.is_visible('#action'))
            await layout_checks(page, label, False)
            await ctx.close()
        for label, w, h in [('iPhone portrait, toolbars showing 393x659', 393, 659), ('phone portrait 390x844', 390, 844), ('small phone portrait 360x640', 360, 640)]:
            page, ctx, errors = await page_for(b, w, h, True); await layout_checks(page, label, True)
            await ctx.close()
        # ---------- the buttons press real keys ----------
        page, ctx, errors = await page_for(b, 844, 390, True)
        await page.evaluate("() => { window.log = []; for (const t of ['keydown','keyup']) addEventListener(t, e => log.push([t, e.code, e.keyCode, e.which, performance.now()])); }")
        async def center(i): bb = (await boxes(page, [i]))[i]; return (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        for bid, code, kc in [('action', 'Space', 32), ('swing', 'KeyF', 70), ('guess', 'KeyG', 71), ('save', 'KeyP', 80), ('back', 'Escape', 27), ('up', 'ArrowUp', 38), ('left', 'ArrowLeft', 37), ('lookL', 'KeyQ', 81), ('zoomIn', 'KeyZ', 90)]:
            await page.evaluate("log.length = 0"); x, y = await center(bid); await page.touchscreen.tap(x, y); await page.wait_for_timeout(200)
            lg = await page.evaluate("log")
            ok = len(lg) == 2 and lg[0][0] == 'keydown' and lg[1][0] == 'keyup' and lg[0][1] == code and lg[0][2] == kc and lg[0][3] == kc
            check(f'buttons: "{bid}" sends {code} with keyCode {kc} (down then up)', ok, lg)
        await page.evaluate("log.length = 0"); x, y = await center('action'); await page.touchscreen.tap(x, y); await page.wait_for_timeout(200)
        lg = await page.evaluate("log"); check('buttons: even an instant tap is held >= 60 ms so the game cannot miss it (%.0f ms)' % (lg[1][4] - lg[0][4]), len(lg) == 2 and lg[1][4] - lg[0][4] >= 60)
        # two fingers at once: walk (up) and attack (swing) together, release them independently
        await page.evaluate("log.length = 0"); ux, uy = await center('up'); sx, sy = await center('swing')
        cdp = await ctx.new_cdp_session(page)
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': ux, 'y': uy, 'id': 1}, {'x': sx, 'y': sy, 'id': 2}]}); await page.wait_for_timeout(150)
        held = await page.evaluate("log.filter(l => l[0]==='keydown').map(l => l[1])")
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': [{'x': sx, 'y': sy, 'id': 2}]}); await page.wait_for_timeout(200)
        ups1 = await page.evaluate("log.filter(l => l[0]==='keyup').map(l => l[1])")
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); await page.wait_for_timeout(200)
        ups2 = await page.evaluate("log.filter(l => l[0]==='keyup').map(l => l[1])")
        check('buttons: two fingers at once press both keys, and each releases on its own', sorted(held) == ['ArrowUp', 'KeyF'] and ups1 == ['KeyF'] and sorted(ups2) == ['ArrowUp', 'KeyF'], (held, ups1, ups2))
        # a button that is held while the finger slides off is still released
        await page.evaluate("log.length = 0")
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': ux, 'y': uy, 'id': 1}]}); await page.wait_for_timeout(100)
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': 400, 'y': 200, 'id': 1}]}); await page.wait_for_timeout(100)
        await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); await page.wait_for_timeout(200)
        lg = await page.evaluate("log.map(l => l[0] + ':' + l[1])"); check('buttons: sliding the finger off a held button still releases the key (no stuck walking)', lg == ['keydown:ArrowUp', 'keyup:ArrowUp'], lg)
        check('buttons: no page errors', not errors, errors)
        # ---------- taps on the game become game coordinates ----------
        async def tap_at(x, y): await page.evaluate("Mobile.takeTap()"); await page.touchscreen.tap(x, y); await page.wait_for_timeout(120); v = await page.evaluate("Mobile.takeTap()"); return None if v < 0 else (v >> 10, v & 1023)
        r = await page.evaluate("(() => { const r = document.getElementById('canvas').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        s = min(r[2] / 960, r[3] / 540); ox, oy = r[0] + (r[2] - 960 * s) / 2, r[1] + (r[3] - 540 * s) / 2
        errs = []
        for gx, gy in [(480, 270), (100, 100), (900, 500), (10, 10), (700, 300)]:
            got = await tap_at(ox + gx * s, oy + gy * s)
            if got is None or abs(got[0] - gx) > 2 or abs(got[1] - gy) > 2: errs.append(((gx, gy), got))
        check('taps: a tap lands on the right game pixel (scale %.2f, offset %.0f,%.0f)' % (s, ox, oy), not errs, errs)
        check('taps: a tap in the black bar outside the picture is ignored', await tap_at(ox - 10, oy + 100) is None if ox > 12 else True)
        check('taps: a second takeTap() with no new tap gives nothing (each tap is delivered once)', await page.evaluate("Mobile.takeTap()") == -1)
        # swipe vs tap
        async def swipe(x0, y0, x1, y1):
            await page.evaluate("Mobile.takeTap(); Mobile.takeDrag();")
            await cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x0, 'y': y0, 'id': 1}]})
            for k in range(1, 9): await cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x0 + (x1 - x0) * k / 8, 'y': y0 + (y1 - y0) * k / 8, 'id': 1}]})
            await cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []}); await page.wait_for_timeout(100)
            return await page.evaluate("[Mobile.takeDrag(), Mobile.takeTap()]")
        d, t = await swipe(ox + 300 * s, oy + 200 * s, ox + 300 * s + 120, oy + 200 * s)
        check('swipe: a 120 px finger swipe turns the camera by ~%.0f game pixels and is NOT a tap (got %.0f, tap %s)' % (120 / s, d, t), abs(d - 120 / s) < 8 and t == -1)
        d, t = await swipe(ox + 300 * s, oy + 200 * s, ox + 300 * s + 5, oy + 200 * s + 3)
        check('swipe: a tiny wobble is a tap, not a camera turn (drag %.1f, tap %s)' % (d, t), abs(d) < 6 and t != -1)
        # ---------- menus hide the walking buttons ----------
        await page.evaluate("Mobile.mode(1)")
        vis = await page.evaluate("Object.fromEntries(['up','down','swing','back','action','guess'].map(i => [i, getComputedStyle(document.getElementById(i)).visibility]))")
        lab = await page.evaluate("[getComputedStyle(document.querySelector('#action .ok')).display, getComputedStyle(document.querySelector('#action .walk')).display]")
        check('menu mode: Up/Down and Back stay (the sure way to pick), Attack and Guess hide, and the big button says OK', vis['up'] == vis['down'] == vis['back'] == vis['action'] == 'visible' and vis['swing'] == vis['guess'] == 'hidden' and lab[0] != 'none' and lab[1] == 'none', (vis, lab))
        await page.evaluate("Mobile.mode(0)")
        check('play mode: Attack and Guess come back and the big button says Jump / Talk', await page.evaluate("getComputedStyle(document.getElementById('swing')).visibility") == 'visible' and await page.evaluate("getComputedStyle(document.querySelector('#action .ok')).display") == 'none')
        fitv = await page.evaluate("[document.documentElement.style.getPropertyValue('--app-h'), innerHeight + 'px', document.documentElement.style.getPropertyValue('--game-h'), Math.round(innerWidth * 9 / 16) + 'px']")
        check('page: the visible height is measured (not guessed from 100vh) and re-measured on resize', fitv[0] == fitv[1] and fitv[2] == fitv[3], fitv)
        await page.set_viewport_size({'width': 700, 'height': 300}); await page.wait_for_timeout(200)
        check('page: after the phone is turned, --app-h follows the new height', await page.evaluate("document.documentElement.style.getPropertyValue('--app-h')") == '300px')
        await page.set_viewport_size({'width': 844, 'height': 390}); await page.wait_for_timeout(100)
        # ---------- typing a name uses the phone's text box ----------
        async def ask(answer):
            async def h(d): await (d.accept(answer) if answer is not None else d.dismiss())
            page.once('dialog', h); return await page.evaluate("Mobile.askText('What is your name?')")
        check('name box: the typed name comes back', await ask('Zed') == 'Zed'); check('name box: cancelling gives null', await ask(None) is None)
        meta = await page.evaluate("document.querySelector('meta[name=viewport]').content"); check('page: has a mobile viewport that stops pinch-zoom', 'width=device-width' in meta and 'user-scalable=no' in meta)
        # ---------- iPhone sound: the silent switch ----------
        iphone = p.devices['iPhone 15']
        for label, dev, expect_silent in [('an iPhone', iphone, True), ('an Android phone', {'viewport': {'width': 844, 'height': 390}, 'has_touch': True, 'is_mobile': True, 'device_scale_factor': 2, 'user_agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36'}, False)]:
            ctx2 = await b.new_context(**dev); pg = await ctx2.new_page(); errs = []
            pg.on('pageerror', lambda e: errs.append(str(e)))
            await pg.add_init_script("""window.__plays = []; const o = HTMLMediaElement.prototype.play;
                HTMLMediaElement.prototype.play = function () { __plays.push({ loop: this.loop, blob: this.src.startsWith('blob:'), inline: this.hasAttribute('playsinline') }); return o.apply(this, arguments); };
                Object.defineProperty(navigator, 'audioSession', { value: { type: 'auto' }, configurable: true });""")
            await pg.route('https://shell.test/**', lambda r: r.fulfill(status=200, content_type='text/html', body=HTML)); await pg.route('https://generativelanguage.googleapis.com/**', lambda r: r.abort())
            await pg.goto('https://shell.test/'); await pg.evaluate("() => { const c = document.getElementById('canvas'); c.width = 960; c.height = 540; }")
            before = await pg.evaluate("[__plays.length, navigator.audioSession.type]")
            await pg.touchscreen.tap(300, 200); await pg.wait_for_timeout(500)
            after = await pg.evaluate("[__plays.length, navigator.audioSession.type, __plays[0] || null, GameAudio.status()]")
            if expect_silent: check('iPhone sound: before any tap nothing is set up; the first tap marks the page as "playback" audio and plays a silent looping clip so the silent switch cannot mute the game', before == [0, 'auto'] and after[1] == 'playback' and after[0] >= 1 and after[2] == {'loop': True, 'blob': True, 'inline': True} and after[3] == 2 and not errs, (before, after, errs))
            else: check('Android/desktop: the audio session is set too, but no silent clip is played (not needed there)', after[1] == 'playback' and after[0] == 0 and after[3] == 2 and not errs, (before, after, errs))
            await ctx2.close()
        check('iPhone sound: audio is also unlocked by the END of a touch (touchend / pointerup), which is the only kind of touch iOS accepts', "'pointerup', 'mousedown', 'touchstart', 'touchend', 'click'" in HTML)
        # the build time and hints
        page, ctx, errors = await page_for(b, 393, 659, True)
        check('page: has a build-time slot and a "no sound?" hint for phones in portrait', await page.is_visible('#soundhint') and await page.evaluate("!!document.getElementById('buildinfo')")); await ctx.close()
        page, ctx, errors = await page_for(b, 1280, 720, False)
        check('desktop: no sound hint, no touch buttons', not await page.is_visible('#soundhint') and not await page.is_visible('#action')); await ctx.close()
        await b.close()
    print(f"{len(passed)} passed, {len(failed)} failed"); [print("  FAILED:", f) for f in failed]
asyncio.run(run())
sys.exit(1 if failed else 0)
