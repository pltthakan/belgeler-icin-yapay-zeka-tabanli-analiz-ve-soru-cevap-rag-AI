package com.hakan.rag.document.dto;

import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.document.DocumentStatus;

import java.time.LocalDateTime;

public record DocumentResponse(
        Long id,
        String originalFilename,
        String contentType,
        Long fileSize,
        DocumentStatus status,
        Integer chunkCount,
        String errorMessage,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static DocumentResponse from(DocumentFile document) {
        return new DocumentResponse(
                document.getId(),
                document.getOriginalFilename(),
                document.getContentType(),
                document.getFileSize(),
                document.getStatus(),
                document.getChunkCount(),
                document.getErrorMessage(),
                document.getCreatedAt(),
                document.getUpdatedAt()
        );
    }
}
