package com.hakan.rag.document;

import com.hakan.rag.user.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DocumentRepository extends JpaRepository<DocumentFile, Long> {
    List<DocumentFile> findByOwnerOrderByCreatedAtDesc(User owner);
    Optional<DocumentFile> findByIdAndOwner(Long id, User owner);
}
