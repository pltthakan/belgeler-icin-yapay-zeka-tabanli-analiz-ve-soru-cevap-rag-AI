#!/usr/bin/env python3
"""Tekrarlanabilir, kişisel veri içermeyen RAG retrieval/cevap regresyon değerlendirmesi."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from rag_engine import RagEngine


def build_engine(data_dir: str, use_ollama: bool) -> RagEngine:
    engine = RagEngine(data_dir)

    # Değerlendirmenin ağ/model indirmelerine bağlı olmaması için retrieval
    # tarafında deterministik hashing embedding kullanılır.
    def hash_embed(texts):
        return engine._hashing_vectorizer.transform(texts).toarray()

    engine._embed_texts = hash_embed
    if not use_ollama:
        engine.ollama_base_url = ""
        engine.ollama_model = ""
        engine.disable_qa_model = True
    elif not (engine.ollama_base_url and engine.ollama_model):
        raise RuntimeError("--with-ollama için OLLAMA_BASE_URL ve OLLAMA_MODEL ayarlanmalıdır.")
    return engine


def write_case_index(engine: RagEngine, case: dict) -> str:
    document_id = f"evaluation-{case['id']}"
    chunks = []
    for index, source in enumerate(case["chunks"]):
        chunks.append({
            "chunkIndex": index,
            "pageNumber": source.get("pageNumber", 1),
            "text": source["text"],
        })

    embeddings = engine._embed_texts([chunk["text"] for chunk in chunks])
    payload = {
        "documentId": document_id,
        "filename": f"{case['id']}.txt",
        "chunkCount": len(chunks),
        "chunks": chunks,
        "embeddings": embeddings.tolist(),
        "documentProfile": engine._build_document_profile(chunks),
    }
    engine._index_path(document_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return document_id


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def evaluate_case(engine: RagEngine, case: dict) -> dict:
    document_id = write_case_index(engine, case)
    result = engine.answer_question(document_id=document_id, question=case["question"], top_k=3)
    retrieved_chunks = [source["chunkIndex"] for source in result["sources"]]
    expected_chunks = set(case["expectedSourceChunks"])
    retrieved_expected_chunks = expected_chunks.issubset(set(retrieved_chunks))

    normalized_answer = normalize(result["answer"])
    missing_terms = [
        term for term in case.get("requiredAnswerTerms", [])
        if normalize(term) not in normalized_answer
    ]
    return {
        "id": case["id"],
        "passed": retrieved_expected_chunks and not missing_terms,
        "retrievedChunks": retrieved_chunks,
        "expectedSourceChunks": sorted(expected_chunks),
        "missingAnswerTerms": missing_terms,
        "answer": result["answer"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG regression evaluation runner")
    parser.add_argument(
        "--with-ollama",
        action="store_true",
        help="Cevap üretiminde yapılandırılmış yerel Ollama modelini de kullanır.",
    )
    args = parser.parse_args()

    cases_path = Path(__file__).with_name("cases.json")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))["cases"]

    with tempfile.TemporaryDirectory(prefix="rag-evaluation-") as data_dir:
        engine = build_engine(data_dir=data_dir, use_ollama=args.with_ollama)
        results = [evaluate_case(engine, case) for case in cases]

    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']}")
        print(f"  retrieved={result['retrievedChunks']} expected={result['expectedSourceChunks']}")
        print(f"  answer={result['answer']}")
        if result["missingAnswerTerms"]:
            print(f"  missing_terms={result['missingAnswerTerms']}")

    passed = sum(result["passed"] for result in results)
    print(f"\nRAG evaluation: {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
