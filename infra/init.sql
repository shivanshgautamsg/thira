-- THIRA Database Initialization
-- This runs on first container start via docker-entrypoint-initdb.d

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;
