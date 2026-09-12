import os
from uuid import uuid4


_LOCAL_PAPERS: dict[str, dict] = {}


def _supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        return None

    from supabase import create_client

    return create_client(url, key)


def save_paper(paper: dict) -> str:
    client = _supabase_client()
    if client is None:
        paper_id = str(uuid4())
        _LOCAL_PAPERS[paper_id] = {"id": paper_id, **paper}
        return paper_id

    response = client.table("papers").insert(paper).execute()
    if not response.data:
        raise RuntimeError("Supabase did not return the saved paper.")
    return str(response.data[0]["id"])


def get_paper(paper_id: str) -> dict | None:
    client = _supabase_client()
    if client is None:
        return _LOCAL_PAPERS.get(paper_id)

    try:
        response = client.table("papers").select("*").eq("id", paper_id).maybe_single().execute()
    except Exception as exc:
        if getattr(exc, "code", None) == "204":
            return None
        raise
    return response.data