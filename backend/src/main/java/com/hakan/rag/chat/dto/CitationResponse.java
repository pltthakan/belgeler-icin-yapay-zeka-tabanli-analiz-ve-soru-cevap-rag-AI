package com.hakan.rag.chat.dto;

public record CitationResponse(
        Integer id,
        String claim,
        Integer sourceIndex,
        Integer pageNumber,
        Integer chunkIndex,
        String quote,
        Double coverage
) {}
