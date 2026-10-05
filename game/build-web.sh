#!/bin/sh
# Check everything is in place BEFORE building, so a missing file or a missing Emscripten setup gives a clear message instead of a cryptic error.
for f in main.cpp shell.html social.h jsonutil.h npc_brain.h npc_brain_weights.h dynamics.h persona.h predictions.h memory.h mcts.h dialogue.json config.json assets/embed.bin raylib/include/raylib.h raylib/lib/libraylib.a; do
  [ -e "$f" ] || { echo "BUILD STOPPED: $f is missing from the game folder"; exit 1; }
done
command -v em++ >/dev/null 2>&1 || { echo "BUILD STOPPED: em++ was not found. Set up Emscripten in this shell first (source emsdk_env.sh)."; exit 1; }
mkdir -p ../MyProject/wwwroot
em++ main.cpp -std=c++17 -sALLOW_MEMORY_GROWTH=1 -o ../MyProject/wwwroot/index.html -Os -Iraylib/include -Lraylib/lib -lraylib \
  -sUSE_GLFW=3 -sEXPORTED_RUNTIME_METHODS=stringToUTF8,UTF8ToString \
  --preload-file assets@assets --preload-file config.json@config.json --preload-file dialogue.json@dialogue.json \
  --shell-file shell.html -DPLATFORM_WEB