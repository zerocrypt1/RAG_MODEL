import argparse
import os
import json
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

# Document Loaders
from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredExcelLoader
)

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA

load_dotenv()

VECTOR_STORE_DIR = os.environ.get("VECTOR_STORE_DIR", "./vector_stores")

# --------------------------------------------------
# Environment validation
# --------------------------------------------------

def validate_environment():
    """Ensure the vector store directory exists."""
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)

# --------------------------------------------------
# Document loader
# --------------------------------------------------

def load_document(file_path: str):
    path = Path(file_path)

    if path.suffix == ".pdf":
        loader = PyPDFLoader(str(path))
    elif path.suffix in [".doc", ".docx"]:
        loader = UnstructuredWordDocumentLoader(str(path))
    elif path.suffix in [".xls", ".xlsx"]:
        loader = UnstructuredExcelLoader(str(path))
    else:
        raise ValueError(f"Unsupported file type: {path.suffix}")

    return loader.load()

# --------------------------------------------------
# Process single document
# --------------------------------------------------

def process_single_file(file_path: str, store_id: str = None):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    store_id = store_id or path.stem
    store_path = Path(VECTOR_STORE_DIR) / store_id

    print("\n" + "=" * 50)
    print(f"Processing: {path.name}")
    print(f"Store ID:   {store_id}")
    print("=" * 50)

    # 1. Load document
    print("📄 Loading document...")
    docs = load_document(str(path))
    print(f"Pages loaded: {len(docs)}")

    # 2. Split text
    print("✂️ Splitting text...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    chunks = splitter.split_documents(docs)
    print(f"Chunks created: {len(chunks)}")

    # 3. Add Metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            "chunk_id": i,
            "store_id": store_id,
            "source_file": path.name,
            "processed_at": datetime.utcnow().isoformat()
        })

    # 4. Embeddings
    print("🔢 Creating embeddings (this may take a moment)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # 5. Vector store
    print("🗄️ Building FAISS index...")
    vector_store = FAISS.from_documents(chunks, embeddings)
    
    # Create directory if it doesn't exist
    os.makedirs(store_path, exist_ok=True)
    vector_store.save_local(str(store_path))

    # 6. Metadata file
    metadata = {
        "store_id": store_id,
        "source_file": path.name,
        "chunk_count": len(chunks),
        "processed_at": datetime.utcnow().isoformat()
    }

    with open(store_path / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"✅ Saved to: {store_path}")
    return metadata

# --------------------------------------------------
# Batch processing
# --------------------------------------------------

def process_directory(dir_path: str):
    path = Path(dir_path)
    # Filter for supported extensions
    valid_exts = [".pdf", ".doc", ".docx", ".xls", ".xlsx"]
    files = [f for f in path.glob("*") if f.suffix.lower() in valid_exts]

    if not files:
        print(f"No valid documents found in {dir_path}")
        return []

    results = []
    for file in files:
        try:
            result = process_single_file(str(file))
            results.append({"file": file.name, "status": "success", **result})
        except Exception as e:
            results.append({"file": file.name, "status": "failed", "error": str(e)})

    return results

# --------------------------------------------------
# List vector stores
# --------------------------------------------------

def list_vector_stores():
    store_dir = Path(VECTOR_STORE_DIR)

    if not store_dir.exists():
        print("No vector stores found.")
        return

    stores = [d for d in store_dir.iterdir() if d.is_dir()]

    print("\nAvailable Vector Stores")
    print("-" * 30)

    for store in stores:
        meta_file = store / "metadata.json"
        if meta_file.exists():
            with open(meta_file) as f:
                data = json.load(f)
            print(f"ID: {data['store_id']} | Chunks: {data['chunk_count']} | Date: {data['processed_at']}")

# --------------------------------------------------
# Query test
# --------------------------------------------------

def test_query(store_id: str, question: str):
    store_path = Path(VECTOR_STORE_DIR) / store_id

    if not store_path.exists():
        print(f"Error: Vector store '{store_id}' not found.")
        return

    print(f"\n🔍 Querying {store_id}...")
    
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # allow_dangerous_deserialization=True is required for FAISS local loading
    vector_store = FAISS.load_local(
        str(store_path), 
        embeddings, 
        allow_dangerous_deserialization=True
    )

    retriever = vector_store.as_retriever(search_kwargs={"k": 4})
    
    # Note: Requires Ollama to be running locally with 'mistral' pulled
    llm = Ollama(model="mistral")

    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=retriever
    )

    print(f"❓ Question: {question}")
    result = qa.invoke({"query": question})

    print("\n🧠 Answer:")
    print("-" * 20)
    print(result["result"])
    print("-" * 20)

# --------------------------------------------------
# CLI Entry Point
# --------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Local RAG Processor")
    subparsers = parser.add_subparsers(dest="command")

    # Process command
    p_parser = subparsers.add_parser("process")
    p_parser.add_argument("--pdf", help="Path to a single PDF/Doc/Excel file")
    p_parser.add_argument("--dir", help="Directory of documents to process")
    p_parser.add_argument("--id", help="Custom store ID (optional)")

    # List command
    subparsers.add_parser("list")

    # Test command
    t_parser = subparsers.add_parser("test")
    t_parser.add_argument("--id", required=True, help="Store ID to query")
    t_parser.add_argument("--question", required=True, help="The question to ask")

    args = parser.parse_args()

    validate_environment()

    if args.command == "process":
        if args.pdf:
            process_single_file(args.pdf, args.id)
        elif args.dir:
            process_directory(args.dir)
        else:
            print("Error: Provide either --pdf or --dir")

    elif args.command == "list":
        list_vector_stores()

    elif args.command == "test":
        test_query(args.id, args.question)

    else:
        parser.print_help()