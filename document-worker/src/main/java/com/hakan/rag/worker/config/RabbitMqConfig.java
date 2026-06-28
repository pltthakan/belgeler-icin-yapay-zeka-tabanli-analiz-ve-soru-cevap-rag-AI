package com.hakan.rag.worker.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.amqp.SimpleRabbitListenerContainerFactoryConfigurer;
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

    @Bean
    public DirectExchange documentProcessingExchange() {
        return new DirectExchange(documentProcessingExchange, true, false);
    }

    @Bean
    public Queue documentProcessingQueue() {
        return new Queue(documentProcessingQueue, true);
    }

    @Bean
    public Binding documentProcessingBinding(Queue documentProcessingQueue, DirectExchange documentProcessingExchange) {
        return BindingBuilder
                .bind(documentProcessingQueue)
                .to(documentProcessingExchange)
                .with(documentProcessingRoutingKey);
    }

    @Bean
    public Jackson2JsonMessageConverter jackson2JsonMessageConverter(ObjectMapper objectMapper) {
        return new Jackson2JsonMessageConverter(
                objectMapper,
                "com.hakan.rag.document",
                "com.hakan.rag.document.queue"
        );
    }

    @Bean
    public SimpleRabbitListenerContainerFactory rabbitListenerContainerFactory(
            SimpleRabbitListenerContainerFactoryConfigurer configurer,
            ConnectionFactory connectionFactory,
            Jackson2JsonMessageConverter messageConverter
    ) {
        SimpleRabbitListenerContainerFactory factory = new SimpleRabbitListenerContainerFactory();
        configurer.configure(factory, connectionFactory);
        factory.setMessageConverter(messageConverter);
        return factory;
    }
}
