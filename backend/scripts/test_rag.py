from backend.app.core.database import SessionLocal
from backend.app.models.product import SoldItem
from backend.app.rag.retriever import sync_policies_to_vector_store, retrieve_relevant_policies
from backend.app.rag.chain import generate_chat_response

def test_rag():
    db = SessionLocal()
    try:
        print("=== BẮT ĐẦU ĐÁNH CHỈ MỤC POLICIES VÀO VECTOR STORE ===")
        sync_policies_to_vector_store(db)

        # 1. Test với sản phẩm Điều hòa Daikin còn hạn bảo hành
        ac_item = db.query(SoldItem).filter(SoldItem.serial_number == "DK-2025-998877").first()
        query1 = "Máy lạnh nhà mình bị chảy nước dàn lạnh có được bảo hành không?"
        print("\n-----------------------------------------------------------")
        print(f"TEST 1: Khách hỏi về {ac_item.product.name} (Hạn BH: {ac_item.warranty_expire_date})")
        print(f"Câu hỏi: '{query1}'")
        retrieved1 = retrieve_relevant_policies(query1, sold_item=ac_item)
        print(f"-> RAG tìm thấy {len(retrieved1)} tài liệu liên quan:")
        for r in retrieved1:
            print(f"   * [{r['score']:.2f}] {r['document']['metadata']['title']}")
        res1 = generate_chat_response(query1, retrieved1, sold_item=ac_item)
        print("\n[AI Chatbot Trả lời]:\n" + res1["reply"])
        print("\nGợi ý hành động:", res1["suggested_action"])

        # 2. Test với sản phẩm Tivi Samsung đã hết hạn bảo hành
        tv_item = db.query(SoldItem).filter(SoldItem.serial_number == "TV-2023-445566").first()
        query2 = "Tivi Samsung bị kẻ sọc màn hình có được thay màn miễn phí không?"
        print("\n-----------------------------------------------------------")
        print(f"TEST 2: Khách hỏi về {tv_item.product.name} (Hạn BH: {tv_item.warranty_expire_date})")
        print(f"Câu hỏi: '{query2}'")
        retrieved2 = retrieve_relevant_policies(query2, sold_item=tv_item)
        print(f"-> RAG tìm thấy {len(retrieved2)} tài liệu liên quan:")
        for r in retrieved2:
            print(f"   * [{r['score']:.2f}] {r['document']['metadata']['title']}")
        res2 = generate_chat_response(query2, retrieved2, sold_item=tv_item)
        print("\n[AI Chatbot Trả lời]:\n" + res2["reply"])
        print("\nGợi ý hành động:", res2["suggested_action"])

        # 3. Test trường hợp từ chối bảo hành (Gãy cánh quạt do va chạm)
        query3 = "Quạt làm mát nhà em bị rơi vỡ cánh quạt có được bảo hành không?"
        print("\n-----------------------------------------------------------")
        print(f"TEST 3: Hỏi chung về '{query3}'")
        retrieved3 = retrieve_relevant_policies(query3)
        res3 = generate_chat_response(query3, retrieved3)
        print("\n[AI Chatbot Trả lời]:\n" + res3["reply"])

    finally:
        db.close()

if __name__ == "__main__":
    test_rag()
