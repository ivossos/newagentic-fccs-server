
import os

def find_byte_in_files(target_byte, search_dir='.'):
    found_files = []
    for root, dirs, files in os.walk(search_dir):
        if 'venv' in dirs:
            dirs.remove('venv')
        if '.git' in dirs:
            dirs.remove('.git')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
            
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    if target_byte in content:
                        found_files.append(file_path)
            except Exception:
                pass
    return found_files

if __name__ == "__main__":
    target = b'\xe7'
    files = find_byte_in_files(target)
    for f in files:
        print(f)

