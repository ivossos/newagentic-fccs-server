import os

def find_byte_e7():
    for root, dirs, files in os.walk('fccs_agent'):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                try:
                    with open(path, 'rb') as file:
                        content = file.read()
                        if b'\xe7' in content:
                            print(f"Found 0xe7 in {path}")
                except Exception as e:
                    print(f"Error reading {path}: {e}")

if __name__ == "__main__":
    find_byte_e7()

