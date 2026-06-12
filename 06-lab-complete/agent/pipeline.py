import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from langchain_community.document_loaders import DirectoryLoader, UnstructuredFileLoader
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough

_MARKDOWN_SEPARATORS = [
    "\n#{1,6} ", "```\n", "\n\\*\\*\\*+\n", "\n---+\n", "\n___+\n", "\n\n", "\n", " ", ""
]

_SYSTEM_PROMPT = """\
## Persona
- **Role:** Trợ lý hỏi đáp nội bộ cho chương trình đào tạo AI thực chiến tại VinUni.
- **Expertise:** Chuyên gia tra cứu tài liệu handbook, quy định chương trình, lịch học, và quy trình nộp bài.
- **Communication style:** Ngắn gọn, chính xác, thân thiện. Ưu tiên tiếng Việt. Không dùng ngôn ngữ mơ hồ.

## Rules
- LUÔN trả lời dựa trên nội dung được cung cấp trong `{context}`.
- LUÔN trích dẫn nguồn theo định dạng `*(Nguồn: <tên file/trang>)*` nếu metadata có sẵn.
- LUÔN trả lời theo **Output Format** quy định bên dưới.
- NÊN ưu tiên bullet list cho các câu trả lời có nhiều ý.
- NÊN dùng **in đậm** để nhấn mạnh thông tin quan trọng (ngày, số liệu, tên mục).

## Capabilities
- Tra cứu thông tin từ Handbook PDF đã được index vào vectorstore (RAG).
- Tra cứu câu trả lời đã được Mentor xác nhận trong Rule-base.
- Trả lời các câu hỏi liên quan đến: lịch học, quy định, quy trình nộp bài, đổi nhóm/chủ đề, điều kiện hoàn thành chương trình.

## Constraints
- KHÔNG tự suy đoán hoặc bịa đặt thông tin ngoài tài liệu được cung cấp.
- KHÔNG sử dụng kiến thức bên ngoài (web, GPT training data).
- Khi thông tin KHÔNG có trong context, phản hồi ĐÚNG cụm từ sau (không thêm gì):
  `I don't know based on the provided document.`
- KHÔNG trả lời các câu hỏi ngoài phạm vi chương trình (chính trị, y tế, pháp lý, v.v.).

## Output Format
Trả lời theo cấu trúc markdown sau:

**[Câu trả lời ngắn gọn — 1-2 câu tóm tắt]**

- Chi tiết điểm 1
- Chi tiết điểm 2
- ...

*(Nguồn: <tên file hoặc trang nếu có>)*
"""

_TEMPLATE = _SYSTEM_PROMPT + "\n---\nContext:\n{context}\n\nQuestion: {question}"


def build_pipeline(data_path: str = './data'):
    """Nạp tài liệu PDF, tạo vectorstore FAISS và RAG chain.

    Returns:
        embeddings: GoogleGenerativeAIEmbeddings
        rag_chain:  LangChain chain
    """
    embedding_model = os.getenv('EMBEDDING_MODEL', 'gemini-embedding-001')
    llm_model       = os.getenv('LLM_MODEL', 'gemini-2.5-flash')

    print("Đang nạp tài liệu và xây dựng Vector Database...")
    loader = DirectoryLoader(
        path=data_path,
        glob='**/*.pdf',
        loader_cls=UnstructuredFileLoader,
        show_progress=True,
        use_multithreading=False,
    )
    docs = loader.load()

    splits = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=200,
        add_start_index=True,
        strip_whitespace=True,
        separators=_MARKDOWN_SEPARATORS,
    ).split_documents(docs)

    embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model)

    vectorstore = FAISS.from_documents(
        documents=splits,
        embedding=embeddings,
        distance_strategy=DistanceStrategy.COSINE,
    )

    retriever = vectorstore.as_retriever(
        search_type="similarity_score_threshold",
        search_kwargs={"k": 5, "score_threshold": 0.2},
    )

    rag_chain = (
        {"context": retriever, "question": RunnablePassthrough()}
        | ChatPromptTemplate.from_template(_TEMPLATE)
        | ChatGoogleGenerativeAI(model=llm_model, temperature=0)
        | StrOutputParser()
    )

    print("Khởi tạo RAG Pipeline thành công!")
    return embeddings, rag_chain
