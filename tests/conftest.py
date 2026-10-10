import os

# Use test-only settings before application modules instantiate Pydantic Settings.
os.environ["DATABASE_URL"] = "sqlite:///./document_intelligence.db"
os.environ["SECRET_KEY"] = "test-only-secret-key-with-at-least-32-characters"
os.environ["GEMINI_API_KEY"] = "test-only-placeholder-key"
os.environ["UPLOAD_DIR"] = "./uploads"
os.environ["MAX_FILE_SIZE"] = "10485760"
