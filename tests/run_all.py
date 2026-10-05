"""Runs every test in the project and prints one summary. Used by hand and by CI (.github/workflows/ci.yml).

    python tests/run_all.py            # everything
    python tests/run_all.py --fast     # skip the browser tests (no Playwright needed)

1. C++ unit tests   game/tests.cpp: game logic, parsing, the NPC brain (incl. C++-vs-Python parity), retrieval memory benchmark
2. ML pipeline      ml/pipeline.py train --quick, and tests/test_pipeline.py (a fake Gemini server, hand-checking, data steps)
3. Browser tests    tests/browser/*.py: the real web page in headless Chromium (AI client, audio engine, mobile layout and touch)
"""
import subprocess, sys, pathlib, shutil, tempfile, os
ROOT = pathlib.Path(__file__).resolve().parents[1]
fast = "--fast" in sys.argv
results = []

def run(name, cmd, cwd=ROOT):
    print(f"\n=== {name} ===", flush=True)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    tail = [l for l in out.strip().splitlines() if l.strip()][-6:]
    print("\n".join(tail)); results.append((name, r.returncode == 0))
    return r

tmp = tempfile.mkdtemp()
exe = os.path.join(tmp, "tests.exe" if os.name == "nt" else "tests")
build = run("C++ unit tests: compile", ["g++", "-std=c++17", "-Wall", "tests.cpp", "-o", exe], cwd=ROOT / "game")
if build.returncode == 0: run("C++ unit tests: run", [exe], cwd=ROOT / "game")   # (the tests read assets/embed.bin relative to game/)
run("ML pipeline (quick)", [sys.executable, "ml/pipeline.py", "train", "--quick"])
run("Pipeline tests", [sys.executable, "tests/test_pipeline.py"])
if not fast:
    for f in sorted((ROOT / "tests" / "browser").glob("test_*.py")): run(f"Browser tests: {f.stem}", [sys.executable, str(f)])
shutil.rmtree(tmp, ignore_errors=True)

print("\n" + "=" * 52)
for name, ok in results: print(("PASS  " if ok else "FAIL  ") + name)
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} test groups passed")
sys.exit(1 if failed else 0)
