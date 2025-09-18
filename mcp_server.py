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


def fetch_documents(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch documents from a repository search API.
    Expects REPO_SERVER_URL to be set. Returns a list of dicts:
      id, title, url, content_type, content, meta
    """
    logger.info("fetch_documents called q=%r limit=%s", query, limit)

    if not REPO_SERVER_URL:
        logger.error("REPO_SERVER_URL not set — fetch_documents will return []")
        return []

    try:
        r = requests.get(REPO_SERVER_URL, params={"q": query, "limit": limit}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:
        logger.exception("Error fetching docs from repo search: %s", e)
        return []

    documents: List[Dict[str, Any]] = []

    # Case 1: payload has {"result": { service: { "documents": [...] } } }
    if isinstance(payload, dict) and "result" in payload and isinstance(payload["result"], dict):
        result_obj = payload["result"]
        for svc_val in result_obj.values():
            if not isinstance(svc_val, dict):
                continue
            docs = svc_val.get("documents", []) or []
            for d in docs:
                doc_data = (d.get("document") or {}) if isinstance(d, dict) else {}
                raw_text = doc_data.get("text", [])
                if isinstance(raw_text, list):
                    content = "\n".join([str(s) for s in raw_text if s is not None])
                else:
                    content = str(raw_text or "")
                doc_item = {
                    "id": d.get("id") or doc_data.get("id") or "",
                    "title": doc_data.get("title") or doc_data.get("url") or "",
                    "url": doc_data.get("url") or "",
                    "content_type": doc_data.get("content_type") or "text/markdown",
                    "content": content,
                    "meta": {"position": d.get("position"), "fieldCount": d.get("fieldCount")}
                }
                documents.append(doc_item)

    # Case 2: payload is {"documents": [...]}
    elif isinstance(payload, dict) and "documents" in payload and isinstance(payload["documents"], list):
        for d in payload["documents"]:
            if not isinstance(d, dict):
                continue
            doc_data = d.get("document") or d
            raw_text = doc_data.get("text", []) if isinstance(doc_data, dict) else ""
            if isinstance(raw_text, list):
                content = "\n".join([str(s) for s in raw_text if s is not None])
            else:
                content = str(raw_text or doc_data.get("content", "") if isinstance(doc_data, dict) else "")
            doc_item = {
                "id": d.get("id") or (doc_data.get("id") if isinstance(doc_data, dict) else ""),
                "title": (doc_data.get("title") if isinstance(doc_data, dict) else "") or "",
                "url": doc_data.get("url") if isinstance(doc_data, dict) else "",
                "content_type": doc_data.get("content_type") if isinstance(doc_data, dict) else "text/markdown",
                "content": content,
                "meta": {"position": d.get("position"), "fieldCount": d.get("fieldCount")}
            }
            documents.append(doc_item)

    # Case 3: payload is a list of document-like dicts
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            content = ""
            if "content" in item and item.get("content") is not None:
                content = str(item.get("content"))
            elif "text" in item and item.get("text") is not None:
                raw_text = item.get("text")
                if isinstance(raw_text, list):
                    content = "\n".join([str(s) for s in raw_text if s is not None])
                else:
                    content = str(raw_text)
            doc_item = {
                "id": item.get("id", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content_type": item.get("content_type", "text/markdown"),
                "content": content,
                "meta": {"position": item.get("position"), "fieldCount": item.get("fieldCount")}
            }
            documents.append(doc_item)

    else:
        logger.warning("Unexpected repo response shape; returning empty list")

    logger.info("fetch_documents returning %d documents", len(documents))
    return documents[:limit]


# Expose the MCP tool
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
