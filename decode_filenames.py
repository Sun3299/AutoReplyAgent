#!/usr/bin/env python3
import subprocess

# Get ls-tree from git
result = subprocess.run(['git', 'ls-tree', '-r', 'HEAD', '--', 'img/'],
                       capture_output=True, text=False)
output = result.stdout.decode('utf-8', errors='replace')

for line in output.strip().split('\n'):
    if not line:
        continue
    parts = line.split('\t')
    if len(parts) != 2:
        continue
    # Format: 100644 blob HASH\tPATH
    hash_part = parts[0].split()[2]
    path_bytes = parts[1].encode('latin-1')
    try:
        decoded_path = path_bytes.decode('utf-8')
    except:
        decoded_path = path_bytes.decode('latin-1')
    print(f'{hash_part}: {decoded_path}')
