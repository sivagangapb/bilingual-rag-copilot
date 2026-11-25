"""Run once while building the Docker image: build chunks, download models, cache embeddings.

Then the container starts fast and never downloads anything at runtime.
"""
from build_chunks import main as build_chunks
from retrievers import EmbeddingRetriever, Reranker, load_corpus

if __name__ == "__main__":
    build_chunks()
    for lang in ["en", "de"]:
        EmbeddingRetriever(load_corpus(lang), lang)    # downloads e5 + saves the .npy cache
    Reranker()                                         # downloads the reranker
    print("warm-up done")
