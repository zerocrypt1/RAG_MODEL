# 📄 RAG PDF — AI-Powered Document Q&A

> Upload PDFs, ask questions, get intelligent answers powered by RAG (Retrieval-Augmented Generation)

![Stack](https://img.shields.io/badge/Frontend-React-61DAFB?style=flat-square&logo=react)
![Stack](https://img.shields.io/badge/Backend-Flask-000000?style=flat-square&logo=flask)
![Stack](https://img.shields.io/badge/AI-LangChain%20%2B%20OpenAI-412991?style=flat-square)
![Stack](https://img.shields.io/badge/Storage-AWS%20S3-FF9900?style=flat-square&logo=amazon-s3)
![Stack](https://img.shields.io/badge/Cache-Redis-DC382D?style=flat-square&logo=redis)
![Stack](https://img.shields.io/badge/Auth-JWT%20%2B%20Google-4285F4?style=flat-square&logo=google)
![Stack](https://img.shields.io/badge/Deploy-Docker-2496ED?style=flat-square&logo=docker)

---

## 🗂️ Project Structure

```
rag-pdf-app/
├── frontend/               # React application
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   │   └── Layout.jsx  # Sidebar layout
│   │   ├── context/
│   │   │   └── AuthContext.jsx
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── RegisterPage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── ChatPage.jsx
│   │   │   └── HistoryPage.jsx
│   │   └── utils/
│   │       └── api.js      # Axios API client
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── backend/                # Flask Python API
│   ├── app/
│   │   ├── models/         # SQLAlchemy models
│   │   ├── routes/
│   │   │   ├── auth.py     # JWT + Google OAuth
│   │   │   ├── pdf.py      # PDF upload (AWS S3)
│   │   │   ├── chat.py     # RAG chat endpoint
│   │   │   └── history.py  # Chat history
│   │   └── services/
│   │       ├── rag_service.py   # LangChain + FAISS
│   │       └── s3_service.py    # AWS S3 operations
│   ├── requirements.txt
│   └── Dockerfile
│
├── training_data/          # Standalone PDF processing scripts
│   ├── process_pdf.py      # CLI tool for batch processing
│   └── requirements.txt
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## ✨ Features

| Feature | Description |
|---|---|
| 📤 **PDF Upload** | Drag & drop PDFs, stored securely on AWS S3 |
| 🤖 **RAG Chat** | Ask questions, get answers with page citations |
| 🔐 **Email Auth** | Register/login with email verification |
| 🔑 **Google OAuth** | One-click sign-in with Google |
| 📧 **Email Notifications** | Verification & password reset emails |
| 💾 **Chat History** | All sessions saved and searchable |
| 🔄 **JWT Auth** | Secure stateless authentication |
| ⚡ **Redis Cache** | Fast session & PDF status caching |
| 🐳 **Docker** | One-command deployment |
| 📊 **User Stats** | PDFs, sessions, message counts |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key
- AWS S3 bucket
- Google OAuth credentials
- Gmail App Password (for email)

### 1. Clone & Configure

```bash
git clone https://github.com/yourname/rag-pdf-app.git
cd rag-pdf-app

# Copy and fill in your credentials
cp .env.example .env
nano .env
```

### 2. Fill in `.env`

```env
SECRET_KEY=<random-64-char-string>
JWT_SECRET_KEY=<another-random-64-char-string>

OPENAI_API_KEY=sk-...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=my-rag-bucket
GOOGLE_CLIENT_ID=...apps.googleusercontent.com

MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Gmail App Password
```

### 3. Launch

```bash
docker-compose up --build -d
```

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:5000/api

---

## 🔧 Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp ../.env.example .env           # edit .env
export $(cat .env | xargs)

flask db upgrade                  # run migrations
python run.py
```

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local     # edit REACT_APP_ variables
npm start
```

---

## 🛠️ Training Data — Standalone PDF Processor

Use the `training_data/` scripts to batch-process PDFs outside the web app.

```bash
cd training_data
pip install -r requirements.txt
cp .env.example .env              # add OPENAI_API_KEY

# Process a single PDF
python process_pdf.py process --pdf ./sample.pdf

# Process all PDFs in a folder
python process_pdf.py process --dir ./pdfs/

# List all vector stores
python process_pdf.py list

# Test a query against a processed PDF
python process_pdf.py test --id sample --question "What is this document about?"
```

---

## 🏗️ Architecture

```
User Browser
    │
    ▼
React Frontend (Port 3000)
    │   JWT stored in localStorage
    │
    ▼
Flask Backend (Port 5000)
    ├── /api/auth     JWT + Google OAuth + Email
    ├── /api/pdf      Upload → AWS S3 → FAISS processing
    ├── /api/chat     RAG query pipeline
    └── /api/history  Saved sessions & search
    │
    ├── PostgreSQL    Users, PDFs, Sessions, Messages
    ├── Redis         Session cache, PDF status cache
    ├── AWS S3        PDF file storage
    └── FAISS         Vector embeddings (local disk)
          │
          └── LangChain → OpenAI Embeddings → GPT-3.5/4
```

### RAG Pipeline

```
PDF Upload
   │
   ▼
PyPDFLoader → load pages
   │
   ▼
RecursiveCharacterTextSplitter
   chunk_size=1000, overlap=200
   │
   ▼
OpenAI text-embedding-ada-002
   │
   ▼
FAISS vector store (saved to disk)
   │
   ▼
User asks question
   │
   ▼
Similarity search → top-4 chunks
   │
   ▼
ConversationalRetrievalChain + GPT-3.5
   │
   ▼
Answer + page citations
```

---

## 🔐 Authentication Flow

### Email/Password
1. User registers → email verification sent
2. Click link → account activated → JWT issued
3. Login → JWT stored in localStorage
4. Every API request includes `Authorization: Bearer <token>`

### Google OAuth
1. User clicks "Continue with Google"
2. Google token sent to `/api/auth/google`
3. Backend verifies with Google SDK
4. JWT issued, user created/updated

---

## ☁️ AWS S3 Setup

1. Create an S3 bucket
2. Create an IAM user with `AmazonS3FullAccess` policy (or create a custom policy)
3. Generate access keys and add to `.env`

**Bucket CORS policy:**
```json
[{
  "AllowedHeaders": ["*"],
  "AllowedMethods": ["GET", "PUT", "POST", "DELETE"],
  "AllowedOrigins": ["https://yourdomain.com"],
  "ExposeHeaders": []
}]
```

---

## 📧 Gmail Setup for Email Sending

1. Enable 2FA on your Google account
2. Go to Google Account → Security → App Passwords
3. Generate a new App Password for "Mail"
4. Use it as `MAIL_PASSWORD` in `.env`

---

## 🌐 Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → APIs & Services → Credentials
3. Create **OAuth 2.0 Client ID** (Web Application)
4. Add authorized origins: `http://localhost:3000` and your production URL
5. Copy the Client ID to `GOOGLE_CLIENT_ID` in `.env`

---

## 🐳 Docker Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f backend
docker-compose logs -f frontend

# Rebuild after code changes
docker-compose up --build -d

# Stop all services
docker-compose down

# Stop and remove volumes (reset database)
docker-compose down -v

# Run database migrations
docker-compose exec backend flask db upgrade

# Access backend shell
docker-compose exec backend python
```

---

## 🔌 API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register with email |
| POST | `/api/auth/login` | Login with email/password |
| POST | `/api/auth/google` | Google OAuth login |
| POST | `/api/auth/verify-email` | Verify email token |
| POST | `/api/auth/forgot-password` | Request reset link |
| POST | `/api/auth/reset-password` | Reset password |
| GET | `/api/auth/me` | Get current user |
| POST | `/api/auth/logout` | Logout |

### PDFs
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/pdf/upload` | Upload PDF (multipart/form-data) |
| GET | `/api/pdf/list` | List user's PDFs |
| GET | `/api/pdf/status/:id` | Get processing status |
| DELETE | `/api/pdf/:id` | Delete PDF |
| GET | `/api/pdf/:id/download-url` | Get presigned S3 URL |

### Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat/session` | Create chat session |
| POST | `/api/chat/message` | Send message (RAG query) |
| GET | `/api/chat/session/:id/messages` | Get session messages |
| GET | `/api/chat/sessions` | List all sessions |
| DELETE | `/api/chat/session/:id` | Delete session |

### History
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/history/` | Paginated history |
| GET | `/api/history/search?q=...` | Search messages |
| GET | `/api/history/stats` | User statistics |

---

## 🛡️ Security Notes

- JWT tokens expire in 24 hours
- PDFs stored as **private** S3 objects (accessed via presigned URLs)
- Passwords hashed with Werkzeug (bcrypt-compatible)
- CORS restricted to frontend origin
- Redis used to invalidate sessions on logout

---

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, React Router 6, Axios |
| Auth UI | @react-oauth/google, JWT localStorage |
| Backend | Flask 3, Gunicorn |
| ORM | SQLAlchemy + Flask-Migrate |
| Auth | Flask-JWT-Extended, Google Auth |
| Email | Flask-Mail (SMTP) |
| AI/RAG | LangChain, FAISS, OpenAI |
| Storage | AWS S3 (boto3) |
| Cache | Redis |
| Database | PostgreSQL |
| Container | Docker + Docker Compose |
| Server | Nginx (frontend proxy) |

---

## 📝 License

MIT License — see [LICENSE](./LICENSE)