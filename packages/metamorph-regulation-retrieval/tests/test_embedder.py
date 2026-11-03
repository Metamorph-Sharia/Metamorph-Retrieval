from metamorph_regulation_retrieval.embedder import SentenceTransformerEmbedder


class Model:
    def __init__(self) -> None:
        self.encoded: list[list[str]] = []

    def encode(self, texts, normalize_embeddings, show_progress_bar):  # noqa: ANN001, ANN201
        self.encoded.append(texts)
        return [[0.5, 0.5]]


def test_a_question_is_embedded_once() -> None:
    model = Model()
    embedder = SentenceTransformerEmbedder(model=model)

    assert embedder.encode("batas pendanaan") == embedder.encode("batas pendanaan") == (0.5, 0.5)
    assert model.encoded == [["batas pendanaan"]]
