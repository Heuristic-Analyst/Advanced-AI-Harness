import os
def read_text(file_path):
    """the whole text of a file, without empty lines or spaces around it. missing file = empty text, no crash
    (for files that are allowed to be empty or missing, like the soul: the caller decides what then)"""
    if not os.path.isfile(file_path):                     # missing: empty text
        return ""
    with open(file_path, encoding="utf-8") as f:          # "with" closes the file again when we're done
        return f.read().strip()
