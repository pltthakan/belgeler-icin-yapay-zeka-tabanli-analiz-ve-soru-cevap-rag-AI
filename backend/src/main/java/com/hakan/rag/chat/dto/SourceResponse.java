package com.hakan.rag.chat.dto;

public record SourceResponse(
        Integer pageNumber,
        Integer chunkIndex,
        Double score,
        String text
) {}
