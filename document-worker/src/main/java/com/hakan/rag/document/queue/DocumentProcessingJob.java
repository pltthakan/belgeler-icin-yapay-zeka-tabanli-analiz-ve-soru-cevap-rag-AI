package com.hakan.rag.document.queue;

import com.hakan.rag.document.DocumentStatus;

public record DocumentProcessingJob(
        Long documentId,
        Long ownerId,
        Long departmentId,
        String storedPath,
        String originalFilename,
        DocumentProcessingOperation operation,
        DocumentStatus previousStatus
) {}
