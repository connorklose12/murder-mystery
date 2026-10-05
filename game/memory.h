// Retrieval-based NPC memory (the "RAG" idea, scaled down to a game): villagers remember MANY things the player told them, and when a conversation
// touches a topic they RETRIEVE only the relevant memory by vector similarity and weave it into the prompt, instead of dumping everything in.

#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

const int EMBED_DIM = 1024;
const size_t MEMORY_MAX = 12;           // facts kept per villager (the newest; a newer answer about the same subject replaces the old one)
const float RECALL_MIN_LEXICAL = 0.30f;    // below this similarity nothing is recalled (both thresholds are calibrated against the benchmarks in tests.cpp)
const float RECALL_MIN_SEMANTIC = 0.30f;
const float RECALL_GAP_SEMANTIC = 0.06f;    // semantic scores are high for everything, so the best match must also beat the runner-up by this much (see the README for the trade-off)

inline uint32_t Fnv1a(const std::string& s, uint32_t h = 2166136261u) {   // a simple, stable string hash
    for (unsigned char c : s) { h ^= c; h *= 16777619u; }
    return h;
}

// Words that say nothing about WHAT a memory is about (every remembered fact starts "the player's favorite ...").
inline bool IsStopWord(const std::string& w) {
    static const char* stop[] = {"the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "are", "his", "her", "their", "they", "them", "about",
                                 "player", "told", "tells", "telling", "said", "favorite", "favourite", "once", "also", "very", "just", "into", "than", "then", "its",
                                 "is", "of", "to", "in", "it", "he", "she", "at", "on", "an", "a", "as", "by", "or", "be", "so", "no", "my", "we", "up"};
    for (const char* s : stop) if (w == s) return true;
    return false;
}

// Tiny normalisation so related words meet: plural endings are dropped and a few families of words share one concept.
inline std::string Normalize(std::string w) {
    struct Family { const char* label; const char* words; };
    static const Family fam[] = {
        {"fear", " afraid scared fear fears frightened terrified phobia nervous "},
        {"dream", " dream dreams dreamed dreamt wish wishes hope hopes someday "},
        {"food", " food foods eat eats eating meal meals hungry taste tasty delicious dish snack dinner lunch breakfast "},
        {"music", " music song songs sing singing singer band melody tune "},
        {"trip", " vacation vacations trip trips travel visit holiday journey "},
        {"hobby", " hobby hobbies pastime craft "},
    };
    if (w.size() > 3 && w.back() == 's' && w[w.size() - 2] != 's') w.pop_back();
    for (const Family& f : fam) if (std::string(f.words).find(" " + w + " ") != std::string::npos) return f.label;
    return w;
}

inline std::vector<std::string> Words(const std::string& text) {   // lowercase letters only, 2+ letters, stop words dropped
    std::vector<std::string> out; std::string cur;
    for (size_t i = 0; i <= text.size(); i++) {
        char c = i < text.size() ? text[i] : ' ';
        if (std::isalpha((unsigned char)c)) cur += (char)std::tolower((unsigned char)c);
        else { if (cur.size() >= 2 && !IsStopWord(cur)) out.push_back(Normalize(cur)); cur.clear(); }
    }
    return out;
}

inline void AddFeature(std::vector<float>& v, const std::string& key, float weight) {   // signed hashing: each feature adds +w or -w to one bucket
    uint32_t h = Fnv1a(key);
    v[h % EMBED_DIM] += ((Fnv1a(key, 0x9e3779b9u) & 1u) ? weight : -weight);
}

struct SemanticTable {
    bool loaded = false; int dim = 0; float scale = 1;
    std::vector<float> mean; std::unordered_map<std::string, int> index; std::vector<int8_t> vec;
};
inline SemanticTable& SemTable() { static SemanticTable t; return t; }
inline bool LoadEmbeddingTable(const unsigned char* d, int n) {   // format: "PWE1", count, dim, scale, mean[dim], count x (length byte + word), count x dim int8 values (little endian)
    SemanticTable t;
    if (!d || n < 16 || std::memcmp(d, "PWE1", 4) != 0) return false;
    uint32_t count, dim; float scale;
    std::memcpy(&count, d + 4, 4); std::memcpy(&dim, d + 8, 4); std::memcpy(&scale, d + 12, 4);
    if (dim < 2 || dim > 1024 || count > 1000000) return false;
    size_t p = 16;
    if ((size_t)n < p + 4 * (size_t)dim) return false;
    t.mean.resize(dim); std::memcpy(t.mean.data(), d + p, 4 * (size_t)dim); p += 4 * (size_t)dim;
    for (uint32_t i = 0; i < count; i++) {
        if (p >= (size_t)n) return false;
        size_t len = d[p++];
        if (p + len > (size_t)n) return false;
        t.index[std::string((const char*)d + p, len)] = (int)i; p += len;
    }
    if (p + (size_t)count * dim > (size_t)n) return false;
    t.vec.resize((size_t)count * dim); std::memcpy(t.vec.data(), d + p, t.vec.size());
    t.dim = (int)dim; t.scale = scale; t.loaded = true;
    SemTable() = std::move(t);
    return true;
}
inline std::vector<float> OovVector(const std::string& w, int dim) {   // an unknown word gets a stable pseudo-random vector (integer arithmetic only, so Python agrees exactly)
    std::vector<float> v(dim); uint32_t state = Fnv1a(w); float norm = 0;
    for (int k = 0; k < dim; k++) { state = state * 1664525u + 1013904223u; v[k] = (float)(state >> 8) / 16777216.0f - 0.5f; norm += v[k] * v[k]; }
    norm = std::sqrt(norm); for (float& x : v) x = x / norm * 3.0f;
    return v;
}
inline std::vector<float> EmbedSemantic(const std::string& text) {   // [mean, element-wise max] of the word vectors (common component removed), scaled to length 1: 2 x dim numbers
    const SemanticTable& T = SemTable(); const int D = T.dim;
    std::vector<float> sum(D, 0.0f), mx(D, -1e30f), x(D); int count = 0;
    for (const std::string& w : Words(text)) {
        auto it = T.index.find(w);
        if (it != T.index.end()) { const int8_t* row = &T.vec[(size_t)it->second * D]; for (int k = 0; k < D; k++) x[k] = (float)row[k] * T.scale - T.mean[k]; }
        else { x = OovVector(w, D); for (int k = 0; k < D; k++) x[k] *= 0.3f; }
        for (int k = 0; k < D; k++) { sum[k] += x[k]; mx[k] = std::max(mx[k], x[k]); }
        count++;
    }
    std::vector<float> v(2 * D, 0.0f);
    if (count == 0) return v;
    for (int k = 0; k < D; k++) { v[k] = sum[k] / count; v[D + k] = mx[k]; }
    float norm = 0; for (float f : v) norm += f * f;
    norm = std::sqrt(norm);
    if (norm > 0) for (float& f : v) f /= norm;
    return v;
}
inline float RecallMinScore() { return SemTable().loaded ? RECALL_MIN_SEMANTIC : RECALL_MIN_LEXICAL; }
inline float RecallMinGap() { return SemTable().loaded ? RECALL_GAP_SEMANTIC : 0.0f; }

inline std::vector<float> EmbedLexical(const std::string& text) {
    std::vector<float> v(EMBED_DIM, 0.0f);
    for (const std::string& w : Words(text)) {
        AddFeature(v, "w:" + w, 1.0f);                                       // the whole word
        std::string padded = "^" + w + "$";
        for (size_t i = 0; i + 3 <= padded.size(); i++) AddFeature(v, "t:" + padded.substr(i, 3), 0.25f);   // its character trigrams ("pizza" ~ "pizzas")
    }
    float norm = 0; for (float x : v) norm += x * x;
    norm = std::sqrt(norm);
    if (norm > 0) for (float& x : v) x /= norm;
    return v;
}

inline std::vector<float> Embed(const std::string& text) { return SemTable().loaded ? EmbedSemantic(text) : EmbedLexical(text); }

inline float Cosine(const std::vector<float>& a, const std::vector<float>& b) {   // both are length 1, so this is just the dot product
    float d = 0; for (size_t i = 0; i < a.size() && i < b.size(); i++) d += a[i] * b[i];
    return d;
}

struct Recalled { int index; float score; };
// Best matches first. With k == 1 the best match must also lead the runner-up by minGap (a clear winner), otherwise nothing is recalled.
inline std::vector<Recalled> Recall(const std::vector<std::string>& memories, const std::string& query, int k, float minScore = -2.0f, float minGap = -2.0f) {
    if (minScore < -1.0f) minScore = RecallMinScore();   // (the defaults: the right thresholds for whichever backend is active)
    if (minGap < -1.0f) minGap = RecallMinGap();
    std::vector<float> q = Embed(query);
    std::vector<Recalled> all;
    for (size_t i = 0; i < memories.size(); i++) all.push_back({(int)i, Cosine(q, Embed(memories[i]))});
    std::stable_sort(all.begin(), all.end(), [](const Recalled& a, const Recalled& b) { return a.score != b.score ? a.score > b.score : a.index > b.index; });   // best first; on a tie the newer memory wins
    std::vector<Recalled> hits;
    for (const Recalled& r : all) if (r.score >= minScore) hits.push_back(r);
    if (k == 1 && !hits.empty() && all.size() > 1 && all[0].score - all[1].score < minGap) hits.clear();
    if ((int)hits.size() > k) hits.resize(k);
    return hits;
}

// Stores a fact: a newer answer about the same subject ("the player's favorite food ...") replaces the older one, and only the newest MEMORY_MAX are kept.
inline void RememberFact(std::vector<std::string>& mem, const std::string& fact, size_t maxKeep = MEMORY_MAX) {
    size_t cut = fact.find(" is ");
    if (cut != std::string::npos) {
        std::string subject = fact.substr(0, cut);
        for (size_t i = 0; i < mem.size();) { if (mem[i].compare(0, subject.size() + 4, subject + " is ") == 0) mem.erase(mem.begin() + i); else i++; }
    }
    mem.push_back(fact);
    while (mem.size() > maxKeep) mem.erase(mem.begin());
}