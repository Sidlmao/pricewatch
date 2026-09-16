#!/usr/bin/env python3
"""Render the dashboard as a static page (site/index.html) for GitHub Pages."""
import os
from app import app, render_page

repo = os.getenv("GITHUB_REPOSITORY")  # set automatically inside GitHub Actions
manage = f"https://github.com/{repo}/actions/workflows/manage.yml" if repo else None
with app.test_request_context():
    html = render_page(static=True, manage_url=manage)
os.makedirs("site", exist_ok=True)
with open("site/index.html", "w") as f:
    f.write(html)
print(f"wrote site/index.html ({len(html)} bytes)")
