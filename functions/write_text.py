import os
def write_text(file_path, text):
    """write text into a file, replacing what was there. a missing folder is created first. first into a temporary
    file, then swapped in: if the program dies in the middle of writing, the old file is still whole"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    temporary = file_path + ".saving"
    with open(temporary, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    os.replace(temporary, file_path)                      # the swap: one step, never half a file
