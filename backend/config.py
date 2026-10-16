"""
统一配置：路径、模型名、API Key
所有其他模块从这里读配置，避免路径写死
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ========== 1. 定位项目根目录 ==========
# __file__ 是 config.py 自己，.parent 是 backend/，再 .parent 是项目根
ROOT_DIR = Path(__file__).resolve().parent.parent

# ========== 2. 加载 .env ==========
ENV_PATH = ROOT_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# ========== 3. 路径常量（从项目根推导，永远正确）==========
DATA_DIR = ROOT_DIR / "data"
VECTOR_DIR = ROOT_DIR / "chroma_db_langchain"
DOC_PATH = DATA_DIR / "my_doc.txt"

# ========== 4. 模型常量 ==========
EMBEDDING_MODEL = "text-embedding-v3"
RERANK_MODEL = "qwen3-rerank"
LLM_MODEL = "qwen3.7-flash"

# ========== 5. 检索参数 ==========
VECTOR_TOP_K = 20      # 向量检索召回条数
RERANK_TOP_N = 3       # rerank 后保留条数（你评测过，top3 最优）

# ========== 6. API Key ==========
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise ValueError("DASHSCOPE_API_KEY 未设置，请检查 .env")

# ========== 7. Rerank 通用 endpoint（不写死专属地址）==========
RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"

# ========== 8. 向量库 collection 名 ==========
COLLECTION_NAME = "langchain"