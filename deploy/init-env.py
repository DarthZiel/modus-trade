#!/usr/bin/env python3
"""Create fresh production secrets without printing or replacing an existing file."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
content = (root / 'deploy/production.env.example').read_text()
content = content.replace('POSTGRES_PASSWORD=\n', f'POSTGRES_PASSWORD={secrets.token_urlsafe(36)}\n')
content = content.replace('BOT_API_SECRET=\n', f'BOT_API_SECRET={secrets.token_urlsafe(36)}\n')
with open(os.open(root / '.env.production', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as target:
    target.write(content)
print('Created .env.production (mode 600). Existing files are never overwritten.')
