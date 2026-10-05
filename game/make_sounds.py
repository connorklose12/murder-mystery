# Generates the game's sound effects (no copyrighted material, all synthesized) at proper loudness.
# Run:  python make_sounds.py   
import numpy as np, wave, sys, os
SR = 22050
rng = np.random.default_rng(7)
def t(sec): return np.arange(int(SR * sec)) / SR
def env(n, attack=0.005, decay=6.0):                    # fast attack, exponential decay
    x = np.arange(n) / SR
    e = np.exp(-decay * x); a = int(attack * SR)
    if a > 0: e[:a] *= np.linspace(0, 1, a)
    return e
def tone(freq, sec, harmonics=((1, 1.0), (2, 0.25), (3, 0.08)), decay=7.0):
    x = t(sec); y = sum(a * np.sin(2 * np.pi * freq * h * x) for h, a in harmonics)
    return y * env(len(x), decay=decay)
def lowpass(x, k): 
    out = np.cumsum(np.insert(x, 0, 0)); return (out[k:] - out[:-k]) / k
def norm(x, peak): return (x / (np.max(np.abs(x)) + 1e-9) * peak).astype(np.float32)
def save(name, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype('<i2')
    with wave.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), name), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

# talk: a friendly two-note "hello" chirp (rising), ~0.3 s - plays when you start talking to someone
n1 = tone(587.33, 0.11, decay=9); n2 = tone(880.0, 0.20, decay=8)
talk = np.concatenate([n1, n2]); save('talk.wav', norm(talk, 0.9))

# blip: a short, clear UI blip, ~0.1 s
save('blip.wav', norm(tone(1046.5, 0.10, decay=14), 0.8))

# footstep: a soft thud with a little gravel noise, ~0.14 s
x = t(0.14); thud = np.sin(2 * np.pi * (95 - 40 * x) * x) * env(len(x), decay=28)
gravel = lowpass(rng.standard_normal(len(x) + 8), 9)[:len(x)] * env(len(x), attack=0.002, decay=40)
save('footstep.wav', norm(thud * 1.0 + gravel * 0.9, 0.6))

# jump: a quick rising sweep, ~0.22 s
x = t(0.22); f = 280 + 650 * (x / 0.22) ** 1.3; ph = 2 * np.pi * np.cumsum(f) / SR
save('jump.wav', norm(np.sin(ph) * env(len(x), attack=0.004, decay=7) + 0.2 * np.sin(2 * ph), 0.75))

# door: a creak that ends in a thunk, ~0.45 s
x = t(0.45); creak = np.sign(np.sin(2 * np.pi * (110 - 35 * x / 0.45) * x)) * 0.35 * np.sin(np.pi * x / 0.3).clip(0)
xs = t(0.2); thunk = (np.sin(2 * np.pi * 70 * xs) + 0.6 * lowpass(rng.standard_normal(len(xs) + 5), 6)[:len(xs)]) * env(len(xs), decay=18)
door = np.concatenate([creak[:int(0.28 * SR)], np.zeros(0)]); door = np.concatenate([door, thunk])
save('door.wav', norm(door, 0.85))

# music: normalise the existing loop (it was only ~10% of full scale, i.e. almost inaudible)
src = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'music.wav')
if os.path.exists(src):
    with wave.open(src) as w: m = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float32) / 32768
    save('music_norm.tmp', norm(m, 0.5)); os.replace(os.path.join(os.path.dirname(src), 'music_norm.tmp'), src)
print("done")
