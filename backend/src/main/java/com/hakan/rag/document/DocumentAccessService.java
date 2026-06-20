package com.hakan.rag.document;

import com.hakan.rag.user.User;
import com.hakan.rag.user.UserRole;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class DocumentAccessService {

    private final DocumentRepository documentRepository;

    public DocumentAccessService(DocumentRepository documentRepository) {
        this.documentRepository = documentRepository;
    }

    @Transactional(readOnly = true)
    public List<DocumentFile> listAccessibleDocuments(User user) {
        if (user.getRole() == UserRole.ADMIN) {
            return documentRepository.findAllByOrderByCreatedAtDesc();
        }

        Map<Long, DocumentFile> visible = new LinkedHashMap<>();
        for (DocumentFile document : documentRepository.findByOwnerOrderByCreatedAtDesc(user)) {
            visible.put(document.getId(), document);
        }
        if (user.getDepartment() != null) {
            for (DocumentFile document : documentRepository.findByDepartmentAndSharingScopeOrderByCreatedAtDesc(
                    user.getDepartment(), DocumentSharingScope.DEPARTMENT)) {
                visible.putIfAbsent(document.getId(), document);
            }
        }
        return List.copyOf(visible.values());
    }

    @Transactional(readOnly = true)
    public DocumentFile getAccessibleDocument(Long documentId, User user) {
        DocumentFile document = documentRepository.findById(documentId)
                .orElseThrow(() -> new IllegalArgumentException("Belge bulunamadı."));
        if (!canAccess(document, user)) {
            throw new IllegalArgumentException("Bu belgeye erişim yetkiniz yok.");
        }
        return document;
    }

    @Transactional(readOnly = true)
    public DocumentFile getManageableDocument(Long documentId, User user) {
        DocumentFile document = getAccessibleDocument(documentId, user);
        if (user.getRole() != UserRole.ADMIN && !document.getOwner().getId().equals(user.getId())) {
            throw new IllegalArgumentException("Bu belgeyi yönetme yetkiniz yok.");
        }
        return document;
    }

    @Transactional(readOnly = true)
    public DocumentFile getReindexableDocument(Long documentId, User user) {
        DocumentFile document = getAccessibleDocument(documentId, user);
        if (user.getRole() == UserRole.ADMIN || document.getOwner().getId().equals(user.getId())) {
            return document;
        }
        if (user.getRole() == UserRole.MANAGER
                && document.getSharingScope() == DocumentSharingScope.DEPARTMENT
                && document.getDepartment() != null
                && user.getDepartment() != null
                && document.getDepartment().getId().equals(user.getDepartment().getId())) {
            return document;
        }
        throw new IllegalArgumentException("Bu belgeyi yeniden indeksleme yetkiniz yok.");
    }

    private boolean canAccess(DocumentFile document, User user) {
        if (user.getRole() == UserRole.ADMIN || document.getOwner().getId().equals(user.getId())) {
            return true;
        }
        return document.getSharingScope() == DocumentSharingScope.DEPARTMENT
                && document.getDepartment() != null
                && user.getDepartment() != null
                && document.getDepartment().getId().equals(user.getDepartment().getId());
    }
}
