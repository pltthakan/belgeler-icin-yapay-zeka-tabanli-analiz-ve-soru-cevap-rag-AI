package com.hakan.rag.auth.dto;

import com.hakan.rag.user.UserRole;

public record AuthResponse(
        String token,
        Long userId,
        String name,
        String email,
        UserRole role
) {}
