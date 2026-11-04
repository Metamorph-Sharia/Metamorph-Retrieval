# Regulation corpus set, context, gateway, 50 rerank candidates, local, 2026-11-04

| Tool | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| all | 64 | 56 | 0.88 | 0.68 |
| search_documents | 64 | 56 | 0.88 | 0.68 |

## By phase

| Phase | Cases | Passed | Recall@k | MRR |
|---|---|---|---|---|
| compliance | 64 | 56 | 0.88 | 0.68 |

## Failures (8)

- **corpus-ojk-pojk-09** (search_documents, compliance): Can OJK fine an issuer that ignores a request for additional registration statement information without first giving a written warning?
  - not in the first 8: doc:ojk:pojk:2016:51#pasal-8/ayat-2
- **corpus-ojk-pojk-20** (search_documents, compliance): During book-building an investor told us they want to buy shares in the IPO. Does that indication commit them to buy?
  - not in the first 8: doc:ojk:pojk:2017:23#pasal-4
- **corpus-ojk-seojk-04** (search_documents, compliance): Laporan harian apa saja yang harus dikirim bank umum syariah ke OJK melalui sistem pelaporan?
  - not in the first 8: doc:ojk:seojk:2025:33#lampiran-i
- **corpus-ojk-seojk-17** (search_documents, compliance): Our conventional bank is applying to convert into a sharia commercial bank. What must the draft amended articles of association contain?
  - not in the first 8: doc:ojk:seojk:2023:6#romawi-iii
- **corpus-bi-pbi-03** (search_documents, compliance): Bank Indonesia is checking the data we reported to it without an on-site visit. What does that indirect supervision involve?
  - not in the first 8: doc:bi:pbi:2024:12#penjelasan/pasal-27/ayat-2/huruf-a
- **corpus-bi-pbi-05** (search_documents, compliance): A bank failed to file a report under PBI 9/6/PBI/2007. Can it be penalised for both non-submission and late submission?
  - not in the first 8: doc:bi:pbi:2007:6#penjelasan/pasal-53/ayat-2/huruf-b
- **corpus-dsnmui-fatwa-01** (search_documents, compliance): Bagaimana sengketa dalam akad pengalihan utang hawalah diselesaikan?
  - none in the first 8 of: doc:dsnmui:fatwa:12#diktum-kedua, doc:dsnmui:fatwa:10#diktum-ketiga, doc:dsnmui:fatwa:11#diktum-ketiga
- **corpus-dsnmui-fatwa-04** (search_documents, compliance): A customer took an interest-free qardh loan from our sharia bank and now wants to add a voluntary gift on repayment. Is that allowed?
  - not in the first 8: doc:dsnmui:fatwa:19#diktum-pertama
