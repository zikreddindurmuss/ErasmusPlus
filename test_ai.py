import sys
import asyncio

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from ai_engine import get_ai_response, vectorstore

async def run_tests():
    questions = [
        "İspanya Universidad de Jaén için aylık hibe miktarı ne kadardır?",
        "Erasmus süresince staj yapabilir miyim?",
        "Japonya'daki üniversiteler hangileri?"
    ]
    
    for i, q in enumerate(questions, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {q}")
        print(f"{'='*60}")
        
        docs = vectorstore.similarity_search(q, k=6)
        print("\n--- FAISS KAYNAK METINLER (top-6) ---")
        for j, doc in enumerate(docs, 1):
            src = doc.metadata.get('source', '?')
            pg = doc.metadata.get('page', '?')
            snippet = doc.page_content[:250].replace('\n', ' ')
            print(f"  [{j}] {src} (s.{pg}): {snippet}...")
            print(f"      {'-'*50}")
            
        print("\n--- LLM CEVABI ---")
        reply = await get_ai_response(q, user_id=999)
        print(reply)
        print()

if __name__ == "__main__":
    asyncio.run(run_tests())
