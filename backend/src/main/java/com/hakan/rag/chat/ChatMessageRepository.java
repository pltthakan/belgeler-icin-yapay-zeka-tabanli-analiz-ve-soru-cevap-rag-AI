package com.hakan.rag.chat;

import com.hakan.rag.document.DocumentFile;
import com.hakan.rag.user.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ChatMessageRepository extends JpaRepository<ChatMessage, Long> {
    List<ChatMessage> findByOwnerAndDocumentOrderByCreatedAtAsc(User owner, DocumentFile document);
    void deleteByDocument(DocumentFile document);
}
