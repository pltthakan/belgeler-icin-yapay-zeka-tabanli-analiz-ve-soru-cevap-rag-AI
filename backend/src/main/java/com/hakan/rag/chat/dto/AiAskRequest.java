package com.hakan.rag.chat.dto;

public record AiAskRequest(
        String documentId,
        String question,
        Integer topK
) {}
