package com.hakan.rag.document.dto;

public record AiIngestResponse(
        String documentId,
        Integer chunkCount,
        String message
) {}
