"""Central configuration: models, paths, chunking and retrieval settings."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = DATA_DIR / "docs"
LEVELS_CSV = DATA_DIR / "levels.csv"
RUBRIC_PATH = DATA_DIR / "order_rubric.json"
EVAL_PATH = DATA_DIR / "eval_questions.json"
CHROMA_DIR = ROOT / "chroma_db"
AUDIT_DB = ROOT / "audit" / "audit.sqlite"  # local audit log (gitignored)
COLLECTION_NAME = "doctrine"

# Ollama (local only)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
# Chat model. Switch here, or without editing: CADET_LLM_MODEL=qwen2.5:14b streamlit run app.py
# qwen2.5:14b follows the language and citation rules more reliably but needs ~10 GB of
# RAM/VRAM and is about twice as slow. Pull it first: ollama pull qwen2.5:14b
LLM_MODEL_OPTIONS = ("qwen2.5:7b", "qwen2.5:14b")
LLM_MODEL = os.getenv("CADET_LLM_MODEL", "qwen2.5:7b")
EMBED_MODEL = "bge-m3"
LLM_TEMPERATURE = 0.1
LLM_NUM_CTX = 8192
LLM_RETRIES = 2  # extra attempts after the first failure
EMBED_BATCH = 16

# Text extraction: pages with fewer characters than this are OCR'd with Tesseract.
OCR_MIN_CHARS = 50
OCR_LANGUAGES = "ara+fra"  # used only when a page's script can't be detected
OCR_DPI = 300
# Drop low-confidence OCR words (icons and photos read as text). Arabic scores are
# unreliable (real words score near 0), so Arabic keeps every word.
OCR_MIN_WORD_CONF = {"ara": 0, "fra": 40, "eng": 40}
# Column detection on OCR'd pages, in multiples of the median word height: a vertical
# gutter at least COLUMN_GAP wide splits columns; a horizontal gap at least BAND_GAP
# high separates bands (rows, paragraphs, headings).
COLUMN_GAP = 1.5
BAND_GAP = 0.8
BROKEN_ARABIC_THRESHOLD = 0.03  # share of corrupted-ligature words that triggers OCR
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "tesseract")  # full path to tesseract.exe on Windows

# Chunking
CHUNK_WORDS = 500
CHUNK_OVERLAP = 80

# Retrieval
TOP_K = 5

# Clearance
USERS: dict[str, int] = {"Cadet": 0, "Officer": 1, "Instructor": 2}
LEVEL_NAMES: dict[int, str] = {0: "Public", 1: "Restricted", 2: "Confidential"}
DEFAULT_LEVEL = 0
