"""
training_data/process_pdf.py
—————————————————————————————
Standalone script to batch-process PDFs, create embeddings,
and store them in a FAISS vector store.

Usage:
  python process_pdf.py --pdf path/to/file.pdf --id custom-id
  python process_pdf.py --dir path/to/pdfs/          # batch process all PDFs in folder
"""

import argparse
import os
import sys
import json
from pathlib import Path
from datetime import datetime

from langchain_community.document_loaders import (
    PyPDFLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredExcelLoader
)
from langchain.text_splitter import RecursiveCharacterTextSplitter
#from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()

VECTOR_STORE_DIR = os.environ.get('VECTOR_STORE_DIR', './vector_stores')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')


def validate_environment():
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY not set in environment or .env file")
        sys.exit(1)
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)


def process_single_pdf(pdf_path: str, store_id: str = None) -> dict:
    """
    Process a single PDF file into a FAISS vector store.

    Args:
        pdf_path: Path to the PDF file
        store_id: Custom ID for the vector store (defaults to filename stem)

    Returns:
        dict with processing results
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    store_id = store_id or pdf_path.stem
    store_path = Path(VECTOR_STORE_DIR) / store_id

    print(f"\n{'='*50}")
    print(f"Processing: {pdf_path.name}")
    print(f"Store ID:   {store_id}")
    print(f"{'='*50}")

    # 1. Load PDF
    print("📄 Loading PDF...")
    loader = PyPDFLoader(str(pdf_path))
    pages = loader.load()
    print(f"   Loaded {len(pages)} pages")

    # 2. Split into chunks
    print("✂️  Splitting into chunks...")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    chunks = splitter.split_documents(pages)
    print(f"   Created {len(chunks)} chunks")

    # Add metadata
    for i, chunk in enumerate(chunks):
        chunk.metadata.update({
            'chunk_id': i,
            'store_id': store_id,
            'source_file': pdf_path.name,
            'processed_at': datetime.utcnow().isoformat()
        })

    # 3. Create embeddings
    print("🔢 Creating embeddings (this may take a moment)...")
    embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

    # 4. Build FAISS index
    print("🗄️  Building vector store...")
    vector_store = FAISS.from_documents(chunks, embeddings)

    # 5. Save to disk
    vector_store.save_local(str(store_path))
    print(f"✅ Saved vector store to: {store_path}")

    # Save metadata
    metadata = {
        'store_id': store_id,
        'source_file': pdf_path.name,
        'page_count': len(pages),
        'chunk_count': len(chunks),
        'processed_at': datetime.utcnow().isoformat(),
        'store_path': str(store_path)
    }
    with open(store_path / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    return metadata


def process_directory(dir_path: str) -> list:
    """Process all PDFs in a directory."""
    dir_path = Path(dir_path)
    pdfs = list(dir_path.glob('*.pdf'))

    if not pdfs:
        print(f"No PDF files found in {dir_path}")
        return []

    results = []
    for pdf in pdfs:
        try:
            result = process_single_pdf(str(pdf))
            results.append({'file': pdf.name, 'status': 'success', **result})
        except Exception as e:
            print(f"❌ Failed to process {pdf.name}: {e}")
            results.append({'file': pdf.name, 'status': 'failed', 'error': str(e)})

    return results


def list_vector_stores():
    """List all available vector stores."""
    store_dir = Path(VECTOR_STORE_DIR)
    if not store_dir.exists():
        print("No vector stores found.")
        return

    stores = [d for d in store_dir.iterdir() if d.is_dir()]
    if not stores:
        print("No vector stores found.")
        return

    print(f"\n{'ID':<30} {'Pages':>6} {'Chunks':>8} {'Processed At'}")
    print('-' * 70)
    for store in sorted(stores):
        meta_file = store / 'metadata.json'
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
            print(f"{meta['store_id']:<30} {meta['page_count']:>6} {meta['chunk_count']:>8}  {meta['processed_at'][:19]}")
        else:
            print(f"{store.name:<30} {'?':>6} {'?':>8}  Unknown")


def test_query(store_id: str, question: str):
    """Test a query against a vector store."""
    from langchain_openai import ChatOpenAI
    from langchain.chains import RetrievalQA

    store_path = Path(VECTOR_STORE_DIR) / store_id
    if not store_path.exists():
        print(f"Vector store not found: {store_id}")
        return

    print(f"\n🔍 Querying store: {store_id}")
    print(f"❓ Question: {question}\n")

    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    vector_store = FAISS.load_local(str(store_path), embeddings, allow_dangerous_deserialization=True)
    retriever = vector_store.as_retriever(search_kwargs={"k": 4})

    llm = ChatOpenAI(openai_api_key=OPENAI_API_KEY, model_name='gpt-3.5-turbo', temperature=0.2)
    qa = RetrievalQA.from_chain_type(llm=llm, chain_type="stuff", retriever=retriever,
                                      return_source_documents=True)
    result = qa.invoke({"query": question})

    print(f"📝 Answer:\n{result['result']}")
    print(f"\n📚 Sources:")
    for doc in result['source_documents']:
        print(f"  - Page {doc.metadata.get('page', '?') + 1}: {doc.page_content[:100]}...")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='RAG PDF Training Tool')
    subparsers = parser.add_subparsers(dest='command')

    # process command
    proc = subparsers.add_parser('process', help='Process a PDF')
    proc.add_argument('--pdf', required=False, help='Path to PDF file')
    proc.add_argument('--dir', required=False, help='Directory with PDFs')
    proc.add_argument('--id', required=False, help='Custom store ID')

    # list command
    subparsers.add_parser('list', help='List all vector stores')

    # test command
    test = subparsers.add_parser('test', help='Test a query')
    test.add_argument('--id', required=True, help='Vector store ID')
    test.add_argument('--question', required=True, help='Question to ask')

    args = parser.parse_args()

    validate_environment()

    if args.command == 'process':
        if args.pdf:
            result = process_single_pdf(args.pdf, args.id)
            print(f"\n✅ Done! Metadata: {json.dumps(result, indent=2)}")
        elif args.dir:
            results = process_directory(args.dir)
            print(f"\n✅ Processed {len([r for r in results if r['status'] == 'success'])}/{len(results)} PDFs")
        else:
            print("Provide --pdf or --dir")
    elif args.command == 'list':
        list_vector_stores()
    elif args.command == 'test':
        test_query(args.id, args.question)
    else:
        parser.print_help()