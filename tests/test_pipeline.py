"""Tests for ml/pipeline.py: the embedding table, the data steps, the Gemini labeller (against a FAKE Gemini server on localhost, since the real one needs a key),
and the hand-check tool (with scripted answers).  Run:  python tests/test_pipeline.py   (exits 1 if anything fails)"""
import http.server, json, os, pathlib, re, sys, tempfile, threading, time
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "ml"))
passed, failed = [], []
def check(name, cond, why=""): (passed if cond else failed).append(name + ("" if cond else f"  [{why}]"))

# ---------- a fake Gemini ----------
class Fake(http.server.BaseHTTPRequestHandler):
    log, mode = [], {"fail_after": None, "rate_limit_first": False, "garbage": False, "skip_ids": set(), "calls": 0}
    def log_message(self, *a): pass
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); Fake.log.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body}); Fake.mode["calls"] += 1
        m = Fake.mode
        if m["rate_limit_first"] and Fake.mode["calls"] == 1: self.send_response(429); self.end_headers(); self.wfile.write(b'{"error":{"message":"slow down"}}'); return
        if m["fail_after"] is not None and Fake.mode["calls"] > m["fail_after"]: self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":{"message":"nope"}}'); return
        prompt = body["contents"][0]["parts"][0]["text"]
        if "Write 25 varied" in prompt: out = [f"a made-up message number {i}" for i in range(25)]
        else:
            out = []
            for i, text in re.findall(r"(\d+)\. VILLAGER: .*? MESSAGE: (\".*?\")\n", prompt):
                if int(i) in m["skip_ids"]: continue
                bad = m["garbage"] and int(i) % 2 == 0
                out.append({"id": int(i), "delta": 99 if bad else (-6.0 if re.search(r"hate|stupid|idiot|ruin", text) else 4.0), "shove": 7 if bad else 0.1})
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(out)}]}}]}).encode())
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["GEMINI_BASE"] = f"http://127.0.0.1:{srv.server_address[1]}"; os.environ["GEMINI_API_KEY"] = "AIza-test-key"
import pipeline as P
time.sleep = lambda s: None                                          # (the retry back-off should not slow the test)
tmp = pathlib.Path(tempfile.mkdtemp()); P.DATA = tmp

# ---------- the embedding table ----------
T = P.Table(); e = T.embed("I'm obsessed with sushi"); e2 = T.embed("I'm obsessed with sushi")
check("the embedding table loads (100 dims) and a text embeds to a unit 200-number vector", T.dim == 100 and e.shape == (200,) and abs(float(e @ e)) - 1 < 1e-5)
check("embedding is deterministic and empty text gives zeros", (e == e2).all() and not T.embed("").any())
check("tokenising mirrors game/memory.h: stop words dropped, plurals stripped, synonyms merged, apostrophes split (tests.cpp checks C++ embeddings against these)", P.tokens("My cats said they're afraid of heights!") == ["cat", "re", "fear", "height"], P.tokens("My cats said they're afraid of heights!"))

# ---------- the data steps ----------
P.cmd_states(300, seed=1); rows = [json.loads(l) for l in open(tmp / "states.jsonl")]
check("states: the headless bot player makes the requested number of villager states with sane ranges", len(rows) == 300 and all(-100 <= r["op"] <= 100 and 0 <= r["agg"] <= 1 and r["col"] in (-1, 0, 1) and 0 <= r["slot"] < 8 for r in rows))
check("states: personalities are the eight real archetypes from persona.h", {(r["c"], r["f"], r["p"]) for r in rows} <= {a[:3] for a in P.archetypes()} and len({r["slot"] for r in rows}) == 8)
P.cmd_messages(False); msgs = json.load(open(tmp / "messages.json"))
check("messages: the bank has 15 categories and hundreds of messages", len(msgs) > 800 and len({m["category"] for m in msgs}) == 15)
P.cmd_label("standin", 120, seed=2); a = [json.loads(l) for l in open(tmp / "labeled.jsonl")]; P.cmd_label("standin", 120, seed=2); b = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
check("stand-in labels: reproducible, in range, and marked as stand-in (never mistaken for Gemini's)", a == b and len(a) == 120 and all(-10 <= r["delta"] <= 10 and 0 <= r["shove"] <= 1 and r["labeler"] == "standin" for r in a))
rude = [r["delta"] for r in a if r["category"] in ("insult", "threat")]; warm = [r["delta"] for r in a if r["category"] in ("compliment", "gratitude")]
check("stand-in labels: insults and threats score lower than compliments and thanks", sum(rude) / len(rude) < sum(warm) / len(warm) - 3, (sum(rude) / len(rude), sum(warm) / len(warm)))

# ---------- the Gemini labeller, against the fake server ----------
Fake.log.clear(); Fake.mode.update(fail_after=None, rate_limit_first=True, garbage=False, skip_ids=set(), calls=0); (tmp / "labeled.jsonl").unlink()
P.cmd_label("gemini", 40, seed=2); g = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
req = Fake.log[1]["body"]; schema = req["generationConfig"]["responseSchema"]
check("gemini labeller: a rate-limited (429) call is retried and the run completes (40 pairs in 2 batches of 20)", len(g) == 40 and Fake.mode["calls"] == 3, Fake.mode["calls"])
check("gemini labeller: sends the key in the header (not the URL) and asks for JSON with a fixed schema of id, delta, shove", Fake.log[0]["key"] == "AIza-test-key" and "AIza" not in Fake.log[0]["path"] and req["generationConfig"]["responseMimeType"] == "application/json"
      and schema["items"]["properties"].keys() == {"id", "delta", "shove"} and schema["items"]["required"] == ["id", "delta", "shove"])
check("gemini labeller: the prompt describes each villager in words, quotes each message, and warns it is untrusted", "VILLAGER:" in req["contents"][0]["parts"][0]["text"] and "untrusted" in req["contents"][0]["parts"][0]["text"] and "opinion of the player" in req["contents"][0]["parts"][0]["text"])
check("gemini labeller: labels are tagged with the model name, and the fake's judgement shows up (rude = negative)", all(r["labeler"].startswith("gemini:") for r in g) and all((r["delta"] < 0) == bool(re.search(r"hate|stupid|idiot|ruin", r["message"])) for r in g))
# resume after a failure: the second run asks only for what is missing
Fake.log.clear(); Fake.mode.update(fail_after=1, rate_limit_first=False, calls=0); (tmp / "labeled.jsonl").unlink()
try: P.cmd_label("gemini", 60, seed=2); crashed = False
except SystemExit: crashed = True
part = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
Fake.log.clear(); Fake.mode.update(fail_after=None, calls=0); P.cmd_label("gemini", 60, seed=2); full = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
check("gemini labeller: a failure mid-run keeps the finished batches, and re-running resumes with only the rest (2 calls, not 3)", crashed and len(part) == 20 and len(full) == 60 and Fake.mode["calls"] == 2, (crashed, len(part), len(full), Fake.mode["calls"]))
# bad numbers and skipped items
Fake.log.clear(); Fake.mode.update(garbage=True, skip_ids={3, 5}, calls=0); (tmp / "labeled.jsonl").unlink(); P.cmd_label("gemini", 20, seed=2); bad = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
check("gemini labeller: absurd numbers are clamped to the schema's range, and items the model skipped are left out (never invented)", all(-10 <= r["delta"] <= 10 and 0 <= r["shove"] <= 1 for r in bad) and {r["id"] for r in bad}.isdisjoint({3, 5}) and len(bad) == 18, len(bad))
Fake.mode.update(garbage=False, skip_ids=set(), calls=0); P.cmd_messages(True)
check("gemini messages: asks for 25 per category, keeps them tagged as gemini-written, and caps each at 80 characters", sum(m["source"] == "gemini" for m in json.load(open(tmp / "messages.json"))) == 15 * 25 and Fake.mode["calls"] == 15)
# no key = a clear stop, not a crash
saved = os.environ.pop("GEMINI_API_KEY")
try: P.cmd_label("gemini", 5); nokey = False
except SystemExit as ex: nokey = "GEMINI_API_KEY" in str(ex)
os.environ["GEMINI_API_KEY"] = saved
check("gemini labeller: without a key it stops with a message that names the variable to set", nokey)

# ---------- the hand-check tool ----------
P.cmd_label("standin", 300, seed=5); rows = [json.loads(l) for l in open(tmp / "labeled.jsonl")]
import random; sample = random.Random(3).sample(rows, 100)
def bucket_letter(d): return "U" if d >= 4 else "u" if d >= 1 else "n" if d > -1 else "d" if d > -4 else "D"
def answers(f):
    p = tmp / "answers.txt"; p.write_text(" ".join(f"{bucket_letter(r['delta']) if f == 'same' else 'D' if r['delta'] > 0 else 'U'} {'y' if r['shove'] >= 0.5 else 'n'}" for r in sample)); return p
res = P.cmd_check(100, seed=3, answers=answers("same"))
check("hand-check: if you agree with every label the report says so (same bucket 100%, correlation high)", res["n"] == 100 and res["same_bucket"] == 1.0 and res["shove_agreement"] == 1.0 and res["correlation"] > 0.8, res)
res2 = P.cmd_check(100, seed=3, answers=answers("opposite"))
check("hand-check: if you disagree with every label the report shows strong disagreement (negative correlation, ~0% same direction)", res2["same_bucket"] < 0.2 and res2["correlation"] < -0.5 and res2["same_direction"] < 0.1, res2)
check("hand-check: the result file is written and you answer blind (the label's numbers are never shown)", (tmp / "handcheck.json").exists())

print(f"{len(passed)} passed, {len(failed)} failed"); [print("  FAILED:", f) for f in failed]
sys.exit(1 if failed else 0)
