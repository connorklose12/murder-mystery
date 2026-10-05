// Monte Carlo forecast of "who dies next, and in what order": imagine the village's future thousands of times, using the game's own rules, and count.
//
// Each ROLLOUT copies the village as it is right now (who likes whom, who has fought, who is dating) and plays it forward with SocialTick / SocialPickTarget / SocialAttack from
// social.h, the same functions the real game calls, until three villagers have died or an hour of game time has passed. Doing that many times gives, for every villager,
// the chance of being the next to die and the chance of being second and third. (This is the random-simulation core of Monte Carlo Tree Search. There is no tree because
// nobody makes decisions inside a rollout, so there is nothing to search over.)
//
// Simplifications, stated plainly: where villagers walk is not simulated, every 20 seconds each one is placed in a random spot (so who is near whom keeps changing), and the
// player does not take part. No raylib here, so tests.cpp can run it.
#pragma once
#include "social.h"
#include <algorithm>

constexpr float ATTACK_COOLDOWN_S = 45.0f;       // seconds before a villager can start another fight (the game and the forecast share this number)
constexpr int FORECAST_DEATHS = 3;               // how many deaths deep each rollout looks (first, second, third)
constexpr int FORECAST_HORIZON_S = 3600;         // each rollout looks at most this far ahead (an hour of game time)

struct DeathForecast {
    int rollouts = 0, noDeath = 0;                // rollouts finished, and how many saw nobody die within the horizon
    int place[FORECAST_DEATHS][MAX_NPCS] = {};   
        float ProbNext(int i) const { int den = rollouts - noDeath; return den > 0 ? (float)place[0][i] / (float)den : 0.0f; }   // chance i dies next, among rollouts where anyone dies
};

inline int ForecastTopPick(const DeathForecast& f, unsigned excludeMask = 0, int k = 0) {   // the likeliest (k+1)-th death, or -1 with no data
    int best = -1;
    for (int i = 0; i < MAX_NPCS; i++) if (!((excludeMask >> i) & 1u) && f.place[k][i] > 0 && (best < 0 || f.place[k][i] > f.place[k][best])) best = i;
    return best;
}
inline void ForecastOrder(const DeathForecast& f, int out[FORECAST_DEATHS]) {                // the likeliest sequence: best first death, then best second among the rest etc.
    unsigned used = 0;
    for (int k = 0; k < FORECAST_DEATHS; k++) { out[k] = ForecastTopPick(f, used, k); if (out[k] >= 0) used |= 1u << out[k]; }
}

inline void ScatterVillagers(const Social& s, SocialView& v, Social& dice) {   // new random places for everyone (room and spot)
    for (int i = 0; i < s.n; i++) {
        float r = dice.Rand01();
        v.loc[i] = r < 0.6f ? 0 : (r < 0.8f ? 1 : 2);
        v.x[i] = (dice.Rand01() * 2.0f - 1.0f) * 7.0f; v.z[i] = (dice.Rand01() * 2.0f - 1.0f) * 7.0f;
    }
}

// Plays the village forward 'seconds' seconds with the game's rules, changing 's'. Records up to maxDeaths victims in order[] and returns how many died.
inline int Simulate(Social& s, SocialView& v, unsigned seed, int seconds, int* order, int maxDeaths) {
    s.rng = seed * 2654435761u + 12345u; if (!s.rng) s.rng = 1u;
    float cooldown[MAX_NPCS] = {};
    int deaths = 0;
    for (int t = 1; t <= seconds && deaths < maxDeaths; t++) {
        if (t % 20 == 0) ScatterVillagers(s, v, s);
        SocialTick(s, v, (float)t);
        for (int a = 0; a < s.n && deaths < maxDeaths; a++) {
            if (!s.alive[a]) continue;
            if (cooldown[a] > 0) { cooldown[a] -= 1.0f; continue; }
            int target = SocialPickTarget(s, v, a);
            if (target < 0 || !s.alive[target]) continue;
            cooldown[a] = ATTACK_COOLDOWN_S;
            if (SocialAttack(s, v, a, target, (float)t) == ATTACK_KILL) order[deaths++] = target;
        }
    }
    return deaths;
}

// One imagined future from the village as it is now (the village is copied, the real one is untouched). Returns how many deaths it found (up to wantDeaths) and who, in order.
inline int Rollout(Social s, SocialView v, unsigned seed, int order[FORECAST_DEATHS], int wantDeaths = FORECAST_DEATHS) { return Simulate(s, v, seed, FORECAST_HORIZON_S, order, wantDeaths); }

// The forecast the game keeps: start it, then call Step() a few rollouts at a time each frame (so the game never stalls) until Done().
struct Forecaster {
    Social base; SocialView view; unsigned seed = 1; int total = 0; DeathForecast f; bool active = false;
    void Start(const Social& s, const SocialView& v, unsigned sd, int rollouts = 120) { base = s; view = v; seed = sd; total = rollouts; f = DeathForecast(); active = true; }
    bool Done() const { return active && f.rollouts >= total; }
    void Step(int n) {
        for (int i = 0; i < n && active && f.rollouts < total; i++) {
            int order[FORECAST_DEATHS]; int d = Rollout(base, view, seed + (unsigned)f.rollouts * 7919u, order);
            f.rollouts++; if (d == 0) f.noDeath++;
            for (int k = 0; k < d; k++) f.place[k][order[k]]++;
        }
    }
};
