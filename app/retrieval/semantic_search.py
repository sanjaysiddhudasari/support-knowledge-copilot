from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.ingestion.loader import load_text_file

model =SentenceTransformer('all-MiniLM-L6-v2')

raw = load_text_file('data/raw/password-policy.md')
documents = [d.strip() for d in raw.split('\n\n') if d.strip()]

document_embeddings = model.encode(documents, convert_to_numpy=True)
query = "I forgot my password. How can I access my account?"

query_embedding = model.encode([query], convert_to_numpy=True)
similarities = cosine_similarity(
    query_embedding,
    document_embeddings
)[0]

print("Similarity scores:")
for i, score in enumerate(similarities):
    print(f"Document {i}: {score:.4f}")

