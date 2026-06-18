package com.hakan.rag.chat.dto;

import java.time.LocalDateTime;
import java.util.List;

public record ChatMessageResponse(
        Long id,
        String question,
        String answer,
        List<SourceResponse> sources,
        LocalDateTime createdAt
) {}
