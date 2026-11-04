# Regulation holdout set, before-context, gateway, 50 rerank candidates, local, 2026-11-04

| Tool | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| all | 36 | 32 | 0.88 | 0.73 |
| search_documents | 36 | 32 | 0.88 | 0.73 |

## By phase

| Phase | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| compliance | 36 | 32 | 0.88 | 0.73 |

## Failures (4)

- **corpus-ojk-seojk-11** (search_documents, compliance): We're preparing our rural bank's governance self-assessment. How many factors does it cover and what are they?
  - not in the first 8: doc:ojk:seojk:2016:5#lampiran-ii
- **corpus-bi-padg-10** (search_documents, compliance): While a conventional bank is receiving short-term liquidity support from Bank Indonesia, which monetary operations may it join?
  - not in the first 8: doc:bi:padg:2023:21#pasal-77
- **corpus-dsnmui-fatwa-14** (search_documents, compliance): A dispute broke out between participants of our sharia multi-level marketing business. How should it be resolved?
  - not in the first 8: doc:dsnmui:fatwa:75#diktum-keempat
- **corpus-other-16** (search_documents, compliance): How do goods and service providers report a suspicious activity report in goAML when they stop a customer due diligence procedure?
  - not in the first 8: doc:id:peraturan-ppatk:2021:2#lampiran-vi
