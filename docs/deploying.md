# Deploying the retrieval layer on AWS

The gateway, its reranker and the regulation index, on the existing ECS services in Jakarta (`ap-southeast-3`). The stacks are in Metamorph-Knowledge-Platform:
- `deploy/aws/retrieval.yaml`: stack `metamorph-retrieval`. It holds the image repository, the `metamorph-retrieval` task (index builds, refreshes, one-off evals) and the `retrieval-gateway` service.
- `deploy/aws/dev/retrieval.yaml`: stack `metamorph-retrieval-dev`. It holds the development-only public address and its own service, `retrieval-gateway-dev`.

## What runs where

| Piece | Runs as | Reads | Writes |
|---|---|---|---|
| Gateway (`metamorph-gateway serve`) | `retrieval-gateway` and `retrieval-gateway-dev`, task family `metamorph-retrieval-gateway`, 2 vCPU / 8 GB | `published_market`, `retrieval_market`, `retrieval_regulation`, as `retrieval_reader` | Nothing |
| Reranker | Inside the gateway task: `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, on its CPU, over the first `METAMORPH_RETRIEVAL_RERANK_CANDIDATES` fused candidates (default 50) | | |
| Regulation index build | Task `metamorph-retrieval`, with a command override | `published`, as `metamorph` | Schema `retrieval_regulation` |
| Market index refresh | Task `metamorph-retrieval`, as it is (`scripts/refresh-market-index.sh`) | `published_market`, as `metamorph` | Schema `retrieval_market` |

**Settings:**
- `PGOPTIONS=-c search_path=retrieval_regulation,public` names the regulation index's schema, for both tasks. It isn't a secret. The market's tables name their own schema, so the setting doesn't affect them.
- The database URLs are the existing parameters, `/metamorph/retrieval/reader-database-url` and `/metamorph/retrieval/indexer-database-url`. The second signs in as `metamorph`, the master user; there is no `retrieval_indexer` role.

**The models** are baked into the image at pinned revisions (`Dockerfile`), and tasks read only them (`HF_HUB_OFFLINE=1`).

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
   deploy dev/retrieval --parameter-overrides GatewayTask=metamorph-retrieval-gateway:1
   ```
4. Then the retrieval stack: the new image, 8 GB, the reranker, `PGOPTIONS`. The `retrieval-gateway` service stays at 0 until the index exists:
   ```bash
   deploy retrieval --parameter-overrides RetrievalTag=$TAG GatewayCount=0
   ```

### 4. The regulation index

Embedding on 2 Graviton vCPUs runs at about 2 units a second (measured 2026-11-03), so a first build there would take more than a day. Vectors move between builds by chunk instead. A chunk's id names its document, its text, its address and its wording, so its vector is the same wherever it is built. So the first build is seeded with vectors made where embedding is fast, and the task embeds only the chunks they don't cover. A later refresh embeds only what changed.

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
   - **The first build activates without a judgement:** there is no active index to compare with. Later builds run `scripts/refresh-regulation-index.sh`, which judges the new snapshot against the active one before activating it.
   - **Check:** `metamorph-regulation-index versions` lists the snapshot as `live`.

### 5. The gate, inside the VPC

7. Both question sets through the gateway, built in the task as `serve` builds it, with the gateway task's settings. Override the command of a `metamorph-retrieval` task with:
   ```bash
   export METAMORPH_RETRIEVAL_RERANKER=cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
   metamorph-eval run eval/regulation/cases.jsonl --provider metamorph_retrieval_gateway.wiring:gateway_from_environment
   metamorph-eval run eval/market/cases.jsonl --provider metamorph_retrieval_gateway.wiring:gateway_from_environment
   ```
   - **The gate:** at least the Mac's results in `eval/README.md` (regulation through the reranking gateway 15 of 42; market 52 of 54).
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
   deploy dev/retrieval --parameter-overrides GatewayTask=metamorph-retrieval-gateway:$REVISION
   ```
   Then run the question sets through `https://d2ae8k1h45zs74.cloudfront.net` with the dev token, as `docs/connecting-an-agent.md` shows.

## Rolling back

- **The gateway:** deploy the retrieval stack with the previous tag (`RetrievalTag=724c16d`), and the dev stack with `GatewayTask=metamorph-retrieval-gateway:1`. The old image doesn't read `retrieval_regulation`, so the index can stay.
- **The reranker alone:** remove `METAMORPH_RETRIEVAL_RERANKER` from the gateway task. Searches then come back in fused order.
- **The index:** `drop schema retrieval_regulation cascade` removes it. Friend 2's trial tables (`public.bench_*`, about 5.5 GB) are separate, and this deployment doesn't touch them.
