package com.hakan.rag.document.dto;

import com.hakan.rag.document.DocumentSharingScope;
import jakarta.validation.constraints.NotNull;

public record DocumentSharingRequest(@NotNull DocumentSharingScope sharingScope) {
}
