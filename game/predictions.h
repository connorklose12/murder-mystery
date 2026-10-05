// "Who dies next?": after each death you guess who will be killed next, and the game keeps score of how many deaths you called right.
// (No raylib here, so tests.cpp can run it.)
#pragma once
#include <string>

struct Predictions {
    int right = 0, total = 0;   // deaths you guessed right / deaths so far (a death you made no guess for counts as a miss)
    int guess = -1;             // who you think dies next (-1 = no guess). Once you pick, it is locked until someone dies.
    int scanned = 0;            // how many events the game has already looked through for deaths, so each death is scored exactly once
    int simRight = 0;           // how many deaths the top of the "most likely to die next" list called right (it plays the same game as you)
    int simGuess = -1;          // the simulation's top pick for the next death (-1 = it had no pick)

    bool Pick(int who) {        // lock in a guess. Returns false (and changes nothing) if you already have one.
        if (guess >= 0) return false;
        guess = who; return true;
    }
    void Death(int victim) {    // someone just died: score your guess and the simulation's, then both are cleared for the next round
        total++;
        if (guess == victim) right++;
        if (simGuess == victim) simRight++;
        guess = simGuess = -1;
    }
    std::string Label() const { return std::to_string(right) + "/" + std::to_string(total) + " deaths predicted correct"; }
    std::string SimLabel() const { return "Top of the list: " + std::to_string(simRight) + "/" + std::to_string(total); }   // how often the top of the "most likely to die next" list was right
};