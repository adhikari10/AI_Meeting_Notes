import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Providers
    AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")  # groq, deepseek, or openai

    # Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # DeepSeek
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

    # OpenAI (optional backup)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Models
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    AI_MODEL = os.getenv("AI_MODEL", "llama-3.3-70b-versatile")  # llama-3.3-70b-versatile, deepseek-chat, or gpt-3.5-turbo
    
    # Audio settings
    SAMPLE_RATE = 16000
    CHUNK_DURATION = 5  # seconds
    
    @property
    def CHUNK_SIZE(self):
        return self.SAMPLE_RATE * self.CHUNK_DURATION
    
    # Database
    DB_PATH = "meetings.db"
    
    def validate(self):
        """Validate configuration"""
        if self.AI_PROVIDER == "groq":
            if not self.GROQ_API_KEY:
                print("❌ Error: GROQ_API_KEY not found in .env file")
                print("Please add your Groq API key to the .env file")
                raise ValueError("Missing GROQ_API_KEY")
            else:
                print(f"✅ Configuration loaded: Provider={self.AI_PROVIDER}, Model={self.AI_MODEL}")
        elif self.AI_PROVIDER == "deepseek":
            if not self.DEEPSEEK_API_KEY:
                print("❌ Error: DEEPSEEK_API_KEY not found in .env file")
                print("Please add your DeepSeek API key to the .env file")
                raise ValueError("Missing DEEPSEEK_API_KEY")
            else:
                print(f"✅ Configuration loaded: Provider={self.AI_PROVIDER}, Model={self.AI_MODEL}")
        elif self.AI_PROVIDER == "openai":
            if not self.OPENAI_API_KEY:
                print("❌ Error: OPENAI_API_KEY not found in .env file")
                print("Please add your OpenAI API key to the .env file")
                raise ValueError("Missing OPENAI_API_KEY")
            else:
                print(f"✅ Configuration loaded: Provider={self.AI_PROVIDER}, Model={self.AI_MODEL}")
        else:
            print(f"⚠️  Warning: Unknown AI_PROVIDER '{self.AI_PROVIDER}'. AI features may not work.")
            print(f"✅ Configuration loaded: Provider={self.AI_PROVIDER}, Model={self.AI_MODEL}")