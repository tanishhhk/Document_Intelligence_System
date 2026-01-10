import google.generativeai as genai
from app.config import settings
import time

# Configure the API key
genai.configure(api_key=settings.GEMINI_API_KEY)

def generate_answer(question: str, context: str, max_retries: int = 3) -> str:
    """
    Generate answer using Google Gemini API with retry logic
    
    Args:
        question: User's question
        context: Retrieved document chunks as context
        max_retries: Maximum number of retry attempts
        
    Returns:
        AI-generated answer
    """
    for attempt in range(max_retries):
        try:
            # Initialize the model
            model = genai.GenerativeModel('models/gemini-2.5-flash')
            
            # Create prompt with context
            prompt = f"""Based on the following context from the document, please answer the question.
If the answer cannot be found in the context, say "I cannot find this information in the provided document."

Context:
{context}

Question: {question}

Answer:"""
            
            # Generate response
            response = model.generate_content(prompt)
            
            return response.text
            
        except Exception as e:
            error_msg = str(e)
            
            # Handle rate limiting
            if "RESOURCE_EXHAUSTED" in error_msg or "429" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    print(f"Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise Exception("Rate limit exceeded. Please try again in a few moments.")
            
            # Handle other errors
            raise Exception(f"Error generating answer: {error_msg}")
    
    raise Exception("Failed to generate answer after multiple retries")