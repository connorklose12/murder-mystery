
#pragma once
#include "npc_brain_weights.h"
#include "memory.h"
#include <cmath>
#include <algorithm>
#include <string>

struct BrainInput {
    float curiosity, friendliness, patience;   // the NPC's personality (0..1 each)
    float opinion;                             // the NPC's current opinion of the player (-100..100)
    float timesTalked;                         // how many times the player has talked to this NPC
    float colorMatch;                          // -1 disliked color, 0 neither, 1 player's favorite color
    float aggression;                          // 0..1, how hostile the player has been acting
    float dayNight;                            // 0 (night) .. 1 (day)
    float response;                            // the tone of the answer-menu choice: +1 friendly .. 0 neutral .. -1 rude (0 for a typed message)
    float msg[MSG_DIM] = {};                   // what the typed message adds (from MessageFeatures); zeros if there is none
};
struct BrainOutput {
    float opinionDelta;   // how much to shift this NPC's opinion after this interaction (-10..10)
    float punchChance;    // 0..1 chance this NPC takes a swing at the player
};

// The message-probe read-out: typed text to MSG_DIM numbers. Zeros if the embedding table is not loaded (the net then simply sees no message).
inline void MessageFeatures(const std::string& text, float out[MSG_DIM]) {
    for (int k = 0; k < MSG_DIM; k++) out[k] = 0.0f;
    if (!SemTable().loaded) return;
    std::vector<float> e = Embed(text);
    if ((int)e.size() != EMB_DIM) return;
    float len2 = 0; for (float v : e) len2 += v * v;
    if (len2 == 0.0f) return;                  
        for (int k = 0; k < MSG_DIM; k++) { float sum = MSG_PROBE_B[k]; for (int i = 0; i < EMB_DIM; i++) sum += e[i] * MSG_PROBE[i][k]; out[k] = sum; }
}

inline BrainOutput RunBrain(const BrainInput& in) {
    float x[BRAIN_INPUTS] = {in.curiosity, in.friendliness, in.patience, in.opinion / 100.0f,
                             in.timesTalked / 20.0f, in.colorMatch, in.aggression, in.dayNight, in.response};
    for (int k = 0; k < MSG_DIM; k++) x[BRAIN_STATE_INPUTS + k] = in.msg[k];

    float hidden[HIDDEN_SIZE];
    for (int j = 0; j < HIDDEN_SIZE; j++) {
        float sum = B1[j];
        for (int i = 0; i < BRAIN_INPUTS; i++) sum += x[i] * W1[i][j];
        hidden[j] = tanhf(sum);
    }

    float out[2];
    for (int k = 0; k < 2; k++) {
        float sum = B2[k];
        for (int j = 0; j < HIDDEN_SIZE; j++) sum += hidden[j] * W2[j][k];
        out[k] = sum;   // linear output layer 
    }

    BrainOutput result;
    result.opinionDelta = std::max(-10.0f, std::min(10.0f, out[0] * 10.0f));
    result.punchChance = std::max(0.0f, std::min(1.0f, out[1]));
    return result;
}

