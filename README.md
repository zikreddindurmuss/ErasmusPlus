🌍 ErasmusPlus: The Universal AI Mentor for Global Mobility
ErasmusPlus is a scalable AI ecosystem designed to eliminate the complex bureaucracy and information overload faced by exchange students worldwide. Unlike traditional chatbots, ErasmusPlus is built on a RAG (Retrieval-Augmented Generation) architecture that can process any university's specific data repository (PDFs, Word docs, Regulations) in seconds. Currently in the "Proof of Concept" phase with the University of Jaén (UJA), the project is engineered to scale across Spain and eventually all Erasmus+ participating countries.

🚀 Vision & Roadmap
ErasmusPlus is more than just a chatbot; it is a global student support infrastructure:

Phase 1 (Completed): Established the core RAG infrastructure and field-tested with University of Jaén data.

Phase 2 (Target): Integration of data repositories for major Erasmus destinations across Spain (Madrid, Granada, Valencia, etc.).

Phase 3 (Vision): Evolution into a "Plug & Play" platform where any university worldwide can generate its own AI mentor by simply uploading its official documents.

🔥 Why ErasmusPlus?
Universal Compatibility: The system transforms into an expert for any institution the moment its guides are added to the info_bank. No code changes required.

Zero Hallucination: By strictly adhering to uploaded official documents, it eliminates misinformation in critical processes like visas, grants, and enrollment.

Context Awareness: Remembers the entire conversation history, explaining complex bureaucratic steps with the familiarity of a senior student.

Data-Driven Evolution: Every unanswered query is captured via "fallback logging," serving as a data mine for continuous system improvement.

🛠️ Technical Stack (Scalable Architecture)
LLM Engine: Meta Llama-3.3 (High-speed inference via Groq API)

Vector Database: FAISS (Optimized for milisecond-level retrieval across massive datasets)

Data Processing: Hybrid LangChain loaders for PDF & Docx integration.

Intelligence: HuggingFace Multilingual Embeddings for deep semantic understanding.

📦 Quick Start
This repository contains the core engine. To create your own university mentor:

Clone the repository.

Add your university's official guides to the info_bank folder.

Run python build_db.py to index the data.

Launch the mentor with python main.py.

📝 Note
"ErasmusPlus is built for students who prioritize experience over bureaucracy."
