import os
from dotenv import load_dotenv

load_dotenv()

from agent.pipeline import build_pipeline
from agent.routes import create_app
from tools.rulebase import build_rulebase_cache

# Resolve paths relative to this file (works both locally and in Docker /app)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data')

# 1. Khởi tạo RAG pipeline (nạp PDF + tạo vectorstore)
embeddings, rag_chain = build_pipeline(data_path=DATA_PATH)

# 2. Nạp Rule-base cache vào bộ nhớ
build_rulebase_cache(embeddings)

# 3. Khởi động Flask server
app = create_app(embeddings, rag_chain)

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
