from pathlib import Path
from typing import List
from dotenv import load_dotenv
import csv , mimetypes , docx2txt 
import pandas as pd 
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.settings import settings

from pypdf import PdfReader 
from bs4 import BeautifulSoup
import pandas as pd
from PIL import Image
import pytesseract

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    CSVLoader,
    UnstructuredHTMLLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredExcelLoader,
    UnstructuredImageLoader,
    UnstructuredFileLoader,
)

