package com.hakan.rag.chat.dto;

import jakarta.validation.constraints.NotBlank;

public record AskRequest(
        @NotBlank String question
) {}
