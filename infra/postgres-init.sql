-- Database-per-service: each microservice owns its schema and nobody else reads it.
CREATE DATABASE identity;
CREATE DATABASE catalog;
CREATE DATABASE orders;
CREATE DATABASE notifications;
