# Deploying the retrieval layer on AWS

The gateway, its reranker and the regulation index, on the existing ECS services in Jakarta (`ap-southeast-3`). The stacks are in Metamorph-Knowledge-Platform:
- `deploy/aws/retrieval.yaml`: stack `metamorph-retrieval`. It holds the image repository, the `metamorph-retrieval` task (index builds, refreshes, one-off evals) and the `retrieval-gateway` service.
- `deploy/aws/dev/retrieval.yaml`: stack `metamorph-retrieval-dev`. It holds the development-only public address and its own service, `retrieval-gateway-dev`.

## What runs where

| Piece | Runs as | Reads | Writes |
|---|---|---|---|
| Gateway (`metamorph-gateway serve`) | `retrieval-gateway` and `retrieval-gateway-dev`, task family `metamorph-retrieval-gateway`, 2 vCPU / 8 GB | `published_market`, `retrieval_market`, `retrieval_regulation`, as `retrieval_reader` | Nothing |
| Reranker | Inside the gateway task: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, on its CPU, over the first `METAMORPH_RETRIEVAL_RERANK_CANDIDATES` fused candidates (50, the code's default, since 2026-11-10: on the eval it gained 4 cases and lost 2 of 187 against 25, for searches about 50% slower) | | |
| Regulation index build | Task `metamorph-retrieval`, with a command override | `published`, as `metamorph` | Schema `retrieval_regulation` |
| Market index refresh | Task `metamorph-retrieval`, as it is (`scripts/refresh-market-index.sh`) | `published_market`, as `metamorph` | Schema `retrieval_market` |

**Settings:**
- `PGOPTIONS=-c search_path=retrieval_regulation,public` names the regulation index's schema, for both tasks. It isn't a secret. The market's tables name their own schema, so the setting doesn't affect them.
- The database URLs are the existing parameters, `/metamorph/retrieval/reader-database-url` and `/metamorph/retrieval/indexer-database-url`. The second signs in as `metamorph`, the master user; there is no `retrieval_indexer` role.

**The models** are baked into the image at pinned revisions (`Dockerfile`), and tasks read only them (`HF_HUB_OFFLINE=1`).

**`DNNL_DEFAULT_FPMATH_MODE=BF16`** has torch's oneDNN do matrix maths in bf16 on Graviton3, whose CPU has `bf16` and `i8mm`. **Fargate doesn't promise that CPU.** An arm64 task lands on Graviton3 (`CPU part 0xd40`) or Graviton2 (`0xd0c`, no `bf16`), and the setting does nothing on Graviton2: the reranker then misses its 5 s budget on every search (below). Of five tasks on 2026-11-04, three were on Graviton3 and one on Graviton2, read from `/proc/cpuinfo`, and one was on Graviton2 by its timings. Measured on Graviton3 on 2026-11-03, 50 rerank pairs:

| Runtime | Time |
|---|---|
| torch, fp32 | 5.3 s |
| torch, bf16 maths | 2.3 s |
| ONNX fp32 | 6.3 s |
| ONNX int8 | 1.9 s |

int8 changed the ranking (rank correlation 0.80 with fp32); bf16 left the question sets' results as good or better (below).

## Why this hardware

The role's policy caps ECS tasks at 2 vCPU and 8 GB (`EcsTaskCpuCap`, `EcsTaskMemoryCap`), and EC2 instances at `*.large`, so no GPU instance. Measured on 2026-11-03:

| Option | Within the role? | Result |
|---|---|---|
| A cross-encoder in the gateway task (CPU) | Yes | `mmarco-mMiniLMv2-L12` as good as `bge-reranker-v2-m3` on the question sets. About 0.9 s a question on 2 threads of an M-series CPU |
| `bge-reranker-v2-m3` in the gateway task | Yes | Several seconds a question on 2 vCPU |
| Bedrock `cohere.rerank-v3-5` | No: needs `aws-marketplace:Subscribe` | |
| Bedrock `amazon.rerank-v1:0` | Yes, through `Project3EcsTaskRole` (`bedrock:InvokeModel*`), but only in `us-west-2` | Throttled at 50 candidates of 2,000 characters even one call at a time. The quota can't be read or raised from the role. And user questions would leave Jakarta |
| A SageMaker endpoint on `ml.g5.xlarge` | Allowed by the policy, with `Project3SageMakerExecutionRole` | Not tried: about USD 1 an hour, always on |

## Checklist

Run it from Metamorph-Knowledge-Platform, with the helpers of its `docs/aws-deployment-guide.md` (`deploy`, `exported`) and an SSO session.

### 1. Code and image

1. Commit both repositories. The image's tag is the retrieval commit:
   ```bash
   TAG=$(git -C ../Metamorph-Retrieval rev-parse --short HEAD)
   TAG=$TAG deploy/aws/push-images.sh retrieval
   ```
   The image is about 6 GB, the models included.

### 2. The database, once

2. As the master user, through the `metamorph-dbops` task (its command is a `psql -c`):
   ```sql
   create schema if not exists retrieval_regulation authorization metamorph;
   grant usage on schema retrieval_regulation to retrieval_reader;
   alter default privileges for role metamorph in schema retrieval_regulation grant select on tables to retrieval_reader;
   ```
   The schema must exist before the build. A `search_path` naming a missing schema would put the tables in `public`.

### 3. The task definitions, with the gateway off

3. The dev stack first. It names the gateway's task definition instead of importing it, so the retrieval stack can register a new revision. With revision 1, the one it runs now, nothing restarts:
   ```bash
   aws cloudformation deploy --stack-name metamorph-retrieval-dev --template-file deploy/aws/dev/retrieval.yaml \
     --tags Owner=project3 --parameter-overrides GatewayTask=metamorph-retrieval-gateway:1
   ```
4. Then the retrieval stack: the new image, 8 GB, the reranker, `PGOPTIONS`. The `retrieval-gateway` service stays at 0 until the index exists:
   ```bash
   deploy retrieval --parameter-overrides RetrievalTag=$TAG GatewayCount=0
   ```

### 4. The regulation index

Embedding on 2 Graviton vCPUs runs at about 2 units a second (measured 2026-11-03), so a first build there would take more than a day. Vectors move between builds by chunk instead. A chunk's id names its document, its text, its address and what the model reads, so its vector is the same wherever it is built, and a change to the context gives new ids and so new vectors. So the first build is seeded with vectors made where embedding is fast, and the task embeds only the chunks they don't cover. A later refresh embeds only what changed.

5. On a machine with a GPU, build the index, or keep one built, then export its vectors and share them through the operations bucket:
   ```bash
   metamorph-regulation-index export-vectors --snapshot <its snapshot> --to vectors.copy.gz
   aws s3 cp vectors.copy.gz s3://metamorph-ops-<account>/transfer/retrieval/regulation-vectors-$SNAPSHOT.copy.gz
   URL=$(aws s3 presign s3://metamorph-ops-<account>/transfer/retrieval/regulation-vectors-$SNAPSHOT.copy.gz --expires-in 21600)
   ```
   - The presigned link lets the task read the file without a role of its own.
   - The file is gzipped `COPY` text: chunk id, then vector. About 840 MB for 180,000 units.
6. Build and activate the snapshot in the `metamorph-retrieval` task. Every published document is included, UU 27/2022 too.
   ```bash
   SNAPSHOT=$(date -u +%Y-%m-%d)
   aws ecs run-task --cluster metamorph --task-definition metamorph-retrieval --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[$(exported metamorph-subnets | cut -d, -f1)],securityGroups=[$(exported metamorph-sg-retrieval)],assignPublicIp=ENABLED}" \
     --overrides "{\"containerOverrides\":[{\"name\":\"main\",\"command\":[\"sh\",\"-c\",\"metamorph-regulation-index build --snapshot $SNAPSHOT --vectors '$URL' && metamorph-regulation-index activate --snapshot $SNAPSHOT\"]}]}" \
     --tags key=Owner,value=project3
   ```
   - **The log** says how many vectors were taken, then embeds the rest.
   - **An index built before 2026-11-04 has no links.** `follow_links` then says so in a warning and answers with the market's links alone, until a build makes `regulation_chunk_live_links` and each document's status history. Nothing else changes, so the same vectors seed that build.
   - **Vectors made before the context change don't seed a build after it.** Since 2026-11-04 the model reads each unit's citation and headings too, so every chunk id is new, and a build seeded with `regulation-vectors-2026-11-03.copy.gz` would take none of its vectors and embed everything in the task. Export fresh vectors first (step 5). The headings come from `published.provision.heading_path`, so the platform database must have that column.
   - **Apply the platform's migration 0023 first** (`metamorph db migrate`, on RDS). It makes the items of a unit longer than 2,000 characters units too (about 43,000 more, most in circulars), and the build embeds them: about 43,000 chunks the seed doesn't cover, unless the vectors come from a build made after the migration. Locally, on 2026-11-10, a build seeded from `61104context` embedded 42,915.
   - **An index built since 2026-11-10 gives each provision its own status,** from the document's address-level status events: an article nothing touched in a partly revoked regulation reads `in_force`. An older index shows each provision its document's status, and reads as before.
   - **An index built before 2026-11-09 has no outlines.** Reading a whole regulation then gives its card without `outline`, and nothing else changes. Outlines come from `published.provision` (`ordinal`, `depth`, `heading_path`, `heading`) and take no vectors, so the same vectors seed that build.
   - **The first build activates without a judgement:** there is no active index to compare with. Later builds run `scripts/refresh-regulation-index.sh` (the platform's `regulation_index` DAG runs it after each publish). It builds a snapshot that takes the live one's vectors by chunk id, so only new and changed chunks are embedded; runs the golden and corpus sets through the regulation provider on both snapshots with `metamorph-eval`; and activates the new one only if `metamorph-eval compare` finds it no worse on each, as the market's refresh does.
   - **Check:** `metamorph-regulation-index versions` lists the snapshot as `live`.

### 5. The gate, inside the VPC

7. Both question sets through the gateway, built in the task as `serve` builds it, with the gateway task's settings. Override the command of a `metamorph-retrieval` task with:
   ```bash
   export METAMORPH_RETRIEVAL_RERANKER=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
   metamorph-eval run eval/regulation/cases.jsonl --provider metamorph_retrieval_gateway.wiring:gateway_from_environment
   metamorph-eval run eval/market/cases.jsonl --provider metamorph_retrieval_gateway.wiring:gateway_from_environment
   ```
   - **The gate:** at least the Mac's results in `eval/README.md` (regulation through the reranking gateway 15 of 42; market 52 of 54).
   - **Check the task's CPU first:** `grep -m1 'CPU part' /proc/cpuinfo`. On Graviton2 the gate measures that CPU, not the build: exit and run another task.
   - **To gate a build before activating it,** point the task at its tables with `METAMORPH_REGULATION_CHUNK_TABLE`, `METAMORPH_REGULATION_EMBED_TABLE` and `METAMORPH_REGULATION_META_TABLE` (`regulation_chunk_<date>`, and so on).
   - **Latency:** a search's p95 on 2 vCPU, which the reranker raises. Before this change it was 701 ms.
   - **Reranking fewer candidates** is faster: run the sets again with `METAMORPH_RETRIEVAL_RERANK_CANDIDATES=25`.
     - On the Mac: 13 of 42 instead of 15 (market unchanged).
     - In a 2-CPU container: the reranker took 1.4 s instead of 4.1 s.

     Set the gateway task's value from what Fargate measures.

### 6. The gateway on

8. Start it:
   ```bash
   deploy retrieval --parameter-overrides RetrievalTag=$TAG GatewayCount=1
   ```
   - The circuit breaker rolls a failed start back.
   - **Health:** the target answers `/health`. The log shows both providers and the reranker loaded.
9. Move the development service to the new revision:
   ```bash
   REVISION=$(aws ecs describe-task-definition --task-definition metamorph-retrieval-gateway --query taskDefinition.revision --output text)
   aws cloudformation deploy --stack-name metamorph-retrieval-dev --template-file deploy/aws/dev/retrieval.yaml \
     --tags Owner=project3 --parameter-overrides GatewayTask=metamorph-retrieval-gateway:$REVISION
   ```
   Then run the question sets through `https://d2ae8k1h45zs74.cloudfront.net` with the dev token, as `docs/connecting-an-agent.md` shows.

## Deployed on 2026-11-04: links

| Gate on the new index, 25 candidates | Regulation set | Market set | Federated set | A search | A `follow_links` |
|---|---|---|---|---|---|
| Inside the VPC, on Graviton3 (**what runs**) | 14 of 42 | 52 of 54 | 25 of 27, links 13 of 13 | p50 3.0 s, p95 4.1 s | p50 50 ms, p95 57 ms |
| Inside the VPC, on Graviton2 | 9 of 42 | 52 of 54 | 24 of 27, links 13 of 13 | p50 7.1 s, p95 8.4 s; 20 of 20 not reranked | p50 51 ms |
| Through the public development address | 14 of 42 | 52 of 54 | 25 of 27 | | |

**What runs:**
- **Image:** `metamorph/retrieval:4d9cb5d`.
- **Task definitions:** `metamorph-retrieval-gateway:5`, for both `retrieval-gateway` and `retrieval-gateway-dev`; and `metamorph-retrieval:5`.
- **Index:** `2026-11-04`, live in `retrieval_regulation`: 577,539 chunks, 179,523 vectors, 137,123 links, 2,561 documents with their status histories. The build took 15 minutes, seeded from the 2026-11-03 vectors, 295 embedded in the task.
- **The tables before it** are kept as `regulation_*_live__old`, about 2.6 GB, to roll back.

**Open:** which CPU `retrieval-gateway`'s task landed on can't be read from outside it. A replaced task can land on Graviton2, and then every search falls back to fused order with `NOT_RERANKED`.

**A gateway decides once whether the index holds links.** One asked before the activation keeps answering without them until it restarts.

## Deployed on 2026-11-03

| Gate, inside the VPC (bf16 maths) | Regulation set | Market set | A search's latency |
|---|---|---|---|
| Regulation provider alone, no reranking | 13 of 42, recall 0.33 | | |
| Gateway, rerank 25 candidates (**what runs**) | 14 of 42, recall 0.36, MRR 0.31 | 52 of 54; search recall 0.71, MRR 0.75 | p50 2.9 s, p95 3.6 s |
| Gateway, rerank 50 candidates | 16 of 42, recall 0.43, MRR 0.38 | 52 of 54; search recall 0.70, MRR 0.75 | p50 5.6 s, p95 6.9 s |
| Gateway, rerank 50, fp32 maths | 7 of 42 | 49 of 54 | p50 10.3 s: the reranker misses its 5 s budget, and the fused order stands |

**Through the public development address** (CloudFront, with the token): regulation 14 of 42 and market 52 of 54, the same. Without the token: 401.

**What runs:**
- **Image:** `metamorph/retrieval:abacb24`.
- **Task definitions:** `metamorph-retrieval-gateway:4`, for both `retrieval-gateway` (1 task) and `retrieval-gateway-dev`; and `metamorph-retrieval:4`.
- **Index:** `2026-11-03`, live in `retrieval_regulation`: 577,539 chunks, 179,523 vectors, 2,561 documents, about 2.6 GB.
  - 179,228 of its vectors came from the Mac's build (`s3://metamorph-ops-<account>/transfer/retrieval/regulation-vectors-2026-11-03.copy.gz`, kept to seed later builds).
  - 295 were embedded in the task, mostly UU 27/2022.

**Latency:** a search was 0.7 s at p95 before the regulation provider and the reranker. Fewer candidates trade quality for speed. So does more hardware, which the role doesn't allow (the table above).

## Traces on AWS: not yet on

The deployed gateway (image `4d9cb5d`) has no exporter. To send its spans to Langfuse:
1. Build and push an image from this code. The image has the `otlp` extra already, as it installs every extra.
2. Write the header as a SecureString, `/metamorph/retrieval/otel-headers`, with the value from [connecting-an-agent.md](connecting-an-agent.md#tracing).
3. In the gateway's task definition, add `OTEL_EXPORTER_OTLP_ENDPOINT` to its environment, and `OTEL_EXPORTER_OTLP_HEADERS` to its `Secrets`, from that parameter.

## Rolling back

- **The gateway:** deploy the retrieval stack with the previous tag (`RetrievalTag=724c16d`), and the dev stack with `GatewayTask=metamorph-retrieval-gateway:1`. The old image doesn't read `retrieval_regulation`, so the index can stay.
- **The reranker alone:** remove `METAMORPH_RETRIEVAL_RERANKER` from the gateway task. Searches then come back in fused order.
- **The index:** the last build's tables are `regulation_*_live__old`; rename them back over the live names, in one transaction. `drop schema retrieval_regulation cascade` removes the index altogether. Friend 2's trial tables (`public.bench_*`, about 5.5 GB) are separate, and this deployment doesn't touch them.
