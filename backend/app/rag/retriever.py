import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.app.models.policy import WarrantyPolicy
from backend.app.models.product import SoldItem
from backend.app.rag.vector_store import vector_store
from backend.app.rag.intents import search_query

logger = logging.getLogger(__name__)

def sync_policies_to_vector_store(db: Session):
    """
    Load all active warranty policies from database into the Vector Store index.
    """
    policies = db.query(WarrantyPolicy).filter(WarrantyPolicy.is_active == True).all()
    if not policies:
        vector_store.add_documents([])
        logger.warning("Không tìm thấy chính sách bảo hành nào trong CSDL để đánh chỉ mục vector.")
        return

    documents = []
    for pol in policies:
        combined_text = (
            f"Tiêu đề: {pol.title}\n"
            f"Ngành hàng: {pol.product_category}\n"
            f"Hãng: {pol.brand or 'Tất cả'}\n"
            f"Nhóm lỗi: {pol.error_group or 'Lỗi chung'}\n"
            f"Quy định: {pol.content}\n"
            f"Điều kiện: {pol.conditions or 'Theo quy định chung'}"
        )
        documents.append({
            "id": pol.id,
            "text": combined_text,
            "metadata": {
                "title": pol.title,
                "category": pol.product_category,
                "brand": pol.brand or "",
                "error_group": pol.error_group or "",
                "is_covered": pol.is_covered,
                "conditions": pol.conditions or "",
                "content": pol.content,
            }
        })

    vector_store.add_documents(documents)
    logger.info(f"Đã nạp và lập chỉ mục {len(documents)} chính sách bảo hành vào Vector Store thành công.")

def retrieve_relevant_policies(
    query: str,
    sold_item: Optional[SoldItem] = None,
    top_k: int = 3,
    chat_history: Optional[list] = None,
) -> List[Dict[str, Any]]:
    """
    Search relevant policy chunks with product awareness (AI-02).
    """
    filter_category = None
    filter_brand = None

    if sold_item and sold_item.product:
        filter_category = sold_item.product.category
        filter_brand = sold_item.product.brand

    results = vector_store.search(
        query=search_query(query, chat_history),
        top_k=top_k,
        filter_category=filter_category,
        filter_brand=filter_brand
    )

    return results
