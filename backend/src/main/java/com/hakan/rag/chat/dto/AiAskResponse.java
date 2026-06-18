package com.hakan.rag.chat.dto;

import java.util.List;

public record AiAskResponse(
        String answer,
        List<SourceResponse> sources
) {}
