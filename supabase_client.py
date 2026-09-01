import os
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Create and reuse the application's Supabase client."""
    supabase_url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    # Accept both the normal project URL and the REST endpoint format that
    # appeared in early InternShield setup instructions.
    supabase_url = supabase_url.removesuffix("/rest/v1")
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Supabase is not configured. Add SUPABASE_URL and "
            "SUPABASE_KEY to the project's .env file."
        )

    return create_client(supabase_url, supabase_key)