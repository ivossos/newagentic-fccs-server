
import os

def find_string_in_binary(target_string, search_dir='.'):
    found_files = []
    target_bytes = target_string.encode('utf-8')
    for root, dirs, files in os.walk(search_dir):
        if 'venv' in dirs:
            dirs.remove('venv')
        for file in files:
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'rb') as f:
                    if target_bytes in f.read():
                        found_files.append(file_path)
            except:
                pass
    return found_files

if __name__ == "__main__":
    for s in ["dashboard", "Dashboard", "RLE"]:
        files = find_string_in_binary(s)
        if files:
            print(f"String '{s}' found in: {files}")

