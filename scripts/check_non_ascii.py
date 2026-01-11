
import os

def check_non_ascii(search_dir='.'):
    for root, dirs, files in os.walk(search_dir):
        if 'venv' in dirs:
            dirs.remove('venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith('.png') or file.endswith('.docx') or file.endswith('.db') or file.endswith('.db.old') or file.endswith('.pyc'):
                continue
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    for i, b in enumerate(content):
                        if b == 0xe7:
                            print(f"Target byte 0xe7 found at position {i} in {file_path}")
                            # Print a bit of context
                            start = max(0, i - 40)
                            end = min(len(content), i + 40)
                            try:
                                context = content[start:end].decode('latin-1')
                                print(f"Context (latin-1): {context}")
                            except:
                                print(f"Context (hex): {content[start:end].hex()}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

if __name__ == "__main__":
    check_non_ascii()

