# Retrieval contract 0.1

**What crosses between a retrieval provider, the gateway and an answering agent.** Every provider speaks it: the market provider (ours) and the regulatory provider (Friend 2's). The gateway composes providers through it alone, and the agent sees its shapes as JSON. The design behind it is `docs/retrieval-architecture.md` in Metamorph-Knowledge-Platform.

- **The formal contract** is the JSON Schema in [`schemas/retrieval.schema.json`](src/metamorph_retrieval_contract/schemas/retrieval.schema.json). Each shape is one of its `$defs`.
- **The Python types** and their codec (`to_dict`, `*_from_dict`) are a convenience for Python providers.
- **0.x may change,** and each change is announced. 1.0 freezes before anyone depends on it in production.

## Refs

A ref is `{namespace}:{id}[#{address}]`. It is the key to cite, cache, log and pass to the next tool.

| Namespace | Owner | Example |
|---|---|---|
| `doc` | regulatory | `doc:ojk:pojk:2024:40#pasal-5/ayat-1` (the address is `published.provision_unit`'s) |
| `report`, `release` | market | `report:ojk:lpksi:2025#p-12` |
| `dataset`, `series` | market | `series:bi:seki:tabel1_1:monthly:row=1` |
| `company`, `register` | market | `company:ojk:lpbbti:kep-49-d.05-2017` |
| `industry`, `sector` | market | `sector:sharia-banking` |

- **One owner per namespace,** declared in the owner's manifest. The gateway routes by it.
- **Ids and addresses come from the platform's read contracts** (`published`, `published_market`), never from an index. So a ref survives a re-index or a new embedding model.
- **A provider may name refs it doesn't own,** such as a dataset's governing regulations. It never resolves them: the owner does.

## Evidence

Every result has the same envelope:

| Field | Meaning |
|---|---|
| `ref`, `kind` | What it is: `regulation`, `fatwa`, `report`, `release`, `dataset`, `series`, `company`… |
| `citation` | Quote it as is |
| `title`, `published_on`, `url` | |
| `legal_force` | `binding`, `sharia`, `explanatory` or `none`. Reports, releases, statistics and companies are always `none`: what a regulator reports, announces or counts, never a requirement |
| `qualifiers` | `status`, `valid_from`, `valid_to`, `under_review`, `provisional`, `as_of`: what limits how much it counts |
| `body` | One of three, or `null` in a card. `text` holds `wording` and `pages`. `figures` holds `unit`, `frequency` and `observations`, each with a `period`, a `value` as the source gives it, and `provisional`. `record` holds `fields` |
| `provenance` | `provider`, `index_version`, `source_published_at`: which build answered, from which publish |

- **A search hit** adds:
  - `rank`, from 1;
  - `score`, comparable only within one provider and one call;
  - `matched_by`: `semantic`, `words`, or both.
- **A page** holds `items`, a `cursor` for the next page, `empty_reason` and `warnings`.
  - "Nothing found" is an empty page, never an error.
  - An empty page always says why: `no_match` (rephrase) or `filters_exclude_all` (widen the filters).

## What a provider offers

```python
class RetrievalProvider(Protocol):
    def manifest(self) -> Manifest: ...
    def search(self, request: SearchRequest) -> Page[Hit]: ...
    def read(self, ref: Ref, *, window: int = 0) -> Evidence: ...
    def describe(self, refs: Sequence[Ref]) -> Sequence[Evidence]: ...
    def links(self, ref: Ref, request: LinksRequest) -> Page[Link]: ...
    def call(self, tool: str, arguments: Mapping[str, Any]) -> JSON: ...
```

- **`manifest`:**
  - its name, version and contract version;
  - the `namespaces` it owns and the `kinds` its search holds (none: no search);
  - whether it answers `links`;
  - its own `tools`, each with a name, version, description and input and output JSON Schemas;
  - its `index_version` and `data_as_of`.
  
  The gateway builds the agent's tool catalog from the manifests.
- **`search`** runs over the kinds the provider holds, with the filters every text search shares:
  - `kinds`, `issuers`, `documents` (whole documents only);
  - `published_from`, `published_to`, `in_force_on`, `legal_force`;
  - `sort` (`relevance` or `newest`);
  - `limit` (8 by default, at most 25) and `cursor`.
  
  A filter the provider can't apply to its kinds is noted in `warnings`, never ignored silently. Filters are never relaxed behind the caller's back.
- **`read`** returns the whole evidence, and `window` passages either side of a passage. It raises `unknown_ref`.
- **`describe`** returns cards (evidence without a body), batched, in the order asked. **A ref it doesn't hold is left out, never an error,** because a link may name a regulation that isn't published yet.
- **`links`** returns what the provider knows about a ref, whether it owns the ref or not:
  - the regulation layer knows what amends a regulation;
  - the market layer knows which passages name it (`names`).
  
  Types: `legal_basis`, `implements`, `amends`, `supersedes`, `revokes`, `partly_revokes`, `adopts_fatwa`, `changes_fatwa`, `refers_to`, `names`.
- **`call`** runs one of the provider's own tools, and its result meets the tool's output schema.
  - A ranked tool returns a page of hits (`hit_page`).
  - An exact tool returns a page of evidence (`evidence_page`: unranked, in the tool's own order).
  - What an item names, it names as `{"ref": "…"}` in its record's fields, so the gateway can enrich it.

**Deterministic:** within one `index_version`, the same call gives the same result. No generative model runs at query time.

## Errors

On the wire, an error is `{"error": code, "message": …}`. The message says what would be accepted.

| Code | When |
|---|---|
| `unknown_ref` | Well formed, but nothing is published under it |
| `unknown_tool` | The provider has no tool of that name |
| `invalid_argument` | A malformed ref, an empty query, dates in the wrong order, a limit over 25 |
| `capability_missing` | Search or links from a provider whose manifest doesn't offer them |
| `provider_unavailable` | The provider failed or didn't answer in time. The others may still answer |

Reading data that breaks the schema raises `ContractViolation`, which lists every problem found. Whoever reads decides what it means: an agent's bad arguments are its `invalid_argument`; a provider's bad answer is that provider's fault.

## Conformance

A provider keeps the contract when this is empty:

```python
from metamorph_retrieval_contract import Samples, ToolCall, conformance_problems

assert conformance_problems(provider, Samples(
    refs=(...),                     # refs it holds
    unknown=Ref.parse("..."),       # a well-formed ref in its namespaces that it doesn't hold
    query="...",                    # when it has search: a query two of its pieces of evidence answer
    linked=Ref.parse("..."),        # when it has links: a ref it knows links about
    tool_calls=(ToolCall("find_series", {"query": "..."}),),  # at least one call of each tool
)) == []
```

**What it checks:**
- every ref is in the provider's namespaces;
- `read` returns the ref asked for, and `describe` agrees with `read(ref).card()`;
- unknown refs raise `unknown_ref`;
- limits are kept, and ranks run from 1;
- the same call gives the same result;
- search and links exist exactly when the manifest says so;
- each tool's output meets its schema, and an unknown tool raises `unknown_tool`;
- everything reads back the same from the wire.

A check that crashes is reported as a problem, never as a crash.

**What it doesn't check:** each provider's own rules, such as the market's `legal_force: none`. Those belong in that provider's tests.

## Versions

- `CONTRACT_VERSION` is `retrieval-0.1`, and a manifest states the version it speaks.
- A breaking change to a shape is a new version, served beside the old one until every caller has moved.
- A tool's schemas and description stay byte-stable within its version. That keeps the agent's prompt cache warm.
