import pytest

from metamorph_market_retrieval.adapters.embedder import MODELS, SentenceTransformerEmbedder, embedder_for


class Encoder:
    """Stands in for a SentenceTransformer: records what it was asked to encode."""

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    def encode(self, texts, **options):  # noqa: ANN001, ANN003, ANN201
        self.asked.append(list(texts))
        assert options["normalize_embeddings"] is True
        return [[float(len(text)), 0.0] for text in texts]


def test_an_e5_model_reads_queries_and_passages_with_their_prefixes() -> None:
    encoder = Encoder()
    embedder = SentenceTransformerEmbedder(MODELS["intfloat/multilingual-e5-base"], encoder=encoder)

    embedder.embed_queries(["pembiayaan"])
    embedder.embed_documents(["Pembiayaan produktif"])

    assert encoder.asked == [["query: pembiayaan"], ["passage: Pembiayaan produktif"]]
    assert embedder.model == "intfloat/multilingual-e5-base"


def test_a_query_asked_again_is_embedded_once() -> None:
    encoder = Encoder()
    embedder = SentenceTransformerEmbedder(MODELS["BAAI/bge-m3"], encoder=encoder)

    first = embedder.embed_queries(["izin usaha"])
    again = embedder.embed_queries(["izin usaha"])

    assert first == again and encoder.asked == [["izin usaha"]]


def test_a_model_not_in_the_table_is_refused_with_the_ones_that_are() -> None:
    with pytest.raises(ValueError, match="no-such/model: not a known embedding model; known: BAAI/bge-m3, "):
        embedder_for("no-such/model")
