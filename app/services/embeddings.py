from sentence_transformers import SentenceTransformer
from typing import List
import numpy as np

# Load the model once (reused for all requests)
model = SentenceTransformer('all-MiniLM-L6-v2')

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts
    
    Args:
        texts: List of text strings to embed
    
    Returns:
        List of embeddings (each embedding is a list of 384 floats)
    """
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()

def generate_single_embedding(text: str) -> List[float]:
    """Generate embedding for a single text"""
    embedding = model.encode([text], convert_to_numpy=True)
    return embedding[0].tolist()