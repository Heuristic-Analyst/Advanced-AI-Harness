import os
import json
def read_json(file_path):
    """the json file at file_path, as python data (dict, list, ...). missing or broken: a clear error"""
    if not os.path.isfile(file_path):                     # a file we need: say so plainly
        raise FileNotFoundError(file_path + " is missing")
    with open(file_path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except ValueError as e:
            raise ValueError(file_path + " is not valid json: " + str(e))
