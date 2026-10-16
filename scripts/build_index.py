"""重建向量库：只读 data/my_doc.txt（干净数据）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shutil
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend import config

# 1. 删旧向量库
if config.VECTOR_DIR.exists():
    print(f"删除旧向量库：{config.VECTOR_DIR}")
    shutil.rmtree(config.VECTOR_DIR)

# 2. 读文档
print(f"读取：{config.DOC_PATH}")
loader = TextLoader(str(config.DOC_PATH), encoding="utf-8")
docs = loader.load()

# 3. 切分（chunk_size 调小，因为 my_doc.txt 每条信息都短）
splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_documents(docs)
print(f"切分后：{len(chunks)} 个 chunk")

# 4. 嵌入 + 存库
print("正在嵌入（会调 DashScope API，约需 10-30 秒）...")
embeddings = DashScopeEmbeddings(model=config.EMBEDDING_MODEL)
vectorstore = Chroma.from_documents(
    documents=chunks,
    embedding=embeddings,
    persist_directory=str(config.VECTOR_DIR),
    collection_name=config.COLLECTION_NAME,
)
print(f"✅ 完成！向量库条数：{vectorstore._collection.count()}")