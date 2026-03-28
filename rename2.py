#!/usr/bin/env python3
"""Fix image filenames using blob hashes and git rm --cached."""
import subprocess
import os

os.chdir(r'C:\Users\AAA\Desktop\autoreply')

# Based on git ls-tree, the files in tree are:
# blob 28fdb13 -> img/RAG\346\265\213\350\257\225.png (WRONG - should be RAG检索.png)
# blob d770b44 -> img/RAG\347\237\245\350\257\206\345\272\223.png (RAG知识库.png - correct)
# blob 8927018 -> img/memory\346\226\207\346\241\243.png (WRONG - should be memory对话框.png)
# blob 2657a0aa -> img/\350\207\252\345\256\232\344\271\211\351\230\266\346\242\257\345\274\217\350\256\256\344\273\267.jpg (WRONG - should be 自动回复流程图.jpg)

# Map: blob_hash -> (correct_name, size)
blob_to_file = {
    b'28fdb132a6770d294f14ad15af0c37400572ad05': ('RAG检索.png', 101288),
    b'd770b449437f1fe414b2dcfffccfd452ce30ef89': ('RAG知识库.png', 425773),
    b'8927018d6ab84fa7715fffa392334c9871d48f98': ('memory对话框.png', 101240),
    b'2657a0aa7abd03c13ea2a9643b13f37966eaef7e': ('自动回复流程图.jpg', 82830),
}

# Get current tree
r = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--', 'img/'], capture_output=True)

# Parse to get blob -> current_git_path
blob_to_current = {}
for line in r.stdout.split(b'\n'):
    if not line:
        continue
    parts = line.split()
    if len(parts) < 4:
        continue
    blob = parts[2]
    path_bytes = parts[3]
    blob_to_current[blob] = path_bytes

print('Parsed tree:')
for blob, path in blob_to_current.items():
    desired = blob_to_file.get(blob, ('?', 0))[0]
    print(f'  {blob[:8]}: path={path} desired={desired}')

# For each file that needs renaming
for blob, (correct_name, size) in blob_to_file.items():
    if blob not in blob_to_current:
        print(f'SKIP: blob {blob[:8]} not in tree')
        continue
    
    current_path_bytes = blob_to_current[blob]  # e.g., b'"img/RAG\\346..."'
    # Extract just the path part (strip quotes)
    current_path_str = current_path_bytes.decode('ascii', errors='replace').strip('"')
    
    # The current git tree path (escaped form)
    current_git_path = current_path_str  # e.g., 'img/RAG\\346\\265\\213...'
    
    # The correct path
    correct_git_path = f'img/{correct_name}'
    
    if current_git_path == correct_git_path:
        print(f'OK (no rename needed): {correct_name}')
        continue
    
    print(f'\nRenaming blob {blob[:8]}: {current_git_path!r} -> {correct_git_path!r}')
    
    # Step 1: Extract blob content and write to correct filename
    r2 = subprocess.run(['git', 'cat-file', '-p', str(blob.decode())], capture_output=True)
    if r2.returncode != 0:
        print(f'  ERROR: failed to extract blob')
        continue
    
    # Write the content to the correct filename
    with open(correct_git_path, 'wb') as f:
        f.write(r2.stdout)
    print(f'  Wrote content to {correct_git_path}')
    
    # Verify size
    actual_size = os.path.getsize(correct_git_path)
    print(f'  File size: {actual_size} (expected {size})')
    
    # Step 2: git add the new file
    r3 = subprocess.run(['git', 'add', correct_git_path], capture_output=True)
    if r3.returncode != 0:
        print(f'  ERROR: git add failed')
        continue
    print(f'  git add OK')
    
    # Step 3: git rm --cached the OLD file (using the escaped path from tree)
    r4 = subprocess.run(['git', 'rm', '--cached', '--', current_git_path], capture_output=True)
    if r4.returncode != 0:
        print(f'  ERROR: git rm --cached failed for {current_git_path!r}')
        print(f'    stderr: {r4.stderr.decode("utf-8", errors="replace")[:200]}')
        continue
    print(f'  git rm --cached {current_git_path!r} OK')

print('\n=== Final status ===')
r5 = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
print(r5.stdout)
