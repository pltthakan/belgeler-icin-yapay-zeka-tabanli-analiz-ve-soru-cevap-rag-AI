package com.hakan.rag.chat.dto;

import java.util.List;
import java.util.Map;

public record AiAskResponse(
        String answer,
        List<SourceResponse> sources,
        Map<String, Object> trace
) {}
