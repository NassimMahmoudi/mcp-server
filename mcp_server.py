# mcp_server.py
import os
import json
import logging
from typing import List, Dict, Any
from fastmcp import FastMCP
from dotenv import load_dotenv
import requests

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server")

# MCP server label can be anything; keep consistent with clients that call it.
mcp = FastMCP("SearchServer")

# Config (REPO_SERVER_URL must be set in the environment)
REPO_SERVER_URL = os.environ.get("REPO_SERVER_URL", "https://qsc.quasiris.de/api/v1/search/quasiris/qsc-documentation-nam").strip()
REQUEST_TIMEOUT = float(os.environ.get("REPO_REQUEST_TIMEOUT", "10"))


def _ensure_content_in_document_obj(doc_obj):
    """
    If doc_obj contains a 'text' (string or list) or nested 'document' with 'text',
    ensure the corresponding 'content' field exists by concatenating text if needed.
    This mutates doc_obj in-place and does nothing else.
    """
    if not isinstance(doc_obj, dict):
        return

    # nested 'document' preferred
    nested = doc_obj.get("document")
    if isinstance(nested, dict):
        if not nested.get("content"):
            raw = nested.get("text")
            if isinstance(raw, list):
                nested["content"] = "\n".join([str(s) for s in raw if s is not None])
            else:
                nested["content"] = str(raw or "")
        return

    # top-level
    if not doc_obj.get("content"):
        raw = doc_obj.get("text")
        if isinstance(raw, list):
            doc_obj["content"] = "\n".join([str(s) for s in raw if s is not None])
        else:
            doc_obj["content"] = str(raw or "")


def fetch_documents(query: str, limit: int = 20):
    """
    Call the fetch endpoint and return its full payload, but ensure each document
    (either in result->...->documents or payload['documents'] or top-level list)
    has a 'content' field created from 'text' when needed.
    """
    logger.info("fetch_documents called q=%r limit=%s", query, limit)

    try:
        r = requests.get(REPO_SERVER_URL, params={"q": query, "limit": limit}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.exception("Error fetching docs from repo search: %s", e)
        return {}

    # If payload has result -> services -> documents
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        for svc in payload["result"].values():
            if not isinstance(svc, dict):
                continue
            docs = svc.get("documents", []) or []
            for d in docs:
                if isinstance(d, dict):
                    _ensure_content_in_document_obj(d)

    # If payload has top-level 'documents'
    elif isinstance(payload, dict) and isinstance(payload.get("documents"), list):
        for d in payload["documents"]:
            if isinstance(d, dict):
                _ensure_content_in_document_obj(d)

    # If payload is a plain list of docs
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                _ensure_content_in_document_obj(item)

    # else: leave payload untouched

    return payload

# Search MCP tool
@mcp.tool(name="search_documents_tool")
async def search_documents_tool(query: str, limit: int = 20):
    """
    Tool signature: search_documents_tool(query: str, limit: int = 20)
    Returns a JSON-serializable list of documents.
    """
    logger.info("search_documents_tool called q=%r limit=%s", query, limit)
    try:
        docs = fetch_documents(query, limit=limit)
        return json.loads(json.dumps(docs))
    except Exception as e:
        logger.exception("search_documents_tool failed: %s", e)
        return []


if __name__ == "__main__":
    logger.info("Starting MCP Search server on http://0.0.0.0:8080/mcp")
    try:
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
    except Exception:
        logger.exception("MCP server terminated.")
