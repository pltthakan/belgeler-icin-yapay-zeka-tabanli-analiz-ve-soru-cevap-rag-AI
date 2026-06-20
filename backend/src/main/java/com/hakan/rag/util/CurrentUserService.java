package com.hakan.rag.util;

import com.hakan.rag.user.User;
import com.hakan.rag.user.UserRepository;
import com.hakan.rag.user.UserRole;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class CurrentUserService {

    private final UserRepository userRepository;

    public CurrentUserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public User getCurrentUser() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || authentication.getName() == null) {
            throw new IllegalArgumentException("Kimlik doğrulama bilgisi bulunamadı.");
        }
        return userRepository.findWithDepartmentByEmail(authentication.getName())
                .orElseThrow(() -> new IllegalArgumentException("Kullanıcı bulunamadı."));
    }

    public User requireAdmin() {
        User user = getCurrentUser();
        if (user.getRole() != UserRole.ADMIN) {
            throw new IllegalArgumentException("Bu işlem için yönetici yetkisi gerekir.");
        }
        return user;
    }
}
