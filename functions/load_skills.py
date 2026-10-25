import os
from functions.read_front_matter import read_front_matter


def load_skills(folder):
    """find every skill: a folder in `folder` with a SKILL.md inside (skills/<name>/SKILL.md). returns a dict:
        skill name -> {"description": the one line for the menu, "path": its SKILL.md}
    only the header is kept: the instructions themselves are read when the model loads the skill (load_skill)"""
    skills = {}
    if not os.path.isdir(folder):                            # no skills folder at all: no skills, no crash
        return skills
    for entry in sorted(os.listdir(folder)):                 # one subfolder per skill
        path = os.path.join(folder, entry, "SKILL.md")
        if not os.path.isfile(path):                         # a file (a README), or a folder without SKILL.md
            continue
        header, body = read_front_matter(path)
        name = header.get("name") or entry                   # no name in the header: the folder's name
        if name in skills:                                   # two skills with one name: the model couldn't tell them apart
            raise SystemExit("two skills are called '" + name + "': " + skills[name]["path"] + " and " + path
                             + ". rename one")
        if not header.get("description"):                    # without one, the model never knows when to use it
            raise SystemExit(path + " has no description in its header: one line saying when to use the skill, "
                             "e.g. 'description: Use when the user asks ...'")
        skills[name] = {"description": header["description"], "path": path}
    return skills
