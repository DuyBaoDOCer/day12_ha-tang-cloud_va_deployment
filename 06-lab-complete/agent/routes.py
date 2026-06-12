import os
from flask import Flask, request, jsonify, send_from_directory

from tools.rulebase import search_rulebase

OUT_OF_SCOPE_PHRASE = "i don't know based on the provided document"
OUT_OF_SCOPE_REPLY = (
    "Xin lỗi, câu hỏi của bạn hiện chưa có thông tin trong tài liệu hướng dẫn. "
    "Vui lòng tham gia **Discord** để được Mentor hỗ trợ trực tiếp nhé!"
)


def create_app(embeddings, rag_chain) -> Flask:
    """Tạo Flask app với embeddings và rag_chain được inject vào."""
    # static_folder trỏ tới thư mục gốc /app (chứa index.html, css/, images/)
    static_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, static_folder=static_dir, static_url_path='')

    @app.route('/')
    def index():
        return send_from_directory(static_dir, 'index.html')

    @app.route('/config')
    def config():
        return jsonify({'discord_invite': os.getenv('DISCORD_INVITE_URL', '')})

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/ask', methods=['POST'])
    def ask():
        data = request.get_json(silent=True) or {}
        question = data.get('question', '').strip()
        if not question:
            return jsonify({'answer': 'Vui lòng nhập câu hỏi.', 'source': 'error'})

        # Bước 1: Rule-base
        rulebase_answer = search_rulebase(embeddings, question)
        if rulebase_answer:
            return jsonify({'answer': rulebase_answer, 'source': 'rulebase'})

        # Bước 2: RAG Handbook
        try:
            answer = rag_chain.invoke(question)
            if OUT_OF_SCOPE_PHRASE in answer.lower():
                return jsonify({'answer': OUT_OF_SCOPE_REPLY, 'source': 'out_of_scope'})
            return jsonify({'answer': answer, 'source': 'rag'})
        except Exception as e:
            err_str = str(e)
            if 'RESOURCE_EXHAUSTED' in err_str or '429' in err_str:
                msg = (
                    'Hệ thống đang quá tải, vui lòng thử lại sau ít phút '
                    'hoặc đặt câu hỏi trên Discord để được Mentor hỗ trợ.'
                )
            else:
                msg = 'Đã xảy ra lỗi khi tra cứu, vui lòng thử lại sau.'
            return jsonify({'answer': msg, 'source': 'error'})

    return app
