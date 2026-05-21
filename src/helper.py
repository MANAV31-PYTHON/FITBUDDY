from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
import os
import glob

def load_pdf_file(data_dir):
    """Load PDF files from directory and extract text content."""
    documents = []
    pdf_files = glob.glob(os.path.join(data_dir, "*.pdf"))
    
    for pdf_file in pdf_files:
        try:
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            
            if text.strip():
                documents.append(Document(page_content=text.strip(), metadata={"source": pdf_file}))
        except Exception as e:
            print(f"Error loading {pdf_file}: {e}")
    
    return documents

def text_split(extracted_data):
    """Split extracted text into chunks."""
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=20)
    return text_splitter.split_documents(extracted_data)

def download_hugging_face_embeddings():
    """Download and return HuggingFace embeddings."""
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
