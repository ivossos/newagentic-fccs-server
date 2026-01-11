
import os

def find_e7_text():
    extensions = ('.py', '.csv', '.json', '.toml', '.md', '.txt', '.pyw', '.sh', '.bat', '.ps1')
    for root, dirs, files in os.walk('.'):
        if 'venv' in dirs:
            dirs.remove('venv')
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        if '.git' in dirs:
            dirs.remove('.git')
        for file in files:
            if not file.endswith(extensions):
                continue
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                    if b'\xe7' in content:
                        print(f"File {file_path} contains 0xe7")
                        lines = content.split(b'\n')
                        for i, line in enumerate(lines):
                            if b'\xe7' in line:
                                print(f"  Line {i+1}: {line}")
            except Exception as e:
                print(f"Error reading {file_path}: {e}")

if __name__ == "__main__":
    find_e7_text()

