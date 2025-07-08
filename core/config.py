import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME = "Feedback App"
    DB_URL = os.getenv("DB_URL")
    ...

settings = Settings()

