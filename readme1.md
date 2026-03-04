# Create README.md using pypandoc as required for markdown generation

import pypandoc

readme_md = r"""
# RAG_MODEL — Local PDF AI Chat System

A full-stack Retrieval Augmented Generation (RAG) system that allows users to:

- Register & Login
- Upload PDF documents
- Automatically create embeddings
- Ask questions about the PDF
- Get answers using local AI models

The system uses local embeddings + Ollama LLM, meaning **no OpenAI API key is required**.

---

# Architecture

React Frontend  
↓  
Flask API (JWT Auth)  
↓  
PDF Upload → AWS S3  
↓  
Background Worker  
↓  
LangChain + HuggingFace Embeddings  
↓  
FAISS Vector Store  
↓  
Ollama Local LLM

---

# Tech Stack

## Frontend
- React
- Axios
- JWT Authentication

## Backend
- Flask
- Flask-JWT-Extended
- SQLAlchemy
- Redis (for caching)
- LangChain

## AI / ML
- HuggingFace Embeddings
- FAISS Vector Database
- Ollama Local LLM

## Storage
- AWS S3

---

# Project Structure

RAG_MODEL
├── backend  
│   ├── app  
│   │   ├── models  
│   │   ├── routes  
│   │   │   ├── auth.py  
│   │   │   ├── pdf.py  
│   │   │   ├── chat.py  
│   │   │   └── history.py  
│   │   ├── services  
│   │   │   ├── rag_service.py  
│   │   │   └── s3_service.py  
│   │   └── __init__.py  
│   ├── requirements.txt  
│   ├── run.py  
│   └── venv  

├── frontend  
│   ├── src  
│   ├── package.json  
│   └── Dockerfile  

├── training_data  
│   ├── process_pdf.py  
│   └── requirements.txt  

├── docker-compose.yml  
└── README.md

---

# Installation Guide

## Clone Repository

git clone https://github.com/YOUR_REPO/RAG_MODEL.git  
cd RAG_MODEL

---

# Backend Setup

cd backend

### Create Virtual Environment

python3 -m venv venv

Activate environment:

source venv/bin/activate

Terminal should show:

(venv)

---

### Install Dependencies

pip install -r requirements.txt

Main libraries:

- Flask
- SQLAlchemy
- LangChain
- FAISS
- Redis
- Sentence Transformers
- boto3

---

# Install Ollama (Local LLM)

Download Ollama:

https://ollama.ai

Start server:

ollama serve

Download model:

ollama pull mistral

---

# Embedding Model

System automatically downloads:

sentence-transformers/all-MiniLM-L6-v2

on first run.

---

# Environment Variables

Create `.env` inside backend.

Example:

FLASK_ENV=development

SECRET_KEY=supersecret

JWT_SECRET_KEY=jwtsecret

DATABASE_URL=sqlite:///rag_app.db

REDIS_URL=redis://localhost:6379

VECTOR_STORE_DIR=./vector_stores

OLLAMA_MODEL=mistral  
OLLAMA_URL=http://localhost:11434

AWS_ACCESS_KEY_ID=YOUR_KEY  
AWS_SECRET_ACCESS_KEY=YOUR_SECRET  
AWS_REGION=us-east-1  
AWS_S3_BUCKET=rag-pdf-storage

---

# Database

SQLite database automatically created:

instance/rag_app.db

---

# Run Backend

source venv/bin/activate  
python3 run.py

Server:

http://localhost:5005

---

# Frontend Setup

cd frontend

Install dependencies:

npm install

Run frontend:

npm start

Frontend URL:

http://localhost:3000

---

# Authentication Flow

### Register

POST /api/auth/register

Fields:

name  
email  
password

---

### Login

POST /api/auth/login

Returns JWT token.

Token stored in localStorage.

---

### Authenticated Requests

Authorization header:

Authorization: Bearer TOKEN

---

# PDF Upload Flow

POST /api/pdf/upload

Steps:

1. Upload PDF
2. Stored in AWS S3
3. Temporary local file created
4. Background processing starts
5. Text chunks created
6. Embeddings generated
7. Stored in FAISS vector database

---

# Check PDF Processing

GET /api/pdf/status/<pdf_id>

Returns:

pending  
processing  
ready  
failed

---

# Chat With PDF

### Create Session

POST /api/chat/session

### Ask Question

POST /api/chat/message

Example JSON:

{
  "session_id": "...",
  "question": "What is the main topic?"
}

---

# RAG Pipeline

User Question  
↓  
FAISS Vector Search  
↓  
Relevant Document Chunks  
↓  
Prompt Construction  
↓  
Ollama LLM  
↓  
Generated Answer

---

# Chat History

GET /api/chat/session/<id>/messages

Stored in:

SQLite database

Cached in:

Redis

---

# Delete PDF

DELETE /api/pdf/<id>

Deletes:

- S3 file
- FAISS index
- Database record

---

# Download PDF

GET /api/pdf/<id>/download

Returns presigned S3 URL.

---

# Performance Optimizations

- Redis caching
- FAISS vector search
- Background PDF processing
- Local LLM inference

---

# Troubleshooting

## Redis error

pip install redis

---

## Sentence Transformers error

pip install sentence-transformers

---

## Ollama not responding

Run:

ollama serve

---

## Python command not found

Use:

python3

---

# License

MIT License

---

# Author

Shivansh Mishra  

Founder — Glocybs  

AI | Quantum Computing | Cybersecurity
"""

output_path = "/mnt/data/README.md"
pypandoc.convert_text(readme_md, "md", format="md", outputfile=output_path, extra_args=["--standalone"])

output_path