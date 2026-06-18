package com.hakan.rag.auth.dto;

public record AuthResponse(
        String token,
        Long userId,
        String name,
        String email
) {}
