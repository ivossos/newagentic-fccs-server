
import os

def find_e7():
    for root, dirs, files in os.walk('.'):
        if 'venv' in dirs:
            dirs.remove('venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        for file in files:
            file_path = os.path.join(root, file)
            if file.endswith(('.png', '.docx', '.db', '.db.old', '.pyc')):
                continue
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    if b'\xe7' in content:
                        print(f"File {file_path} contains 0xe7")
                        # Find line number
                        lines = content.split(b'\n')
                        for i, line in enumerate(lines):
                            if b'\xe7' in line:
                                print(f"  Line {i+1}: {line}")
            except Exception as e:
                pass

if __name__ == "__main__":
    find_e7()

