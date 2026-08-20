import os
from pathlib import Path
import re

import chromadb
import ollama
from dotenv import load_dotenv


POLICY_PATH = Path(__file__).resolve().parent / "policies" / "sla_policy.md"
SOURCE = "policies/sla_policy.md"
VECTORSTORE_PATH = Path(__file__).resolve().parent / "vectorstore"
COLLECTION_NAME = "reg_policies"
TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)

load_dotenv()
ollama_client = ollama.Client(
    host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
)
chroma_client = chromadb.PersistentClient(path=str(VECTORSTORE_PATH))
collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)


def estimate_tokens(text: str) -> int:
    """Use a small tokenizer estimate without adding another dependency."""
    return len(TOKEN_PATTERN.findall(text))


def markdown_blocks(markdown: str) -> list[dict]:
    """Keep each heading with its following paragraph."""
    sections = re.split(r"(?m)(?=^#{1,6}\s+)", markdown.strip())
    blocks = []

    for section in sections:
        if not section.strip():
            continue

        lines = section.splitlines()
        heading = ""
        body_lines = lines

        if re.match(r"^#{1,6}\s+", lines[0]):
            heading = lines[0].strip()
            body_lines = lines[1:]

        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", "\n".join(body_lines))
            if paragraph.strip()
        ]

        if not paragraphs:
            paragraphs = [""]

        for number, paragraph in enumerate(paragraphs):
            text = paragraph
            if number == 0 and heading:
                text = f"{heading}\n{paragraph}".strip()

            blocks.append(
                {
                    "text": text,
                    "section": heading.removeprefix("#").strip(),
                }
            )

    return blocks


def chunk_markdown(
    markdown: str,
    min_tokens: int = 400,
    max_tokens: int = 800,
    overlap_ratio: float = 0.125,
    source: str = SOURCE,
) -> list[dict]:
    blocks = markdown_blocks(markdown)
    overlap_target = int(((min_tokens + max_tokens) / 2) * overlap_ratio)

    chunks = []
    start = 0

    while start < len(blocks):
        end = start
        token_count = 0

        while end < len(blocks):
            if (
                end > start
                and blocks[end]["section"] != blocks[start]["section"]
            ):
                break

            block_tokens = estimate_tokens(blocks[end]["text"])

            if (
                end > start
                and token_count >= min_tokens
                and token_count + block_tokens > max_tokens
            ):
                break

            token_count += block_tokens
            end += 1

            if end < len(blocks) and token_count >= min_tokens:
                next_tokens = estimate_tokens(blocks[end]["text"])
                if token_count + next_tokens > max_tokens:
                    break

        chunk_blocks = blocks[start:end]
        chunk_number = len(chunks) + 1
        chunk_id = f"{source}:chunk-{chunk_number:04d}"

        chunks.append(
            {
                "id": chunk_id,
                "text": "\n\n".join(block["text"] for block in chunk_blocks),
                "metadata": {
                    "source": source,
                    "chunk_id": chunk_id,
                    "section": chunk_blocks[0]["section"],
                    "token_count": token_count,
                },
            }
        )

        if end == len(blocks):
            break

        if blocks[end]["section"] != blocks[end - 1]["section"]:
            start = end
            continue

        overlap_start = end
        overlap_tokens = 0
        while overlap_start > start:
            previous_tokens = estimate_tokens(blocks[overlap_start - 1]["text"])
            if overlap_tokens and overlap_tokens + previous_tokens > overlap_target:
                break
            overlap_start -= 1
            overlap_tokens += previous_tokens

        start = overlap_start

    return chunks


def load_policy_chunks() -> list[dict]:
    markdown = POLICY_PATH.read_text(encoding="utf-8")
    return chunk_markdown(markdown, source=SOURCE)


def embed_chunks(chunks: list[dict]) -> list[list[float]]:
    response = ollama_client.embed(
        model=os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding"),
        input=[chunk["text"] for chunk in chunks],
    )
    return response["embeddings"]


def index_policy() -> int:
    chunks = load_policy_chunks()
    embeddings = embed_chunks(chunks)

    collection.upsert(
        ids=[chunk["id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        embeddings=embeddings,
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    return len(chunks)


def search_policy(question: str, k: int = 4) -> dict:
    question_embedding = embed_chunks([{"text": question}])[0]
    return collection.query(
        query_embeddings=[question_embedding],
        n_results=k,
    )


if __name__ == "__main__":
    print(search_policy("What is the return policy?"))
