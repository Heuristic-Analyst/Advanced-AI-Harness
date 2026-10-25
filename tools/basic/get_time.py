# tools/basic/get_time.py — the date and time right now. the model has no clock: without this tool it only knows
# the date its training ended, and guesses. it gets the time of the user's computer, or of any time zone it asks for.
# time zones by their IANA name (Europe/Berlin, America/New_York, UTC), read with python's zoneinfo.
# on windows, zoneinfo needs the tzdata package (pip install tzdata): without it, only the computer's own time works.

import re
import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ZONE = r"[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*"   # what a time zone name may look like: Europe/Berlin,
                                                     # America/Argentina/Salta, Etc/GMT+2. no .. and no / in front:
                                                     # zoneinfo reads it as a file name, so it can never point elsewhere


def run(agent, timezone=""):
    if not timezone:                                 # no time zone asked for: the user's computer's own
        now = datetime.datetime.now().astimezone()   # astimezone(): the local time, with its time zone attached
        where = "the time zone of the user's computer"
    else:
        if not re.fullmatch(ZONE, timezone) or len(timezone) > 60:   # CHECK: a name, not a path
            return "invalid time zone: give an IANA name like Europe/Berlin, America/New_York or UTC"
        try:
            now = datetime.datetime.now(ZoneInfo(timezone))
        except (ZoneInfoNotFoundError, ValueError):  # no such zone, or no time zone data on this computer
            return ("unknown time zone '" + timezone + "': give an IANA name like Europe/Berlin or UTC. "
                    "or leave it out for the user's own time")
        where = timezone

    offset = now.utcoffset()                         # e.g. 2:00:00. its distance from UTC
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    utc = "UTC" + sign + format(abs(minutes) // 60, "02") + ":" + format(abs(minutes) % 60, "02")   # UTC+02:00
    return (now.strftime("%A, %Y-%m-%d %H:%M:%S")    # Saturday, 2026-10-24 13:20:05
            + "." + format(now.microsecond // 1000, "03")   # .042: milliseconds. microseconds // 1000, always 3 digits
            + " " + utc + " (" + (now.tzname() or "") + ", " + where + ")")   # UTC+02:00 (CEST, ...)


TOOL = {
    "name": "get_time",
    "description": "Get the current date, time and weekday. You have no clock of your own: use this whenever an "
                   "answer depends on today's date or the time, e.g. 'what day is it', 'how long until Friday', "
                   "'how old is someone born in 1990', or anything 'today', 'tomorrow' or 'this week'.",
    "parameters": {"type": "object",
                   "properties": {"timezone": {"type": "string",
                                               "description": "optional: an IANA time zone like Europe/Berlin, "
                                                              "America/New_York or UTC. left out: the user's own "
                                                              "time"}}},
}
