from __future__ import annotations

from pathlib import Path
from typing import Any


import chromadb


class ChromaPolicyStore:
    """Chroma-backed index for policy documents RAG search."""

    def __init__(
        self,
        persist_directory: Path,
        embedding_model: Any,
        collection_name: str = "policy_chunks",
    ) -> None:
        self.persist_directory = persist_directory
        self.embedding_model = embedding_model
        
        # Ensure the directory exists
        self.persist_directory.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize Chroma DB Persistent Client
        self.client = chromadb.PersistentClient(path=str(self.persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def ensure_index(self, markdown_path: Path) -> None:
        # Rebuild if the collection is currently empty
        if self.collection.count() == 0:
            self.rebuild(markdown_path)

    def rebuild(self, markdown_path: Path) -> None:
        from rag.parser import parse_policy_markdown

        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown policy file not found at {markdown_path}")
            
        with open(markdown_path, "r", encoding="utf-8") as f:
            markdown_text = f.read()
            
        chunks = parse_policy_markdown(markdown_text)
        if not chunks:
            return
            
        # Recreate the collection to clear out old data
        try:
            self.client.delete_collection(name=self.collection.name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(name=self.collection.name)
        
        documents = [c["rendered_text"] for c in chunks]
        embeddings = self.embedding_model.embed_documents(documents)
        metadatas = [{
            "section_h2": c["section_h2"],
            "section_h3": c["section_h3"],
            "citation": c["citation"]
        } for c in chunks]
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        
        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        # Embed query text
        query_vector = self.embedding_model.embed_query(query)
        
        # Search the Chroma collection
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k
        )
        
        hits = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []
            
            for i in range(len(docs)):
                meta = metas[i] if i < len(metas) else {}
                dist = dists[i] if i < len(dists) else 0.0
                content = docs[i]
                
                hits.append({
                    "citation": meta.get("citation", ""),
                    "content": content,
                    "distance": dist
                })
        return hits
