from pathlib import Path

import rag


PROJECT_ROOT = Path(__file__).resolve().parent
POLICIES_PATH = PROJECT_ROOT / "policies"


def read_policy_chunks() -> tuple[list[Path], list[dict]]:
    documents = sorted(POLICIES_PATH.rglob("*.md"))
    chunks = []

    for document in documents:
        source = document.relative_to(PROJECT_ROOT).as_posix()
        markdown = document.read_text(encoding="utf-8")
        chunks.extend(rag.chunk_markdown(markdown, source=source))

    return documents, chunks


def rebuild_collection(chunks: list[dict]) -> None:
    embeddings = rag.embed_chunks(chunks)

    rag.chroma_client.delete_collection(rag.COLLECTION_NAME)
    collection = rag.chroma_client.get_or_create_collection(
        name=rag.COLLECTION_NAME
    )
    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=embeddings,
        metadatas=[chunk["metadata"] for chunk in chunks],
    )


def main() -> None:
    documents, chunks = read_policy_chunks()

    if chunks:
        rebuild_collection(chunks)

    print(f"Indexed {len(documents)} documents and {len(chunks)} chunks.")


if __name__ == "__main__":
    main()
