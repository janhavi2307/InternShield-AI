import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase credentials are missing. Check your .env file."
    )


def get_supabase_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)