
import os
import sys

def check_env():
    print(f"Python version: {sys.version}")
    print(f"Default encoding: {sys.getdefaultencoding()}")
    print(f"Filesystem encoding: {sys.getfilesystemencoding()}")
    
    for k, v in os.environ.items():
        try:
            k.encode('utf-8')
            v.encode('utf-8')
        except UnicodeEncodeError:
            print(f"Environment variable {k} has non-UTF8 value!")
            # print(f"Value (latin-1): {v.encode('latin-1').decode('latin-1')}")

if __name__ == "__main__":
    check_env()

