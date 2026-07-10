package com.hakan.rag.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMqConfig {
    @Value("${app.rabbitmq.document-processing.exchange}")
    private String documentProcessingExchange;

    @Value("${app.rabbitmq.document-processing.queue}")
    private String documentProcessingQueue;

    @Value("${app.rabbitmq.document-processing.routing-key}")
    private String documentProcessingRoutingKey;

    @Value("${app.rabbitmq.document-processing.retry-exchange}")
    private String documentProcessingRetryExchange;

    @Value("${app.rabbitmq.document-processing.retry-queue}")
    private String documentProcessingRetryQueue;

    @Value("${app.rabbitmq.document-processing.retry-routing-key}")
    private String documentProcessingRetryRoutingKey;

    @Value("${app.rabbitmq.document-processing.retry-delay-ms}")
    private int documentProcessingRetryDelayMs;

    @Value("${app.rabbitmq.document-processing.dead-letter-exchange}")
    private String documentProcessingDeadLetterExchange;

    @Value("${app.rabbitmq.document-processing.dead-letter-queue}")
    private String documentProcessingDeadLetterQueue;

    @Value("${app.rabbitmq.document-processing.dead-letter-routing-key}")
    private String documentProcessingDeadLetterRoutingKey;

    @Bean
    public DirectExchange documentProcessingExchange() {
        return new DirectExchange(documentProcessingExchange, true, false);
    }

    @Bean
    public DirectExchange documentProcessingRetryExchange() {
        return new DirectExchange(documentProcessingRetryExchange, true, false);
    }

    @Bean
    public DirectExchange documentProcessingDeadLetterExchange() {
        return new DirectExchange(documentProcessingDeadLetterExchange, true, false);
    }

    @Bean
    public Queue documentProcessingQueue() {
        return QueueBuilder.durable(documentProcessingQueue)
                .deadLetterExchange(documentProcessingDeadLetterExchange)
                .deadLetterRoutingKey(documentProcessingDeadLetterRoutingKey)
                .build();
    }

    @Bean
    public Queue documentProcessingRetryQueue() {
        return QueueBuilder.durable(documentProcessingRetryQueue)
                .ttl(documentProcessingRetryDelayMs)
                .deadLetterExchange(documentProcessingExchange)
                .deadLetterRoutingKey(documentProcessingRoutingKey)
                .build();
    }

    @Bean
    public Queue documentProcessingDeadLetterQueue() {
        return QueueBuilder.durable(documentProcessingDeadLetterQueue).build();
    }

    @Bean
    public Binding documentProcessingBinding(
            @Qualifier("documentProcessingQueue") Queue documentProcessingQueue,
            @Qualifier("documentProcessingExchange") DirectExchange documentProcessingExchange
    ) {
        return BindingBuilder
                .bind(documentProcessingQueue)
                .to(documentProcessingExchange)
                .with(documentProcessingRoutingKey);
    }

    @Bean
    public Binding documentProcessingRetryBinding(
            @Qualifier("documentProcessingRetryQueue") Queue documentProcessingRetryQueue,
            @Qualifier("documentProcessingRetryExchange") DirectExchange documentProcessingRetryExchange
    ) {
        return BindingBuilder
                .bind(documentProcessingRetryQueue)
                .to(documentProcessingRetryExchange)
                .with(documentProcessingRetryRoutingKey);
    }

    @Bean
    public Binding documentProcessingDeadLetterBinding(
            @Qualifier("documentProcessingDeadLetterQueue") Queue documentProcessingDeadLetterQueue,
            @Qualifier("documentProcessingDeadLetterExchange") DirectExchange documentProcessingDeadLetterExchange
    ) {
        return BindingBuilder
                .bind(documentProcessingDeadLetterQueue)
                .to(documentProcessingDeadLetterExchange)
                .with(documentProcessingDeadLetterRoutingKey);
    }

    @Bean
    public Jackson2JsonMessageConverter jackson2JsonMessageConverter(ObjectMapper objectMapper) {
        return new Jackson2JsonMessageConverter(objectMapper);
    }

    @Bean
    public RabbitTemplate rabbitTemplate(ConnectionFactory connectionFactory, Jackson2JsonMessageConverter messageConverter) {
        RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
        rabbitTemplate.setMessageConverter(messageConverter);
        return rabbitTemplate;
    }
}
