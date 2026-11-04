# Regulation holdout set, context, gateway, 25 rerank candidates, local, 2026-11-04

| Tool | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| all | 36 | 33 | 0.90 | 0.74 |
| search_documents | 36 | 33 | 0.90 | 0.74 |

## By phase

| Phase | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| compliance | 36 | 33 | 0.90 | 0.74 |

## Failures (3)

- **corpus-ojk-seojk-11** (search_documents, compliance): We're preparing our rural bank's governance self-assessment. How many factors does it cover and what are they?
  - not in the first 8: doc:ojk:seojk:2016:5#lampiran-ii
- **corpus-bi-padg-10** (search_documents, compliance): While a conventional bank is receiving short-term liquidity support from Bank Indonesia, which monetary operations may it join?
  - not in the first 8: doc:bi:padg:2023:21#pasal-77
- **corpus-dsnmui-fatwa-14** (search_documents, compliance): A dispute broke out between participants of our sharia multi-level marketing business. How should it be resolved?
  - not in the first 8: doc:dsnmui:fatwa:75#diktum-keempat
