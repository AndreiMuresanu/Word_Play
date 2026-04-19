import os
import re
import hashlib
from pathlib import Path

SRC_DIR = Path("sprite_library/src")

def get_file_hash(filepath):
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

def simplify_name(name):
    # Remove file extension for processing
    base, ext = os.path.splitext(name)
    base = base.lower()
    
    # Remove specific patterns
    base = re.sub(r'[-_]type[-_]?\d+[-_]?\d*', '', base) # -type-01-01
    base = re.sub(r'[-_]large', '', base)
    base = re.sub(r'[-_]small', '', base)
    
    # Dawnlike common suffixes
    base = re.sub(r'_[01]$', '', base) # _0, _1
    
    # CDDA common prefixes/suffixes
    
    # replace spaces and dashes with underscores
    base = base.replace(' ', '_').replace('-', '_')
    
    # remove duplicate underscores
    base = re.sub(r'_+', '_', base)
    
    # trim underscores from edges
    base = base.strip('_')
    
    return base + ext

seen_hashes = set()
redundant_deleted = 0
renamed_count = 0

for root, _, files in os.walk(SRC_DIR):
    folder_name_counts = {}
    
    for file in files:
        if not file.endswith('.png'): continue
        
        file_path = Path(root) / file
        
        # 1. Deduplication by content hash
        file_hash = get_file_hash(file_path)
        if file_hash in seen_hashes:
            os.remove(file_path)
            redundant_deleted += 1
            print(f"Deleted duplicate: {file_path}")
            continue
            
        seen_hashes.add(file_hash)
        
        # 2. Simplify name
        new_name = simplify_name(file)
        
        # 3. Handle naming collisions in the same folder
        base, ext = os.path.splitext(new_name)
        
        counter = 1
        proposed_name = new_name
        # If proposed name exists and it's not our current file, increment
        while (Path(root) / proposed_name).exists() and proposed_name != file:
            proposed_name = f"{base}_{counter}{ext}"
            counter += 1
            
        new_name = proposed_name
        
        if new_name != file:
            os.rename(file_path, Path(root) / new_name)
            renamed_count += 1
            print(f"Renamed: {file} -> {new_name}")

print(f"Deleted {redundant_deleted} redundant duplicate files.")
print(f"Simplified names for {renamed_count} files.")
