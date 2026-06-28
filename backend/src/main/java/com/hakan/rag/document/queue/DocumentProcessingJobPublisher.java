package com.hakan.rag.document.queue;

import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentProcessingJobPublisher {
    private final RabbitTemplate rabbitTemplate;
    private final String exchange;
    private final String routingKey;

    public DocumentProcessingJobPublisher(
            RabbitTemplate rabbitTemplate,
            @Value("${app.rabbitmq.document-processing.exchange}") String exchange,
            @Value("${app.rabbitmq.document-processing.routing-key}") String routingKey
    ) {
        this.rabbitTemplate = rabbitTemplate;
        this.exchange = exchange;
        this.routingKey = routingKey;
    }

    public void publish(DocumentProcessingJob job) {
        rabbitTemplate.convertAndSend(exchange, routingKey, job);
    }
}
