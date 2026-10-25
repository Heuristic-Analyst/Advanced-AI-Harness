# tools/results/search_result.py — grep for ONE saved result (functions/results.py). the parts of the result are
# glued back together first, so a line cut between two parts is still found whole. every line it shows says which
# part it is in (so the model knows what to read_result next) and its line number.
# done with python's re module, not the grep program: the same on windows, mac and linux, nothing to install.
# a long answer from this tool is saved as a result itself. that is on purpose: search that one again, narrower.
#
#   option          grep     what it does
#   regex           -E       pattern is a regular expression (python's syntax: error|warn, ^line 1, \d+, ...)
#   ignore_case     -i       upper/lower case doesn't matter
#   whole_word      -w       only whole words: "log" matches "log", not "login"
#   invert          -v       the lines that do NOT match
#   before / after  -B / -A  also show this many lines before / after each match
#   only_matching   -o       only the matched pieces, not the whole lines
#   count           -c       only how many lines match
#   max_count       -m       stop after this many matching lines

import re
from functions import results

AROUND = 150                                         # a very long line (e.g. one-line json) is shown only this many
                                                     # characters before and after its match


def run(agent, name, pattern, regex=False, ignore_case=False, whole_word=False, invert=False,
        before=0, after=0, only_matching=False, count=False, max_count=0):
    parts = results.load(agent.results_dir, name)    # only this conversation's results folder
    if parts is None:
        return results.not_found(agent.results_dir, name)
    if pattern == "":
        return "give a pattern to search for"

    # 1. the pattern, as grep would read it with these options
    text = pattern if regex else re.escape(pattern)  # not a regex: escape it, so . * ( | mean only themselves
    if whole_word:
        text = r"(?<!\w)(?:" + text + r")(?!\w)"    # no letter, digit or _ right before or after it, like grep -w
    try:
        finder = re.compile(text, re.IGNORECASE if ignore_case else 0)
    except re.error as e:                            # a broken regex: say why, so the model can fix it
        return "that regex doesn't work: " + str(e)
    before, after, max_count = max(0, int(before)), max(0, int(after)), max(0, int(max_count))   # "2" -> 2, no < 0

    # 2. the result, glued back together and cut into lines
    lines, starts, part_at = glue(parts)

    # 3. which lines match. invert: the ones that don't. max_count: stop after that many
    hits = []
    for number, line in enumerate(lines):
        if bool(finder.search(line)) != invert:      # a match (or, with invert, a line without one)
            hits.append(number)
            if max_count and len(hits) == max_count:
                break
    stopped = " (stopped at max_count " + str(max_count) + ")" if max_count and len(hits) == max_count else ""
    if count:
        return name + ": " + str(len(hits)) + " matching line(s)" + stopped
    if not hits:
        return "no line in " + name + " matches '" + pattern + "'"

    # 4. what to show. each line: "part 2, line 150: ..." for a match, "part 2, line 149- ..." for a line around one
    shown = []
    if only_matching and not invert:                 # -o: only the matched pieces, each on its own line
        for number in hits:
            for found in finder.finditer(lines[number]):
                if found.group(0):                   # an empty match (e.g. regex a*) shows nothing, like grep
                    shown.append(label(part_at(starts[number] + found.start()), number, ":") + found.group(0))
    else:
        matching = set(hits)                         # a set: "is this line a match?" is quick to ask
        wanted = set()                               # the matching lines, plus the lines before and after them
        for number in hits:
            wanted.update(range(max(0, number - before), min(len(lines), number + after + 1)))
        last = None
        for number in sorted(wanted):
            if (before or after) and last is not None and number != last + 1:
                shown.append("--")                   # lines left out in between. like grep: only when lines
                                                     # around the matches are shown, otherwise every gap would get one
            found = finder.search(lines[number]) if number in matching and not invert else None
            where = starts[number] + (found.start() if found else 0)   # the part of the match, or of the line start
            mark = ":" if number in matching else "-"
            shown.append(label(part_at(where), number, mark) + cut(lines[number], found))
            last = number

    return (name + ": " + str(len(hits)) + " matching line(s)" + stopped + ". 'line 150:' = a matching line, "
            "'line 149-' = a line around one, '--' = lines left out. read_result shows a whole part:\n"
            + "\n".join(shown))


def glue(parts):
    """the parts glued back together, cut into lines. returns the lines, where each line starts in the glued text,
    and a function that says which part a position is in (from the real parts, so it stays right even if
    RESULT_PART was changed since this result was saved)"""
    whole = ""
    ends = []                                        # where each part ends in the glued text
    for number in range(1, len(parts) + 1):
        whole += parts[str(number)]
        ends.append(len(whole))
    lines = whole.split("\n")
    starts = []
    position = 0
    for line in lines:
        starts.append(position)
        position += len(line) + 1                    # + 1: the "\n" that split() took away

    def part_at(position):
        part = 1
        while part < len(ends) and position >= ends[part - 1]:
            part += 1
        return part
    return lines, starts, part_at


def label(part, number, mark):
    return "part " + str(part) + ", line " + str(number + 1) + mark + " "   # number + 1: lines counted from 1


def cut(line, found):
    """a very long line: only the piece around the match (or its start, for a line without one)"""
    if len(line) <= 2 * AROUND + 50:
        return line
    at = found.start() if found else 0
    start = max(0, at - AROUND)
    return ("..." if start > 0 else "") + line[start:at + AROUND] + "..."   # "..." only where something is left out


TOOL = {
    "name": "search_result",
    "description": "grep for one of your saved results (tool results too long for your context, saved as results-1, "
                   "results-2, ...). Shows every matching line with its part and line number, so you know which "
                   "part to read with read_result. The options work like grep's: regex (-E), ignore_case (-i), "
                   "whole_word (-w), invert (-v), before / after (-B / -A) for lines around each match, "
                   "only_matching (-o), count (-c), max_count (-m). If the answer is long itself, it is saved as a "
                   "new result: search that one again, narrower.",
    "parameters": {"type": "object",
                   "properties": {
                       "name": {"type": "string", "description": "the result, e.g. results-3"},
                       "pattern": {"type": "string", "description": "what to look for. plain text, or a regular "
                                                                    "expression (python's syntax) if regex is true"},
                       "regex": {"type": "boolean", "description": "pattern is a regular expression, e.g. "
                                                                   "error|warning or ^line \\d+. default false"},
                       "ignore_case": {"type": "boolean", "description": "upper/lower case doesn't matter. "
                                                                         "default false"},
                       "whole_word": {"type": "boolean", "description": "only whole words. default false"},
                       "invert": {"type": "boolean", "description": "show the lines that do NOT match. default false"},
                       "before": {"type": "integer", "description": "also show this many lines before each match. "
                                                                    "default 0"},
                       "after": {"type": "integer", "description": "also show this many lines after each match. "
                                                                   "default 0"},
                       "only_matching": {"type": "boolean", "description": "only the matched pieces, not whole "
                                                                           "lines. default false"},
                       "count": {"type": "boolean", "description": "only count the matching lines. default false"},
                       "max_count": {"type": "integer", "description": "stop after this many matching lines. "
                                                                       "default 0 = no limit"}},
                   "required": ["name", "pattern"]},
}
