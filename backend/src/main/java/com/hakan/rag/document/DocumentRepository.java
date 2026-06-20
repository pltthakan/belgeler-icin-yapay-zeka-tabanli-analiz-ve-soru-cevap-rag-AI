package com.hakan.rag.document;

import com.hakan.rag.department.Department;
import com.hakan.rag.user.User;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface DocumentRepository extends JpaRepository<DocumentFile, Long> {
    @EntityGraph(attributePaths = {"owner", "department"})
    List<DocumentFile> findByOwnerOrderByCreatedAtDesc(User owner);

    @EntityGraph(attributePaths = {"owner", "department"})
    Optional<DocumentFile> findByIdAndOwner(Long id, User owner);

    @EntityGraph(attributePaths = {"owner", "department"})
    Optional<DocumentFile> findById(Long id);

    @EntityGraph(attributePaths = {"owner", "department"})
    List<DocumentFile> findByDepartmentAndSharingScopeOrderByCreatedAtDesc(
            Department department,
            DocumentSharingScope sharingScope
    );

    @EntityGraph(attributePaths = {"owner", "department"})
    List<DocumentFile> findAllByOrderByCreatedAtDesc();
}
