#!/usr/bin/env python3
import subprocess
import re

# Get README image refs
r = subprocess.run(['git', 'show', 'HEAD:README.md'], capture_output=True)
data = r.stdout

print('=== README image refs ===')
for m in re.finditer(rb'img/([^)]+\.(?:jpg|png))', data):
    path_bytes = m.group(1)
    decoded = path_bytes.decode('utf-8', errors='replace')
    print(f'  {decoded}')

print()

# Get git tree filenames
r2 = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--', 'img/'], capture_output=True)
print('=== Git tree filenames ===')
for line in r2.stdout.split(b'\n'):
    if not line: continue
    parts = line.split()
    if len(parts) < 4: continue
    path_bytes = parts[3]
    # Strip quotes
    path_str = path_bytes.decode('ascii', errors='replace').strip('"')
    # Get just the filename part
    if 'img/' in path_str:
        filename = path_str.split('img/')[1]
        print(f'  {filename}')
