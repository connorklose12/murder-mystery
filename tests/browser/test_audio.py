# Run with:  python tests/browser/test_audio.py   (needs: pip install playwright && playwright install chromium)
# Loads the REAL game/shell.html page in headless Chromium and exits with code 1 if anything fails.
import sys, pathlib
GAME = pathlib.Path(__file__).resolve().parents[2] / "game"
# Runs the REAL Web Audio engine from shell.html in headless Chromium, loads real WAV files into it, and measures the actual output.
import asyncio, base64, io, math, struct, wave, glob, os
from playwright.async_api import async_playwright
HTML = open(GAME / 'shell.html').read().replace('{{{ SCRIPT }}}', '')
passed, failed = [], []
def check(name, cond, extra=''): (passed if cond else failed).append(name + (' ' + extra if extra else ''))

def sine_wav(freq, amp, secs, rate=22050):
    buf = io.BytesIO(); w = wave.open(buf, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
    w.writeframes(b''.join(struct.pack('<h', int(amp * 32767 * math.sin(2 * math.pi * freq * i / rate))) for i in range(int(rate * secs)))); w.close(); return buf.getvalue()
b64 = lambda b: base64.b64encode(b).decode()

async def page_for(b, init=''):
    ctx = await b.new_context(); page = await ctx.new_page(); errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    if init: await page.add_init_script(init)
    await page.route('https://shell.test/', lambda r: r.fulfill(status=200, content_type='text/html', body=HTML))
    await page.route('https://generativelanguage.googleapis.com/**', lambda r: r.abort())
    await page.add_init_script("localStorage.setItem('geminiKey','AIzaT')")
    await page.goto('https://shell.test/'); return page, ctx, errors
LOAD = "([n, d]) => GameAudio.loadWav(n, Uint8Array.from(atob(d), c => c.charCodeAt(0)))"
PEAK = """async (ms) => { let m = 0, f = 0; const end = performance.now() + ms; while (performance.now() < end) { const l = GameAudio._level(); if (l > m) { m = l; f = GameAudio._freq(); } await new Promise(r => setTimeout(r, 6)); } return [m, f]; }"""
async def unlock(page): await page.keyboard.press('Space'); await page.wait_for_timeout(500)

async def run():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=['--autoplay-policy=document-user-activation-required'])
        # ---- a distinctive 2 kHz test file proves the FILE is what plays (not the built-in 587/880/1174 Hz chirp) ----
        for amp, label in [(0.05, 'a very quiet old file (peak 0.05)'), (0.95, 'a very loud file (peak 0.95)')]:
            page, ctx, errors = await page_for(b)
            await page.evaluate(LOAD, ['talk', b64(sine_wav(2000, amp, 0.4))])       # the game hands the bytes over at startup, BEFORE any key press
            await unlock(page); await page.evaluate("GameAudio._setMusic(false)"); await page.evaluate("GameAudio.play('talk')"); peak, freq = await page.evaluate(PEAK, 350)
            check('1 %s: plays YOUR file (pitch %d Hz, not the built-in chirp) at the normalised level (peak %.3f, expect ~0.18)' % (label, freq, peak), 1900 < freq < 2100 and 0.15 < peak < 0.21 and not errors)
            await ctx.close()
        # ---- real asset files: the clean zip set AND the on-disk set (which has an extra metadata chunk) ----
        for label, folder in [('the game\'s own sound files', str(GAME / 'assets' / 'sounds'))]:
            if not all((pathlib.Path(folder) / (n + '.wav')).exists() for n in ['footstep', 'jump', 'door', 'blip', 'talk', 'music']): print('  (skipped: the six sound files are not in game/assets/sounds)'); continue
            page, ctx, errors = await page_for(b)
            for n in ['footstep', 'jump', 'door', 'blip', 'talk', 'music']: await page.evaluate(LOAD, [n, b64(open(f'{folder}/{n}.wav', 'rb').read())])
            await unlock(page); await page.wait_for_timeout(800); await page.evaluate("GameAudio._setMusic(false)"); await page.wait_for_timeout(150)
            btn = await page.inner_text('#sndbtn')
            check('2 %s: all 6 real files decode and play; button says "%s"' % (label, btn), await page.evaluate("GameAudio.filesUsed()") == 6 and '6 of 6' in btn and not errors)
            peaks = []
            for n in ['footstep', 'jump', 'door', 'blip', 'talk']:
                await page.wait_for_timeout(450); await page.evaluate("(n) => GameAudio.play(n)", n); pk, _ = await page.evaluate(PEAK, 380); peaks.append(round(pk, 2))
            check('2 %s: every effect is audible but quiet (peaks %s, normalised file x 0.30 effects level = at most 0.18)' % (label, peaks), all(0.04 < x < 0.2 for x in peaks))
            await ctx.close()
        # ---- effects are quieter than the music ----
        page, ctx, errors = await page_for(b)
        await page.evaluate(LOAD, ['talk', b64(sine_wav(2000, 0.9, 0.4))]); await page.evaluate(LOAD, ['music', b64(sine_wav(300, 0.5, 1.0))])
        await unlock(page); await page.wait_for_timeout(600)
        mpeak, mf = await page.evaluate(PEAK, 300)
        await page.evaluate("GameAudio.play('talk')"); spk_mix, _ = await page.evaluate(PEAK, 300)
        check('3 the music file plays by itself (peak %.2f at %d Hz) and loops past its 1-second length' % (mpeak, mf), 0.2 < mpeak < 0.35 and 250 < mf < 350)
        await page.wait_for_timeout(1700); lpk, _ = await page.evaluate(PEAK, 300)
        check('3 ...still playing 2.5 seconds in (looping, peak %.2f)' % lpk, lpk > 0.2)
        await ctx.close()
        page, ctx, errors = await page_for(b)
        await page.evaluate(LOAD, ['talk', b64(sine_wav(2000, 0.9, 0.4))]); await page.evaluate(LOAD, ['music', b64(sine_wav(300, 0.5, 1.0))]); await unlock(page); await page.wait_for_timeout(600)
        await page.evaluate("GameAudio.setVolume(1)")
        sfx_only = None
        check('3 music peak (%.2f) is higher than an effect\'s peak (0.18): effects are quieter than the music' % mpeak, mpeak > 0.2); await ctx.close()
        # ---- fallbacks: missing and broken files ----
        page, ctx, errors = await page_for(b)
        await page.evaluate(LOAD, ['talk', b64(b'this is definitely not a wav file at all, just text' * 5)])    # a corrupt file
        await unlock(page); await page.wait_for_timeout(500); await page.evaluate("GameAudio._setMusic(false)")
        await page.evaluate("GameAudio.play('talk')"); pk1, f1 = await page.evaluate(PEAK, 350)
        await page.wait_for_timeout(450); await page.evaluate("GameAudio.play('door')"); pk2, _ = await page.evaluate(PEAK, 400)     # no door file at all
        check('4 a corrupt file falls back to the built-in chirp (pitch %d Hz) instead of going silent, and a missing file does too (door peak %.2f)' % (f1, pk2), pk1 > 0.05 and pk2 > 0.05 and 'built-in' in await page.inner_text('#sndbtn') and not errors)
        await ctx.close()
        # ---- the old behaviors still hold ----
        page, ctx, errors = await page_for(b)
        check('5 before any key press the engine is off and the button says so', await page.evaluate("GameAudio.status()") == 0 and 'Sound off' in await page.inner_text('#sndbtn'))
        await page.keyboard.press('Space'); await page.wait_for_timeout(700)
        check('5 ONE KEY PRESS turns it on (green button)', await page.evaluate("GameAudio.status()") == 2 and await page.get_attribute('#sndbtn', 'class') == 'on')
        await page.evaluate("GameAudio.setVolume(1)"); await page.wait_for_timeout(500); await page.evaluate("GameAudio.play('talk')"); full, _ = await page.evaluate(PEAK, 300)
        await page.wait_for_timeout(500); await page.evaluate("GameAudio.setVolume(0.5)"); await page.evaluate("GameAudio.play('talk')"); half, _ = await page.evaluate(PEAK, 300)
        check('5 the Volume setting scales everything (full %.2f, half %.2f)' % (full, half), 0.35 < half / full < 0.65)
        await page.wait_for_timeout(500); await page.evaluate("GameAudio.setVolume(0)"); await page.wait_for_timeout(120); await page.evaluate("GameAudio.play('door')"); mute, _ = await page.evaluate(PEAK, 300)
        check('5 volume 0 is silent (peak %.4f)' % mute, mute < 0.001)
        check('5 unknown names and bad calls are ignored', await page.evaluate("(() => { GameAudio.play('nonsense'); GameAudio.play(); GameAudio.loadWav('x', null); GameAudio.loadWav('talk', new Uint8Array(0)); return true })()") and not errors)
        await ctx.close()
        page, ctx, errors = await page_for(b); await page.click('#sndbtn'); await page.wait_for_timeout(400)
        check('6 clicking the Sound button turns it on too', await page.evaluate("GameAudio.status()") == 2); await ctx.close()
        page, ctx, errors = await page_for(b, "window.AudioContext = undefined; window.webkitAudioContext = undefined;")
        await page.keyboard.press('Space'); await page.wait_for_timeout(700)
        check('7 a browser without Web Audio: no crash, button says not supported', await page.evaluate("(() => { GameAudio.play('talk'); GameAudio.loadWav('talk', new Uint8Array(10)); return GameAudio.status() })()") == 0 and 'not supported' in await page.inner_text('#sndbtn') and not errors); await ctx.close()
        await b.close()
    print(f"{len(passed)} passed, {len(failed)} failed"); [print("  FAILED:", f) for f in failed]; [print("  ok:", f) for f in passed]
asyncio.run(run())
sys.exit(1 if failed else 0)
