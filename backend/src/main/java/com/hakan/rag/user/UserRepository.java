package com.hakan.rag.user;

import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmail(String email);

    @EntityGraph(attributePaths = "department")
    Optional<User> findWithDepartmentByEmail(String email);

    boolean existsByEmail(String email);

    @Override
    @EntityGraph(attributePaths = "department")
    java.util.List<User> findAll();
}
