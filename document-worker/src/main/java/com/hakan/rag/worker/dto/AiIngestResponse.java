package com.hakan.rag.worker.dto;

public record AiIngestResponse(
        String documentId,
        Integer chunkCount,
        String message
) {}
