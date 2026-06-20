package com.hakan.rag.user;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class BootstrapAdminInitializer implements ApplicationRunner {
    private final UserRepository userRepository;
    private final String bootstrapAdminEmail;

    public BootstrapAdminInitializer(
            UserRepository userRepository,
            @Value("${app.bootstrap-admin-email:}") String bootstrapAdminEmail
    ) {
        this.userRepository = userRepository;
        this.bootstrapAdminEmail = bootstrapAdminEmail == null ? "" : bootstrapAdminEmail.trim();
    }

    @Override
    public void run(ApplicationArguments args) {
        if (bootstrapAdminEmail.isBlank()) {
            return;
        }
        userRepository.findByEmail(bootstrapAdminEmail.toLowerCase())
                .filter(user -> user.getRole() != UserRole.ADMIN)
                .ifPresent(user -> {
                    user.setRole(UserRole.ADMIN);
                    userRepository.save(user);
                });
    }
}
