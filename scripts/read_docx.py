
try:
    from docx import Document
    import sys

    def read_docx(file_path):
        doc = Document(file_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        return '\n'.join(full_text)

    if __name__ == "__main__":
        if len(sys.argv) < 2:
            print("Usage: python read_docx.py <file_path>")
            sys.exit(1)
        print(read_docx(sys.argv[1]))
except ImportError:
    print("python-docx not installed.")

