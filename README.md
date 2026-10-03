# Purple World
(Latest FINALPRODUCTBRANCH is most updated file)
[**Play in Browser**](https://connorklose12.github.io/cppgame/) · [GitHub Repository](https://github.com/connorklose12/cppgame) · [CI Status](https://github.com/connorklose12/cppgame/actions/workflows/ci.yml)

**Technologies:** C++, Python, JavaScript, WebAssembly, Google Gemini, GitHub Actions

A 3D social simulation. With each their own complex AI system, 8 villagers form relationships, spread rumors, remember conversations, and react to the player. Google Gemini generates dynamic dialogue. No backend server is required.

I built the game in C++ and made it playable directly in a web browser. Google Gemini generates unique dialogue, while a small machine learning model helps determine how villagers feel about the player. No backend server is required.

## Gameplay Demo

![Purple World gameplay demo](docs/demo.gif)

## Screenshots

<table>
  <tr>
    <td><img src="docs/game-pic1.jpeg" alt="Purple World gameplay screenshot 1" width="100%"></td>
    <td><img src="docs/game-pic2.jpeg" alt="Purple World gameplay screenshot 2" width="100%"></td>
  </tr>
</table>


## Key Features

* **Living village:** Villagers develop crushes, form relationships, spread rumors, hold grudges, and get into fights.

* **Machine learning:** Trained a small neural network in Python and integrated it into the C++ game. Its test error was 0.50, compared with 1.62 for a linear model.

* **NPC memory:** Villagers can remember information the player tells them and recall it when relevant. In a test of 58 questions, the system recalled every correct answer without any false recalls.

* **AI-generated conversations:** Integrated Google Gemini to generate branching conversations. Added caching to reuse responses, prefetching to reduce waiting, and error handling for failed requests.

* **Browser and mobile support:** Compiled the C++ game to WebAssembly and added touch controls, responsive layouts, and browser audio.

* **Save-file testing:** Built a tool to test how the game handles corrupted save files. Tested 90,000 modified saves using memory and undefined-behavior error detectors, finding and fixing a bug.

## Testing and Deployment

The project has **388 automated checks**, including:

* 169 C++ unit tests

* 201 browser integration tests

* 4 machine learning checks

* 14 dialogue analysis checks

GitHub Actions automatically builds and tests the game. It deploys a new version only when all checks pass.

## Tech Stack

* **Languages:** C++17, Python, JavaScript

* **Game and browser:** raylib, WebAssembly, Emscripten, HTML/CSS

* **AI:** Google Gemini API, neural networks, NPC memory retrieval

* **Testing and deployment:** GitHub Actions, browser testing, fuzzing, AddressSanitizer, UndefinedBehaviorSanitizer

## Run Locally

```bash
git clone https://github.com/connorklose12/cppgame
cd cppgame
python tests/run_all.py
```

To build and play the game locally, see the build instructions in the repository. Playing the browser version requires your own Gemini API key for AI-generated dialogue.

## Limitations

* The dialogue is meant to be genuinely funny, and I avoided having the characters saying things potentially offensive or talk about overly serious topics, but there's no guarantee they won't do that so beware.

* The neural network was trained using simulated data rather than real player behavior.

* The NPC memory test used a small, synthetic dataset, so real-world accuracy may differ.
