import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

from core.db.base import Base

# Explicitly import the model classes so Alembic detects them
from models.user import User
from models.otp import OTP_Tbl
from models.feedback import Feedback, FeedbackStatus
from models.developer import Developer
from models.feedback_developer import FeedbackDeveloper  


target_metadata = Base.metadata

# Load environment variables
load_dotenv()

# DB URL from .env
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


# Alembic Config object
config = context.config
fileConfig(config.config_file_name)

# Override DB URL
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Target metadata for autogenerate
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(url=DATABASE_URL, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
