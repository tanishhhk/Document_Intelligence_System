from typing import List

def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks
    
    Args:
        text: The text to split
        chunk_size: Size of each chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text or len(text) == 0:
        return []
    
    chunks = []
    start = 0
    
    while start < len(text):
        # Get chunk from start to start+chunk_size
        end = start + chunk_size
        chunk = text[start:end]
        
        # Add chunk if it's not empty
        if chunk.strip():
            chunks.append(chunk.strip())
        
        # Move start forward (chunk_size - overlap)
        start += (chunk_size - overlap)
    
    return chunks