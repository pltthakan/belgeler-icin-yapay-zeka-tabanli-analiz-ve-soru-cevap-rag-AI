#!/usr/bin/env python3
"""Offline, repeatable RAG quality and regression evaluation runner."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from evaluation.metrics import aggregate_results, evaluate_quality_gates, score_case
from rag_engine import RagEngine


def build_engine(data_dir: str, use_ollama: bool) -> RagEngine:
    engine = RagEngine(data_dir)
    engine._vector_store = None
    # Evaluation must not read or write shared runtime cache state.
    engine.cache._client = None

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


def validate_case(case: Dict[str, Any]) -> None:
    required_fields = ("id", "question", "chunks")
    missing = [field for field in required_fields if not case.get(field)]
    if missing:
        raise ValueError(f"Evaluation vakası eksik alan içeriyor: {case.get('id', '<unknown>')} {missing}")
    if case.get("evaluationMode", "pipeline") not in {"pipeline", "guard"}:
        raise ValueError(f"Geçersiz evaluationMode: {case['id']}")
    if case.get("evaluationMode") == "guard" and not case.get("candidateAnswer"):
        raise ValueError(f"Guard vakası candidateAnswer içermelidir: {case['id']}")


def case_sources(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "chunkIndex": index,
            "pageNumber": source.get("pageNumber", 1),
            "text": source["text"],
            "score": float(source.get("score", 1.0)),
        }
        for index, source in enumerate(case["chunks"])
    ]


def write_case_index(engine: RagEngine, case: Dict[str, Any]) -> str:
    document_id = f"evaluation-{case['id']}"
    chunks = case_sources(case)
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


def run_case(engine: RagEngine, case: Dict[str, Any], default_top_k: int) -> Dict[str, Any]:
    started_at = time.perf_counter()
    if case.get("evaluationMode", "pipeline") == "guard":
        sources = case_sources(case)
        response_mode = engine._classify_response_mode(case["question"])
        answer, trace = engine._finalize_answer_candidate(
            question=case["question"],
            answer=case["candidateAnswer"],
            sources=sources,
            response_mode=response_mode,
            generation={
                "provider": "evaluation-injected-answer",
                "model": "synthetic",
                "responseMode": response_mode,
                "prompt": None,
            },
        )
        result = {"answer": answer, "sources": sources, "trace": trace}
    else:
        document_id = write_case_index(engine, case)
        result = engine.answer_question(
            document_id=document_id,
            question=case["question"],
            top_k=int(case.get("topK", default_top_k)),
        )
    duration_ms = (time.perf_counter() - started_at) * 1000
    return score_case(case, result, duration_ms)


def load_cases(paths: List[Path]) -> List[Dict[str, Any]]:
    cases = []
    seen_ids = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload.get("cases", []):
            validate_case(case)
            if case["id"] in seen_ids:
                raise ValueError(f"Tekrarlanan evaluation vaka kimliği: {case['id']}")
            seen_ids.add(case["id"])
            cases.append(case)
    return cases


def write_report(path: Path, report: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def default_report_path() -> Path:
    configured_path = os.getenv("RAG_EVALUATION_REPORT_PATH", "").strip()
    if configured_path:
        return Path(configured_path)
    data_dir = os.getenv("DATA_DIR", "").strip()
    if data_dir:
        return Path(data_dir) / "evaluation" / "latest.json"
    return Path(__file__).with_name("reports") / "latest.json"


def print_report(report: Dict[str, Any]) -> None:
    for result in report["cases"]:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"[{status}] {result['id']} ({result['category']}/{result['evaluationMode']})")
        print(f"  retrieved={result['retrievedChunks']} expected={result['expectedSourceChunks']}")
        print(f"  answer={result['answer']}")
        if result["failures"]:
            print(f"  failures={result['failures']}")

    metrics = report["metrics"]
    retrieval = metrics["retrieval"]
    print("\nRAG evaluation summary")
    print(f"  cases:              {metrics['passedCases']}/{metrics['caseCount']}")
    print(f"  retrieval recall@k: {retrieval['recallAtK']:.1%}")
    print(f"  retrieval precision: {retrieval['precisionAtK']:.1%}")
    print(f"  retrieval MRR:      {retrieval['mrr']:.3f}")
    print(f"  answer correctness: {metrics['answerCorrectness']:.1%}")
    print(f"  groundedness:       {metrics['groundedness']:.1%}")
    print(f"  citation accuracy:  {metrics['citationAccuracy']:.1%}")
    print(f"  no-answer accuracy: {metrics['noAnswerAccuracy']:.1%}")
    print(f"  guard accuracy:     {metrics['guardAccuracy']:.1%}")
    print(f"  latency p50/p95:    {metrics['latencyMs']['p50']:.2f}/{metrics['latencyMs']['p95']:.2f} ms")
    for gate in report["qualityGates"]:
        status = "PASS" if gate["passed"] else "FAIL"
        print(f"  gate {status}: {gate['metric']}={gate['actual']:.4f} minimum={gate['minimum']:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Geniş RAG kalite ve regresyon değerlendirmesi")
    parser.add_argument("--with-ollama", action="store_true", help="Yerel Ollama modelini de değerlendirir.")
    parser.add_argument("--top-k", type=int, default=3, help="Pipeline vakalarında getirilecek kaynak sayısı.")
    parser.add_argument(
        "--output",
        type=Path,
        default=default_report_path(),
        help="JSON rapor yolu.",
    )
    parser.add_argument("--no-gates", action="store_true", help="Kalite kapıları başarısız olsa da sıfır koduyla çıkar.")
    args = parser.parse_args()

    evaluation_dir = Path(__file__).parent
    case_paths = [evaluation_dir / "cases.json", evaluation_dir / "guard_cases.json"]
    cases = load_cases(case_paths)
    gates = json.loads((evaluation_dir / "quality_gates.json").read_text(encoding="utf-8"))["minimums"]

    with tempfile.TemporaryDirectory(prefix="rag-evaluation-") as data_dir:
        engine = build_engine(data_dir=data_dir, use_ollama=args.with_ollama)
        results = [run_case(engine, case, args.top_k) for case in cases]

    metrics = aggregate_results(results)
    gate_decisions = evaluate_quality_gates(metrics, gates)
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "ollama" if args.with_ollama else "offline-deterministic",
        "datasets": [path.name for path in case_paths],
        "metrics": metrics,
        "qualityGates": gate_decisions,
        "cases": results,
    }
    write_report(args.output, report)
    print_report(report)
    print(f"\nJSON report: {args.output}")

    gates_passed = all(decision["passed"] for decision in gate_decisions)
    return 0 if args.no_gates or gates_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
