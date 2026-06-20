package com.hakan.rag.document.dto;

import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.document.DocumentSharingScope;
import com.hakan.rag.document.DocumentStatus;

import java.time.LocalDateTime;

public record DocumentResponse(
        Long id,
        Long ownerId,
        String originalFilename,
        String contentType,
        Long fileSize,
        DocumentStatus status,
        Integer chunkCount,
        String errorMessage,
        DocumentSharingScope sharingScope,
        Long departmentId,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    public static DocumentResponse from(DocumentFile document) {
        return new DocumentResponse(
                document.getId(),
                document.getOwner().getId(),
                document.getOriginalFilename(),
                document.getContentType(),
                document.getFileSize(),
                document.getStatus(),
                document.getChunkCount(),
                document.getErrorMessage(),
                document.getSharingScope(),
                document.getDepartment() == null ? null : document.getDepartment().getId(),
                document.getCreatedAt(),
                document.getUpdatedAt()
        );
    }
}
