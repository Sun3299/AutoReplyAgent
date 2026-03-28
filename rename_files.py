#!/usr/bin/env python3
"""Rename git files to match README references."""
import subprocess
import os
import re

os.chdir(r'C:\Users\AAA\Desktop\autoreply')

# Map: (blob_hash, size) -> desired_filename
# From git ls-tree analysis:
blob_info = {
    '28fdb132a6770d294f14ad15af0c37400572ad05': ('RAG检索.png', 101288),
    'd770b449437f1fe414b2dcfffccfd452ce30ef89': ('RAG知识库.png', 425773),
    '8927018d6ab84fa7715fffa392334c9871d48f98': ('memory对话框.png', 101240),
    '2657a0aa7abd03c13ea2a9643b13f37966eaef7e': ('自动回复流程图.jpg', 82830),
}

# Get git tree (names are escaped in output)
r = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--', 'img/'], capture_output=True)

# Parse blob hash and escaped filename
current_map = {}  # blob_hash -> current_filename (escaped)
for line in r.stdout.split(b'\n'):
    if not line:
        continue
    parts = line.split()
    if len(parts) < 4:
        continue
    blob_hash = parts[2].decode('ascii')
    # path is like b'"img/RAG\\346\\265\\213\\350\\257\\225.png"'
    path_bytes = parts[3]
    # Strip quotes
    path_str = path_bytes.decode('ascii', errors='replace').strip('"')
    # Extract just the filename (after img/)
    if b'img/' in path_bytes:
        filename = path_bytes.split(b'img/')[1].strip(b'"')
        # Decode octal escapes
        def decode_octal(m):
            return chr(int(m.group(1), 8))
        decoded_bytes = re.sub(rb'\\([0-7]{3})', lambda m: bytes([int(m.group(1), 8)]), filename)
        decoded = decoded_bytes.decode('utf-8', errors='replace')
        current_map[blob_hash] = decoded

print('Current files in git:')
for h, name in current_map.items():
    desired = blob_info.get(h, ('?', 0))[0]
    print(f'  {h[:8]}: {name!r} -> want: {desired!r}')

# For each file that needs renaming:
# 1. Extract blob content to a temp file with correct name (using Python file I/O)
# 2. git add the new file
# 3. git rm the old file

for blob_hash, (desired_name, size) in blob_info.items():
    if blob_hash not in current_map:
        print(f'SKIP: {blob_hash[:8]} not in tree')
        continue
    
    current_name = current_map[blob_hash]
    if current_name == desired_name:
        print(f'OK: {desired_name} already correct')
        continue
    
    print(f'Renaming: {current_name!r} -> {desired_name!r}')
    
    # Step 1: Extract blob content
    r2 = subprocess.run(['git', 'cat-file', '-p', blob_hash], capture_output=True)
    if r2.returncode != 0:
        print(f'  FAILED to extract blob')
        continue
    
    # Write to a temp file with the correct name in img/
    new_path = os.path.join('img', desired_name)
    with open(new_path, 'wb') as f:
        f.write(r2.stdout)
    print(f'  Wrote content to {new_path}')
    
    # Step 2: git add the new file
    r3 = subprocess.run(['git', 'add', new_path], capture_output=True)
    if r3.returncode != 0:
        print(f'  FAILED to git add: {r3.stderr.decode("utf-8", errors="replace")}')
        continue
    print(f'  git add {new_path} OK')
    
    # Step 3: git rm the old file from index (use --cached to only remove from index)
    old_path = os.path.join('img', current_name)
    r4 = subprocess.run(['git', 'rm', '--cached', '--', old_path], capture_output=True)
    if r4.returncode != 0:
        print(f'  FAILED to git rm --cached: {r4.stderr.decode("utf-8", errors="replace")[:200]}')
        continue
    print(f'  git rm --cached {old_path} OK')

print('\nDone. Check git status.')
