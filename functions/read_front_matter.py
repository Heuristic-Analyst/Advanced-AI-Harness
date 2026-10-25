def read_front_matter(file_path):
    """a file that starts with a header between two '---' lines, one 'key: value' per line (SKILL.md, later
    templates). returns the header as a dict, and the text after the header:
        ---
        name: commit-message                  ->  header = {"name": "commit-message",
        description: Use when ...                           "description": "Use when ..."}
        ---
        # Writing commit messages             ->  body = "# Writing commit messages\n1. ..."
        1. ..."""
    header = {}
    body = ""
    dashes = 0                                               # how many '---' lines we passed: 0 before, 1 inside, 2 after
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            if line.strip() == "---" and dashes < 2:         # a '---' line opens or closes the header
                dashes += 1
            elif dashes == 1:                                # inside the header: "key: value"
                if ":" in line:
                    key, value = line.split(":", 1)          # split at the FIRST ":" only: the value may have more
                    header[key.strip()] = value.strip().strip('"\'')   # no spaces, then no quotes: "x" -> x
            else:                                            # before or after the header: the body
                body += line
    return header, body.strip()
