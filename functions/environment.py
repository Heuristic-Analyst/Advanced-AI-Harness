import os
def read_key(provider, file_path):
    """the line PROVIDER_API_KEY=... from .env, for the provider in MODEL. None if there is none
    (fine for local models like ollama). the key never goes into the environment"""
    if not os.path.isfile(file_path):                     # no .env at all: no key, no crash
        return None
    with open(file_path, encoding="utf-8") as f:          # "with" closes the file again when we're done
        for line in f:
            if line.startswith(provider + "_API_KEY="):
                return line.split("=", 1)[1].strip().strip("'\"")   # everything after the first "=", without quotes
    return None
