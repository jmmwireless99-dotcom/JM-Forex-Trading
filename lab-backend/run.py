#!/usr/bin/env python3
"""Run JM Lab trading API (port 8001 by default)."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)
