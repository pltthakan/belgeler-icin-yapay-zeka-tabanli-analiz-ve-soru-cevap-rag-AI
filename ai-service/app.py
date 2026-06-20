import os
from flask import Flask, jsonify, request
from flask_cors import CORS

from rag_engine import RagEngine

app = Flask(__name__)
CORS(app)

DATA_DIR = os.getenv("DATA_DIR", "./data")
rag_engine = RagEngine(data_dir=DATA_DIR)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "UP",
        "service": "private-document-rag-ai-service",
        "embeddingModel": rag_engine.embedding_model_name,
        "qaModel": rag_engine.qa_model_name,
        "localLlmEnabled": bool(rag_engine.ollama_base_url and rag_engine.ollama_model),
        "vectorStore": "pgvector" if rag_engine._vector_store is not None else "json-fallback",
    })


@app.post("/api/ingest")
def ingest():
    document_id = request.form.get("documentId")
    owner_id = request.form.get("ownerId")
    department_id = request.form.get("departmentId")
    file = request.files.get("file")

    if not document_id:
        return jsonify({"message": "documentId zorunludur."}), 400
    if file is None:
        return jsonify({"message": "file zorunludur."}), 400

    try:
        result = rag_engine.ingest_document(
            document_id=document_id,
            file_storage=file,
            owner_id=owner_id,
            department_id=department_id,
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"message": str(exc)}), 500


@app.post("/api/ask")
def ask():
    payload = request.get_json(silent=True) or {}
    document_id = payload.get("documentId")
    question = payload.get("question")
    top_k = int(payload.get("topK") or 4)

    if not document_id:
        return jsonify({"message": "documentId zorunludur."}), 400
    if not question:
        return jsonify({"message": "question zorunludur."}), 400

    try:
        result = rag_engine.answer_question(document_id=document_id, question=question, top_k=top_k)
        return jsonify(result)
    except FileNotFoundError:
        return jsonify({"message": "Bu belge için vektör indeksi bulunamadı."}), 404
    except Exception as exc:
        return jsonify({"message": str(exc)}), 500


@app.delete("/api/index/<document_id>")
def delete_index(document_id):
    try:
        rag_engine.delete_document(document_id)
        return jsonify({"documentId": document_id, "deleted": True})
    except Exception as exc:
        return jsonify({"message": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
