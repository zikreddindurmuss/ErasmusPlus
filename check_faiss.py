from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from dotenv import load_dotenv

load_dotenv()

vs = FAISS.load_local(
    "./faiss_index",
    OpenAIEmbeddings(model="text-embedding-3-small"),
    allow_dangerous_deserialization=True
)

docs = vs.similarity_search("hibe miktari ispanya 600 avro", k=6)
for i, d in enumerate(docs, 1):
    src = d.metadata.get("source", "?")
    pg = d.metadata.get("page", "?")
    print(f"[{i}] {src} (s.{pg})")
    print(f"    {d.page_content[:300]}")
    print()
