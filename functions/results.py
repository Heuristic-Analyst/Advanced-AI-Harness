# results.py — tool results too long for the context. they are saved into the conversation's results/ folder,
# cut into parts, and the model only gets a short preview: the start, the end, and where the rest is.
#   Conversations/<name>/results/results-1.json     {"1": "the first 4000 characters", "2": "the next 4000", ...}
#   Conversations/<name>/results/results-2.json     the next long result, and so on
# the model reads them with read_result (one part at a time) and searches them with search_result.
# everything is counted in characters, never in tokens: the same for every model.

import os
import re
import json
from config import RESULT_LIMIT, RESULT_PART, RESULT_PREVIEW
from functions.read_json import read_json

NAME = r"results-[0-9]+"                               # what a result's name looks like: results-1, results-2, ...
                                                       # nothing else is ever read: no / or .., so never another folder


def shorten(folder, text):
    """the tool result as the model gets it: short ones as they are. long ones (more than RESULT_LIMIT characters)
    are saved into folder, and the model gets a preview instead. folder None: no place to save, so as it is"""
    if len(text) <= RESULT_LIMIT or not folder:
        return text
    name, count = save(folder, text)
    return preview(name, text, count)


def save(folder, text):
    """cut text into parts of RESULT_PART characters and save them as folder/results-<n>.json, as a dict:
    {"1": part 1, "2": part 2, ...}. returns the result's name (results-3) and how many parts it has"""
    parts = {}
    number = 1
    for start in range(0, len(text), RESULT_PART):     # 0, 4000, 8000, ...: where each part starts
        parts[str(number)] = text[start:start + RESULT_PART]
        number += 1
    os.makedirs(folder, exist_ok=True)                 # the folder appears with the first long result
    name = "results-" + str(next_number(folder))
    with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(parts, f, indent=1, ensure_ascii=False)
    return name, len(parts)


def next_number(folder):
    """the number for the next result: one more than the highest one in the folder. so after /open the counting
    goes on, and a name is never used twice in one conversation"""
    highest = 0
    for file in os.listdir(folder):
        found = re.fullmatch(r"results-([0-9]+)\.json", file)   # results-12.json -> "12"
        if found:
            highest = max(highest, int(found.group(1)))
    return highest + 1


def preview(name, text, count):
    """what the model gets instead of a long result: where it is, how big, the start and the end"""
    return ("[this result is too long (" + format(len(text), ",") + " characters). it is saved as "
            + name + ", in " + str(count) + (" part" if count == 1 else " parts")
            + " of up to " + format(RESULT_PART, ",") + " characters. "
            "read_result shows one part, search_result finds lines in it. its start and its end:]\n"
            + text[:RESULT_PREVIEW] + "\n[...]\n" + text[-RESULT_PREVIEW:])


def load(folder, name):
    """the parts of one saved result, as a dict {"1": ..., "2": ...}. None if there is no such result in folder"""
    if not folder or not re.fullmatch(NAME, str(name)):   # only a real result name, never a path from the model
        return None
    path = os.path.join(folder, name + ".json")
    if not os.path.isfile(path):
        return None
    return read_json(path)


def not_found(folder, name):
    """the answer when there is no result with that name: which ones there are"""
    found = []
    if folder and os.path.isdir(folder):
        numbers = [int(f[len("results-"):-len(".json")]) for f in os.listdir(folder)
                   if re.fullmatch(r"results-[0-9]+\.json", f)]
        found = ["results-" + str(n) for n in sorted(numbers)]   # sorted as numbers: 2 before 10
    return "there is no result called '" + str(name) + "'. yours: " + (", ".join(found) or "none yet")
