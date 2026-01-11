
import os

def check_encodings(search_dir='.'):
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
                    content.decode('utf-8')
            except UnicodeDecodeError as e:
                print(f"File {file_path} is NOT UTF-8: {e}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

if __name__ == "__main__":
    check_encodings()

