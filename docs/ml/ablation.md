Labels: **standin**; 3000 labeled pairs; test = 444 pairs whose message text never appeared in training.

| Model | Opinion error (RMSE, points) | Shove error (MAE) | Within 3 points | Right direction | Parameters |
|---|---|---|---|---|---|
| hand-written rule (word lists) | 3.67 | 0.179 | 53% | 58% | - |
| linear (state + message probe) | 2.68 | 0.091 | 74% | 88% | - |
| old teacher-trained net (state only) | 2.98 | 0.067 | 73% | 86% | - |
| retrained, state only (no message) | 2.99 | 0.073 | 73% | 87% | - |
| MLP, state + raw embedding PCA-16 (overfits) | 3.09 | 0.069 | 70% | 86% | - |
| MLP 8 hidden, state + message probe | 2.67 | 0.065 | 75% | 87% | 114 |
| MLP 16 hidden, state + message probe (shipped) | 2.61 | 0.067 | 77% | 89% | 226 |
| MLP 32 hidden, state + message probe | 2.57 | 0.068 | 77% | 89% | 450 |
