#!/usr/bin/env python3
"""gui.py - a window in front of the harness. nothing in the harness itself is changed.

run it from this folder:
    python gui.py

it does exactly what main.py does when it starts (soul, tools, skills, locks, the sandbox, a first
conversation), and then carries your messages to agent.ask() and paints what comes back.

the harness only ever talks to a terminal, with print(). so this file gives classes/agent.py,
classes/sandbox.py and functions/commands.py a print() of its own, which puts the text into a queue
instead of the terminal (sys.stdout and sys.stderr are caught too, so nothing gets lost). the window
empties that queue and draws it:

    * your message, in a block
    * the answer, as markdown, while it streams in
    * the thinking, and every tool call, as ONE line - click the line to open it
    * a note for everything else the program says (retries, checkpoints, errors)

the /commands are done here, in the window; main.py's chat loop is not used at all:
    /new   /open [name]   /list   /rename [old] <new>   /delete [name]   /sandbox ...   /help   /exit

the conversations on the left: click one to continue it. the pin (top left) keeps the list open;
unpinned, it slides in when the mouse touches the left edge.

a conversation you open is drawn from its log.jsonl, not from state.json: the log is only ever added to, so
you see everything that was ever said, also across a checkpoint (where the model's own context is emptied
and replaced by its notes - those show up as a folded "checkpoint" line).
"""

import io
import json
import os
import re
import sys
import time
import queue
import itertools
import threading
import traceback
import webbrowser

try:
    import tkinter as tk
    from tkinter import ttk, font as tkfont, messagebox, simpledialog
except ImportError:
    raise SystemExit("this window needs tkinter, which this python does not have.\n"
                     "  windows/mac: install python from python.org (it brings tkinter along), then try again\n"
                     "  debian/ubuntu: sudo apt install python3-tk\n"
                     "main.py still works in a terminal without it")


# ----------------------------------------------------------------------------- look

BG      = "#FAF9F5"     # the page
PANEL   = "#F1EFE8"     # the conversation list
PANEL_2 = "#E4E0D6"
CARD    = "#FFFFFF"     # the input box
TOOLBG  = "#F4F1EA"
TEXT    = "#2C2A26"
MUTED   = "#8B857B"
FAINT   = "#C2BCB0"
ACCENT  = "#C2623C"
ACCENT_D= "#A14E2E"
CODE_BG = "#F3F0E8"
USER_BG = "#EDE7DB"
SELECT  = "#C9D8EC"     # a selection has to be visible over every other colour in the transcript
LINK    = "#2F6DB5"
OK      = "#5F8C5C"
WARN    = "#C9922E"
BAD     = "#C0503C"
LINE    = "#E6E1D7"

SIDE_W  = 236           # how wide the conversation list is
HISTORY_SHOWN = 120     # how many of the newest messages are drawn when a conversation is opened.
                        # the rest is one click away (the line at the top), so a long conversation opens fast


def short_num(n):
    """1204 -> 1.2k, 999 -> 999"""
    n = int(n)
    if n < 1000:
        return str(n)
    if n < 1000000:
        return ("%.1fk" % (n / 1000.0)).replace(".0k", "k")
    return ("%.1fM" % (n / 1000000.0)).replace(".0M", "M")


def human(n):
    return format(int(n), ",")


# ----------------------------------------------------------------------------- markdown

INLINE_RE = re.compile(
    r"`([^`\n]+)`"                          # 1 code
    r"|\*\*([^*\n]+)\*\*"                   # 2 bold
    r"|__([^_\n]+)__"                       # 3 bold
    r"|\*([^*\n]+)\*"                       # 4 italic
    r"|_([^_\n]+)_"                         # 5 italic
    r"|~~([^~\n]+)~~"                       # 6 strike
    r"|\[([^\]\n]+)\]\(([^)\n]+)\)"         # 7 + 8 link
)

_link_ids = itertools.count(1)


class _Writer:
    """puts text into the Text widget. pieces that carry the same tags are glued into one insert before they
    are written, so a whole code block (or a whole plain paragraph) is ONE insert and not one per line.
    that is most of the difference between a long conversation that takes a moment and one that takes a minute."""

    def __init__(self, t):
        self.t = t
        self.pending = ""
        self.tags = None

    def put(self, text, tags):
        if not text:
            return
        tags = tuple(tags)
        if tags == self.tags:
            self.pending += text
        else:
            self.flush()
            self.pending = text
            self.tags = tags

    def flush(self):
        if self.pending:
            self.t.insert("end-1c", self.pending, self.tags)
            self.pending = ""
            self.tags = None


def insert_inline(w, text, tags):
    """one line of markdown text: `code`, **bold**, *italic*, ~~strike~~, [text](url)"""
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            w.put(text[pos:m.start()], tags)
        code, bold1, bold2, ital1, ital2, strike, ltext, url = m.groups()
        if code is not None:
            w.put(code, ("code",) + tuple(tags))
        elif bold1 is not None or bold2 is not None:
            w.put(bold1 if bold1 is not None else bold2, ("bold",) + tuple(tags))
        elif ital1 is not None or ital2 is not None:
            w.put(ital1 if ital1 is not None else ital2, ("italic",) + tuple(tags))
        elif strike is not None:
            w.put(strike, ("strike",) + tuple(tags))
        else:
            tag = "linktag_%d" % next(_link_ids)      # one tag per link: a click knows its own url
            w.t.tag_configure(tag, foreground=LINK, underline=True)
            w.t.tag_raise("sel")
            try:
                w.t.tag_bind(tag, "<Button-1>", lambda e, u=url: webbrowser.open(u))
            except tk.TclError:
                pass
            w.put(ltext, (tag,) + tuple(tags))
        pos = m.end()
    if pos < len(text):
        w.put(text[pos:], tags)


def _code_block(w, lines, lang, base):
    if lang:
        w.put(" " + lang + "\n", ("codelang",) + tuple(base))
    w.put("\n".join(lines) + "\n", ("codeblock",) + tuple(base))     # one insert for the whole block
    w.put("\n", base)


def _table(w, rows, base):
    """a | a | b | table, drawn in a monospace font, columns lined up"""
    cells = []
    for row in rows:
        row = row.strip()
        if row.startswith("|"):
            row = row[1:]
        if row.endswith("|"):
            row = row[:-1]
        cells.append([c.strip() for c in row.split("|")])
    width = max(len(r) for r in cells)
    widths = [0] * width
    for r in cells:
        for j, c in enumerate(r):
            widths[j] = max(widths[j], len(re.sub(r"[`*_]", "", c)))
    out = []
    for r in cells:
        parts = []
        for j in range(width):
            c = r[j] if j < len(r) else ""
            parts.append(c + " " * max(0, widths[j] - len(re.sub(r"[`*_]", "", c))))
        out.append("  " + " │ ".join(parts).rstrip())
    w.put("\n".join(out) + "\n", ("codeblock",) + tuple(base))
    w.put("\n", base)


def render_markdown(t, md, extra=()):
    """draw markdown into the Text widget t, at its end"""
    w = _Writer(t)
    base = ("body",) + tuple(extra)
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):                      # a code block, closed or (while streaming) not
            lang = stripped[3:].strip()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            _code_block(w, code, lang, base)
            continue

        if "|" in line and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            rows = [line]
            i += 2                                          # the ---|--- line is not shown
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(lines[i])
                i += 1
            _table(w, rows, base)
            continue

        if not stripped:                                    # an empty line
            w.put("\n", base)
            i += 1
            continue

        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):    # a horizontal rule
            w.put("─" * 58 + "\n", ("hr",) + tuple(extra))
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)        # a heading
        if m:
            level = min(len(m.group(1)), 3)
            tag = ("h%d" % level,) + tuple(extra)
            w.put("\n", base)
            insert_inline(w, m.group(2), tag)
            w.put("\n", tag)
            i += 1
            continue

        m = re.match(r"^(\s*)([-*+])\s+(.*)$", line)         # a bullet
        if m:
            tag = ("bullet",) + tuple(extra)
            w.put("   " * (len(m.group(1)) // 2) + "•  ", tag)
            insert_inline(w, m.group(3), tag)
            w.put("\n", tag)
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)[.)]\s+(.*)$", line)       # a numbered item
        if m:
            tag = ("bullet",) + tuple(extra)
            w.put("   " * (len(m.group(1)) // 2) + m.group(2) + ".  ", tag)
            insert_inline(w, m.group(3), tag)
            w.put("\n", tag)
            i += 1
            continue

        if stripped.startswith(">"):                        # a quote
            tag = ("quote",) + tuple(extra)
            w.put("▏ ", tag)
            insert_inline(w, re.sub(r"^>\s?", "", stripped), tag)
            w.put("\n", tag)
            i += 1
            continue

        insert_inline(w, line, base)                        # just a line
        w.put("\n", base)
        i += 1
    w.flush()


# ----------------------------------------------------------------------------- the window

class Gui:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()           # the worker thread(s) put what happens in here, the window reads it

        # the harness, filled in by _boot()
        self.Agent = None
        self.sandbox = None
        self.workspace = None
        self.soul = ""
        self.tools = {}
        self.skills = {}
        self.conv_mod = None
        self.locks = None
        self.model = ""
        self.effort = None
        self.limit = 0
        self.config = None
        self.current = None
        self.agent = None

        # what the window is doing
        self.busy = False
        self.opening = False
        self.picking = False
        self.pinned = True
        self.side_x = -SIDE_W
        self.side_target = -SIDE_W
        self.side_anim = False
        self.hover_until = 0
        self.ready = False
        self.follow = True               # scroll along with new text? (no: the user scrolled up)
        self.rawbuf = ""

        # what is drawn
        self.history = []                # the messages of the open conversation, as read from its log
        self.draw = None                 # the drawing job in progress (a conversation can be long)
        self.drawing = False
        self.blocks = {}                 # n -> {kind, hdr, body, open, label}
        self.block_n = 0
        self.pending_tools = []          # tool blocks waiting for their result, in the order they were asked
        self.live = None                 # the answer or thinking block that is streaming in right now
        self.conv_names = []
        self.count_cache = {}            # conversation -> (mtime, size) of its state.json, and how many messages

        self._make_fonts()
        self._capture_output()
        self._build()
        self.root.report_callback_exception = self._tk_error
        self._poll()
        threading.Thread(target=self._boot, daemon=True).start()

    # --- fonts -----------------------------------------------------------------
    def _make_fonts(self):
        families = set(tkfont.families(self.root))

        def pick(names, size, weight="normal", slant="roman"):
            for name in names:
                if name in families:
                    return tkfont.Font(self.root, family=name, size=size, weight=weight, slant=slant)
            return tkfont.Font(self.root, size=size, weight=weight, slant=slant)

        sans = ["Inter", "Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue",
                "Helvetica", "DejaVu Sans", "Arial"]
        mono = ["JetBrains Mono", "Cascadia Mono", "SF Mono", "Menlo", "Consolas",
                "DejaVu Sans Mono", "Courier New"]
        self.F = {
            "body":         pick(sans, 11),
            "bold":         pick(sans, 11, "bold"),
            "italic":       pick(sans, 11, "normal", "italic"),
            "small":        pick(sans, 9),
            "small_italic": pick(sans, 9, "normal", "italic"),
            "small_bold":   pick(sans, 9, "bold"),
            "tiny":         pick(sans, 8),
            "h1":           pick(sans, 17, "bold"),
            "h2":           pick(sans, 14, "bold"),
            "h3":           pick(sans, 12, "bold"),
            "mono":         pick(mono, 10),
            "mono_s":       pick(mono, 9),
            "ui":           pick(sans, 10),
            "ui_bold":      pick(sans, 10, "bold"),
            "title":        pick(sans, 12, "bold"),
        }

    # --- catching what the harness prints ---------------------------------------
    def _capture_output(self):
        """print() from the harness goes into the queue, and so does anything written to stdout/stderr.
        (the real stdout is kept: a crash of the window itself still shows in the terminal)"""
        self.real_out, self.real_err = sys.stdout, sys.stderr
        sys.stdout = _Stream(self.q, "out")
        sys.stderr = _Stream(self.q, "err")

    def hooked_print(self, *args, sep=" ", end="\n", file=None, flush=False):
        """what print() becomes inside the harness modules: the same call, but into the queue"""
        if sep is None:
            sep = " "
        self.q.put(("print", sep.join(str(a) for a in args), end))

    def _hook_modules(self):
        """every module of the harness that prints gets its own print(), which comes here"""
        for name in ("classes.agent", "classes.sandbox", "functions.commands", "functions.conversations"):
            module = sys.modules.get(name)
            if module is not None:
                module.print = self.hooked_print

    def _tk_error(self, kind, value, tb):
        """a crash inside a click must show: in the terminal, and in the window"""
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            print(text, file=self.real_err)
        except BaseException:
            pass
        try:
            self._end_block()
            self._error_block("the window hit a problem:\n" + text)
        except BaseException:
            pass

    # --- the look --------------------------------------------------------------
    def _build(self):
        r = self.root
        r.title("Harness")
        r.geometry("1220x820")
        r.minsize(860, 540)
        r.configure(bg=BG)
        r.protocol("WM_DELETE_WINDOW", self._quit)

        style = ttk.Style(r)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Vertical.TScrollbar", background=PANEL_2, troughcolor=BG, bordercolor=BG,
                        arrowcolor=MUTED, relief="flat", width=10, arrowsize=10)

        self._top_bar()
        self._footer()
        self._body_parts()

    def _top_bar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(side="top", fill="x")
        tk.Frame(self.root, bg=LINE, height=1).pack(side="top", fill="x")

        self.pin_btn = tk.Button(bar, text="☰", command=self._toggle_pin, bg=BG, fg=ACCENT, relief="flat",
                                 bd=0, highlightthickness=0, activebackground=PANEL_2, cursor="hand2",
                                 padx=8, pady=2, font=self.F["title"])
        self.pin_btn.pack(side="left", padx=(10, 4), pady=7)

        tk.Label(bar, text="Harness", bg=BG, fg=TEXT, font=self.F["title"]).pack(side="left")
        self.conv_lbl = tk.Label(bar, text="", bg=BG, fg=MUTED, font=self.F["ui"])
        self.conv_lbl.pack(side="left", padx=(10, 0))

        self.busy_lbl = tk.Label(bar, text="", bg=BG, fg=ACCENT, font=self.F["ui"])
        self.busy_lbl.pack(side="right", padx=(0, 14))

        self.tok_lbl = tk.Label(bar, text="", bg=BG, fg=MUTED, font=self.F["ui"])
        self.tok_lbl.pack(side="right", padx=(8, 0))
        self.tok_bar = tk.Canvas(bar, width=110, height=6, bg=BG, highlightthickness=0)
        self.tok_bar.pack(side="right", padx=(10, 0))

        self.model_lbl = tk.Label(bar, text="", bg=BG, fg=MUTED, font=self.F["ui"])
        self.model_lbl.pack(side="right", padx=(20, 0))

    def _footer(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(side="bottom", fill="x")
        tk.Frame(wrap, bg=LINE, height=1).pack(side="top", fill="x")
        self.status_lbl = tk.Label(wrap, text="", bg=BG, fg=FAINT, font=self.F["tiny"], anchor="w")
        self.status_lbl.pack(side="left", fill="x", padx=14, pady=4)

    def _body_parts(self):
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(side="top", fill="both", expand=True)

        # the chat: transcript above, input below. placed (not packed) so the sidebar can slide over it
        self.chat = tk.Frame(self.body, bg=BG)
        self.chat.place(x=0, y=0, relwidth=1, relheight=1)

        self._input_area()
        self._transcript()
        self._sidebar()

    def _transcript(self):
        wrap = tk.Frame(self.chat, bg=BG)
        wrap.pack(side="top", fill="both", expand=True)

        self.txt = tk.Text(wrap, bg=BG, fg=TEXT, font=self.F["body"], relief="flat", wrap="word",
                           padx=30, pady=16, insertwidth=0, borderwidth=0, highlightthickness=0,
                           selectbackground=SELECT, selectforeground=TEXT, spacing1=0, spacing3=2,
                           cursor="arrow")
        self.txt.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.txt.yview)
        scroll.pack(side="right", fill="y")
        scroll.bind("<ButtonRelease-1>", self._scrolled)
        self.txt.configure(yscrollcommand=scroll.set)

        self._style_tags()

        # read only, but selectable: typing does nothing, everything else (select, copy, the fold lines) works
        self.txt.bind("<Key>", self._readonly)
        self.txt.bind("<Button-1>", lambda e: self.txt.focus_set(), add="+")
        self.txt.bind("<<Paste>>", lambda e: "break")
        self.txt.bind("<<Cut>>", lambda e: "break")
        self.txt.bind("<<Copy>>", self._copy_selection)
        self.txt.bind("<<SelectAll>>", self._select_all)
        self.txt.bind("<Control-c>", self._copy_selection)
        self.txt.bind("<Control-a>", self._select_all)
        try:                                   # cmd+c / cmd+a on a mac (the modifier is not on every system)
            self.txt.bind("<Command-c>", self._copy_selection)
            self.txt.bind("<Command-a>", self._select_all)
        except tk.TclError:
            pass
        for seq in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.txt.bind(seq, self._text_menu)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.txt.bind(seq, self._scrolled, add="+")

    def _style_tags(self):
        t = self.txt
        f = self.F
        t.tag_configure("body", font=f["body"], foreground=TEXT, spacing1=1, spacing3=3)
        t.tag_configure("bold", font=f["bold"])
        t.tag_configure("italic", font=f["italic"])
        t.tag_configure("strike", overstrike=True)
        t.tag_configure("code", font=f["mono_s"], background=CODE_BG, foreground="#8A4B2A")
        t.tag_configure("codeblock", font=f["mono"], background=CODE_BG, foreground="#3A3833",
                        lmargin1=20, lmargin2=20, spacing1=1, spacing3=1)
        t.tag_configure("codelang", font=f["tiny"], foreground=MUTED, lmargin1=20, lmargin2=20, spacing1=4)
        t.tag_configure("h1", font=f["h1"], foreground=TEXT, spacing1=14, spacing3=6)
        t.tag_configure("h2", font=f["h2"], foreground=TEXT, spacing1=12, spacing3=4)
        t.tag_configure("h3", font=f["h3"], foreground=TEXT, spacing1=10, spacing3=3)
        t.tag_configure("bullet", lmargin1=22, lmargin2=40)
        t.tag_configure("quote", font=f["italic"], foreground=MUTED, lmargin1=22, lmargin2=22)
        t.tag_configure("hr", foreground=FAINT)
        t.tag_configure("user", font=f["body"], background=USER_BG, lmargin1=14, lmargin2=14, spacing1=2,
                        spacing3=4)
        t.tag_configure("you", font=f["small_bold"], foreground=ACCENT, spacing1=12, spacing3=1)
        t.tag_configure("note", font=f["small"], foreground=MUTED, spacing1=3, spacing3=3, lmargin1=2)
        t.tag_configure("error", font=f["small"], foreground=BAD, spacing1=3, spacing3=3, lmargin1=2)
        t.tag_configure("rule", font=f["tiny"], foreground=FAINT, spacing1=10, spacing3=10)
        # tk draws the selection with the tag "sel", and a tag created LATER wins. everything drawn here
        # (code blocks, quotes, bubbles) is created later, so without this the highlight would be invisible
        # over exactly the parts you most want to copy.
        t.tag_raise("sel")

    def _input_area(self):
        outer = tk.Frame(self.chat, bg=BG)
        outer.pack(side="bottom", fill="x", padx=30, pady=(0, 12))

        card = tk.Frame(outer, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(side="top", fill="x")

        self.entry = tk.Text(card, height=3, bg=CARD, fg=TEXT, font=self.F["body"], relief="flat",
                             wrap="word", padx=12, pady=10, insertbackground=ACCENT,
                             insertwidth=2, borderwidth=0, highlightthickness=0,
                             spacing1=0, spacing3=0)
        self.entry.pack(side="left", fill="both", expand=True)

        right = tk.Frame(card, bg=CARD)
        right.pack(side="right", fill="y", padx=8, pady=8)
        self.send_btn = tk.Button(right, text="Send", command=self._send, bg=ACCENT, fg="white",
                                  activebackground=ACCENT_D, activeforeground="white", relief="flat",
                                  bd=0, highlightthickness=0, cursor="hand2", padx=16, pady=6,
                                  font=self.F["ui_bold"], state="disabled")
        self.send_btn.pack(side="bottom")

        self.hint = tk.Label(outer, text="Enter sends  ·  Shift+Enter makes a new line  ·  /help shows the commands",
                             bg=BG, fg=FAINT, font=self.F["tiny"], anchor="w")
        self.hint.pack(side="top", fill="x", pady=(5, 0))

        try:                                  # ctrl+a / cmd+a in the box: select the whole message
            self.entry.bind("<Control-a>", self._entry_select_all)
            self.entry.bind("<Command-a>", self._entry_select_all)
        except tk.TclError:
            pass
        self.entry.bind("<Control-A>", self._entry_select_all)
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Shift-Return>", self._on_shift_return)
        self.entry.bind("<Escape>", lambda e: "break")

    def _sidebar(self):
        self.side = tk.Frame(self.body, bg=PANEL)
        self.side.place(x=-SIDE_W, y=0, width=SIDE_W, relheight=1)

        head = tk.Frame(self.side, bg=PANEL)
        head.pack(side="top", fill="x", padx=12, pady=(12, 4))
        tk.Label(head, text="Conversations", bg=PANEL, fg=TEXT, font=self.F["ui_bold"]).pack(side="left")
        tk.Button(head, text="+", command=self._new, bg=PANEL, fg=MUTED, relief="flat", bd=0,
                  highlightthickness=0, activebackground=PANEL_2, cursor="hand2",
                  font=self.F["title"]).pack(side="right")
        tk.Button(head, text="☰", command=self._toggle_pin, bg=PANEL, fg=MUTED, relief="flat", bd=0,
                  highlightthickness=0, activebackground=PANEL_2, cursor="hand2",
                  font=self.F["ui"]).pack(side="right", padx=(0, 4))

        actions = tk.Frame(self.side, bg=PANEL)           # packed before the list, so it keeps its room
        actions.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        for text, job in (("Rename", self._rename_selected), ("Delete", self._delete_selected)):
            tk.Button(actions, text=text, command=job, bg=PANEL, fg=MUTED, relief="flat", bd=0,
                      highlightthickness=0, activebackground=PANEL_2, activeforeground=TEXT,
                      cursor="hand2", padx=8, pady=3,
                      font=self.F["small"]).pack(side="left", padx=(0, 4))

        listwrap = tk.Frame(self.side, bg=PANEL)
        listwrap.pack(side="top", fill="both", expand=True, padx=(8, 2), pady=(2, 10))

        self.lb = tk.Listbox(listwrap, bg=PANEL, fg=TEXT, font=self.F["small"], relief="flat",
                             highlightthickness=0, borderwidth=0, activestyle="none",
                             selectbackground=SELECT, selectforeground=TEXT, exportselection=False,
                             cursor="hand2")
        self.lb.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(listwrap, orient="vertical", command=self.lb.yview)
        scroll.pack(side="right", fill="y")
        self.lb.configure(yscrollcommand=scroll.set)
        self.lb.bind("<<ListboxSelect>>", self._on_pick)
        for seq in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.lb.bind(seq, self._list_menu)
        self.lb.bind("<Delete>", lambda e: self._delete_selected())
        self.lb.bind("<F2>", lambda e: self._rename_selected())

        tk.Frame(self.side, bg=LINE, width=1).place(x=SIDE_W - 1, y=0, relheight=1)

        # the strip that feels the mouse at the left edge when the list is out
        self.strip = tk.Frame(self.body, bg=PANEL_2, width=6, cursor="hand2")
        self.strip.place(x=0, y=0, width=6, relheight=1)
        self.strip.lower(self.side)

        self.side_x = 0                      # we start pinned: the list is out
        self.side_target = 0
        self.side.place_configure(x=0)
        self._layout_chat()

    # --- the sidebar: pinned, or in and out with the mouse ---------------------
    def _layout_chat(self):
        x = SIDE_W if self.pinned else 0
        self.chat.place_configure(x=x, relwidth=1, width=-x)

    def _toggle_pin(self):
        self.pinned = not self.pinned
        self.pin_btn.configure(fg=ACCENT if self.pinned else MUTED)
        self._layout_chat()
        if self.pinned:
            self.side_target = 0
            self._slide_step()
        else:
            self.hover_until = 0        # let the poll decide: it slides out once the mouse is away

    def _slide_step(self):
        """move the sidebar a step towards where it should be"""
        if self.side_x == self.side_target:
            self.side_anim = False
            return
        self.side_anim = True
        step = 28 if self.side_target > self.side_x else -28
        nxt = self.side_x + step
        if (step > 0 and nxt > self.side_target) or (step < 0 and nxt < self.side_target):
            nxt = self.side_target
        self.side_x = nxt
        try:
            self.side.place_configure(x=nxt)
        except tk.TclError:
            return
        self.root.after(10, self._slide_step)

    def _in(self, widget, x, y):
        try:
            if not widget.winfo_ismapped():
                return False
            wx, wy = widget.winfo_rootx(), widget.winfo_rooty()
            return wx <= x < wx + widget.winfo_width() and wy <= y < wy + widget.winfo_height()
        except tk.TclError:
            return False

    def _poll(self):
        """runs all the time: the queue, and the mouse at the left edge"""
        self._drain()
        if self.ready and not self.pinned:
            x, y = self.root.winfo_pointerxy()
            if self._in(self.side, x, y) or self._in(self.strip, x, y):
                self.hover_until = time.time() + 0.4
            if self.hover_until > time.time():
                self.side_target = 0
            else:
                self.side_target = -SIDE_W
            if self.side_x != self.side_target and not self.side_anim:
                self._slide_step()
        self.root.after(60, self._poll)

    # --- starting the harness --------------------------------------------------
    def _boot(self):
        """the whole start of main.py, in a thread (podman can take a while), then "ready" into the queue"""
        self.q.put(("note", "starting the harness…"))
        try:
            import config
            from config import (SOUL_FILE, TOOLS_DIR, SKILLS_DIR, SANDBOXES_DIR, SHARED_DIR, COMMON, ENGINE,
                                INSTANCE, CONTAINER_CMD, SANDBOX_MEMORY, SANDBOX_CPUS, SANDBOX_PIDS,
                                COMMAND_TIMEOUT, MODEL, EFFORT, CONTEXT_LIMIT, READONLY_PROJECTS)
            from classes.agent import Agent
            from classes.sandbox import Sandbox
            from functions.read_text import read_text
            from functions.load_tools import load_tools
            from functions.load_skills import load_skills
            from functions import conversations, locks
        except BaseException:
            self.q.put(("fatal", "could not start the harness:\n\n" + traceback.format_exc()))
            return

        self._hook_modules()

        try:
            soul = read_text(SOUL_FILE) or "You are a helpful assistant."
            tools = load_tools(TOOLS_DIR)
            skills = load_skills(SKILLS_DIR)

            locks.start()
            sandbox = Sandbox(SANDBOXES_DIR, SHARED_DIR, COMMON, ENGINE, INSTANCE, command=CONTAINER_CMD,
                              memory=SANDBOX_MEMORY, cpus=SANDBOX_CPUS, pids=SANDBOX_PIDS,
                              timeout=COMMAND_TIMEOUT, readonly=READONLY_PROJECTS)
            import atexit
            atexit.register(locks.stop)
            atexit.register(sandbox.shutdown)

            workspace = None
            if sandbox.available():
                workspace = sandbox
                sandbox.cleanup()
            else:
                for name in [n for n, tool in tools.items()
                             if tool["folder"].split("/")[0] in ("sandbox", "notebook")]:
                    tools.pop(name)
                skills.pop("sandbox", None)
                skills.pop("notebook", None)
                skills.pop("browser", None)
            if not skills:
                tools.pop("load_skill", None)

            self.config = config
            self.Agent = Agent
            self.sandbox = sandbox
            self.workspace = workspace
            self.soul = soul
            self.tools = tools
            self.skills = skills
            self.conv_mod = conversations
            self.locks = locks
            self.model = MODEL
            self.effort = EFFORT
            self.limit = CONTEXT_LIMIT
            self.current = conversations.new_name()
            self.agent = self._new_agent(self.current)
        except BaseException:
            self.q.put(("fatal", "could not start the harness:\n\n" + traceback.format_exc()))
            return

        self.q.put(("ready", None))

    def _new_agent(self, name, messages=None):
        """an agent for one conversation, exactly as main.py makes one - but streaming and with the thinking
        printed, because the window shows both while they arrive"""
        conv = self.conv_mod
        return self.Agent(self.model, self.config.API_KEY, instructions=self.soul,
                          stream=True, effort=self.effort, print_thinking=True,
                          tools=self.tools, skills=self.skills, conversation=messages,
                          log_file=conv.log_of(name), results_dir=conv.results_of(name),
                          checkpoint_file=conv.checkpoint_of(name), context_limit=self.limit,
                          sandbox=self.workspace)

    def _on_ready(self):
        self.ready = True
        self.model_lbl.configure(text=self.model)
        sandbox_note = ("sandbox: " + (", ".join(self.sandbox.names()) or "none")) if self.workspace \
            else "no podman: no sandbox"
        self.q.put(("note", "ready  ·  model " + self.model + "  ·  tools " + str(len(self.tools))
                    + "  ·  skills " + str(len(self.skills)) + "  ·  " + sandbox_note))
        if not self.workspace:
            self.q.put(("note", "podman is not installed or not running, so the agent cannot run code. "
                                "(mac/windows: podman machine start, then start this again)"))
        self._set_input(True)
        self._update_tokens()
        self._refresh_sidebar()
        self._update_status()
        self.entry.focus_set()

    # --- conversations ---------------------------------------------------------
    def _pretty(self, name):
        """a folder name -> a line for the list"""
        shown = name
        m = re.match(r"^(\d{4})(\d{2})(\d{2})-(\d{2})-(\d{2})-(\d{2})", name)
        if m:
            shown = "%s-%s-%s  %s:%s" % (m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
        try:
            path = self.conv_mod.state_of(name)
            stat = os.stat(path)
            key = (stat.st_mtime, stat.st_size)
            cached = self.count_cache.get(name)
            if cached and cached[0] == key:
                count = cached[1]
            else:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    count = f.read().count('"role"')      # one per message, no json needed
                self.count_cache[name] = (key, count)
            if count:
                shown += "   · " + str(count)
        except BaseException:
            pass
        return shown

    def _refresh_sidebar(self):
        if not self.conv_mod:
            return
        try:
            names = self.conv_mod.names()
        except BaseException:
            names = []
        if self.current and self.current not in names:
            names = names + [self.current]
        self.conv_names = names
        self.lb.delete(0, "end")
        for name in names:
            self.lb.insert("end", "  " + self._pretty(name))
        if self.current in names:
            i = names.index(self.current)
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.lb.see(i)
        self.conv_lbl.configure(text=self.current or "")
        self.root.title("Harness  ·  " + (self.current or ""))

    def _end_picking(self):
        self.picking = False

    def _on_pick(self, event=None):
        if self.picking:
            return
        sel = self.lb.curselection()
        if not sel:
            return
        i = int(sel[0])
        if 0 <= i < len(self.conv_names):
            name = self.conv_names[i]
            if name != self.current:
                self._open(name)

    def _list_menu(self, event):
        """right click in the list: open / rename / delete"""
        i = self.lb.nearest(event.y)
        if 0 <= i < len(self.conv_names):
            self.picking = True
            self.lb.selection_clear(0, "end")
            self.lb.selection_set(i)
            self.root.after(120, self._end_picking)
            name = self.conv_names[i]
            menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT, activebackground=SELECT,
                           activeforeground=TEXT, relief="flat", bd=1)
            menu.add_command(label="Open", command=lambda: self._open(name))
            menu.add_command(label="Rename…", command=lambda: self._rename(name))
            menu.add_separator()
            menu.add_command(label="Delete…", command=lambda: self._delete(name))
            self.hover_until = time.time() + 30
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
                self.hover_until = time.time() + 0.3
        return "break"

    def _open(self, name):
        if not self.ready:
            return
        if self.busy or self.opening or self.drawing:
            self.q.put(("note", "one moment: the agent is still working in " + str(self.current)))
            return
        if name == self.current:
            return
        self.opening = True
        self.q.put(("note", "opening " + name + " …"))

        def work():
            try:
                data = self.conv_mod.load(name)          # what the model carries right now (and its size)
                messages = data.get("messages") or []
                agent = self._new_agent(name, messages)
                agent.tokens = data.get("tokens", 0)
                history = self._read_log(name)           # everything ever said, which is more than that
                if history is None:
                    history = messages
                self.q.put(("opened", (name, agent, history)))
            except BaseException:
                self.q.put(("error", "could not open " + name + ":\n" + traceback.format_exc()))
                self.q.put(("opened_none", None))

        threading.Thread(target=work, daemon=True).start()

    def _on_opened(self, payload):
        name, agent, history = payload
        self.current, self.agent = name, agent
        self.opening = False
        self.history = history
        self._update_tokens()
        self._refresh_sidebar()
        self._draw_history(max(0, len(history) - HISTORY_SHOWN))
        self._set_input(True)

    def _new(self):
        if not self.ready:
            return
        if self.busy or self.opening or self.drawing:
            self.q.put(("note", "one moment: the agent is still working in " + str(self.current)))
            return
        try:
            self.current = self.conv_mod.new_name()
            self.agent = self._new_agent(self.current)
        except BaseException:
            self.q.put(("error", "could not start a new conversation:\n" + traceback.format_exc()))
            return
        self.history = []
        self._clear_chat()
        self._rule("new conversation")
        self._update_tokens()
        self._refresh_sidebar()
        self.entry.focus_set()

    def _selected_name(self):
        """the conversation highlighted in the list (the open one, if nothing is highlighted)"""
        sel = self.lb.curselection()
        if sel and int(sel[0]) < len(self.conv_names):
            return self.conv_names[int(sel[0])]
        return self.current

    def _rename_selected(self):
        name = self._selected_name()
        if name:
            self._rename(name)

    def _delete_selected(self):
        name = self._selected_name()
        if name:
            self._delete(name)

    def _rename(self, name):
        if self.busy:
            return
        self.hover_until = time.time() + 60
        new = simpledialog.askstring("rename", "new name for '" + name + "':", parent=self.root)
        self.hover_until = time.time() + 0.3
        if not new:
            return
        new = new.strip()
        problem = self.conv_mod.rename(name, new)
        if problem:
            self.q.put(("error", problem))
            return
        if name == self.current:                     # renamed the one we are in: its files live there now
            self.current = new
            self.agent.log_file = self.conv_mod.log_of(new)
            self.agent.results_dir = self.conv_mod.results_of(new)
            self.agent.checkpoint_file = self.conv_mod.checkpoint_of(new)
        self.q.put(("note", "renamed " + name + " -> " + new))
        self._refresh_sidebar()

    def _delete(self, name):
        if self.busy:
            return
        self.hover_until = time.time() + 60
        yes = messagebox.askyesno("delete", "Delete '" + name + "' with everything in it?\n"
                                            "There is no undo.", parent=self.root)
        self.hover_until = time.time() + 0.3
        if not yes:
            return
        problem = self.conv_mod.delete(name)
        if problem:
            self.q.put(("error", problem))
            return
        self.q.put(("note", "deleted " + name))
        if name == self.current:
            self._new()
        else:
            self._refresh_sidebar()

    def _show_list(self):
        names = self.conv_mod.names() if self.conv_mod else []
        lines = ["saved conversations:"]
        for name in names:
            lines.append(("  * " if name == self.current else "    ") + self._pretty(name))
        if not names:
            lines.append("  none yet")
        self.q.put(("note", "\n".join(lines)))
        if not self.pinned:                      # /list means "show me": bring the list in for a moment
            self.hover_until = time.time() + 2.5

    # --- typing -----------------------------------------------------------------
    def _readonly(self, event):
        mods = event.state & (0x4 | 0x8 | 0x10 | 0x80)
        if mods and event.keysym.lower() in ("c", "a", "insert"):
            return None
        if event.keysym in ("Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next", "Tab"):
            return None
        return "break"

    def _has_selection(self):
        try:
            return bool(self.txt.tag_ranges("sel"))
        except tk.TclError:
            return False

    def _drop_cursor(self):
        r = self.txt.tag_ranges("cursor")
        if r:
            self.txt.delete(r[0], r[-1])

    def _copy_selection(self, event=None):
        try:
            text = self.txt.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"                  # nothing selected: nothing to copy
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._flash("copied " + short_num(len(text)) + " characters")
        return "break"

    def _copy_all(self):
        text = self.txt.get("1.0", "end-1c")
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._flash("copied the whole transcript (" + short_num(len(text)) + " characters)")

    def _flash(self, message):
        """a word in the status line for a moment, so a copy is not silent"""
        try:
            self.status_lbl.configure(text=message, fg=ACCENT)
        except tk.TclError:
            return

        def back():
            try:
                self.status_lbl.configure(fg=FAINT)
            except tk.TclError:
                return
            self._update_status()

        self.root.after(1600, back)

    def _select_all(self, event=None):
        self.txt.tag_add("sel", "1.0", "end-1c")
        self.txt.mark_set("insert", "1.0")
        return "break"

    def _text_menu(self, event):
        """right click in the transcript: copy what is selected, or everything"""
        menu = tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT, activebackground=SELECT,
                       activeforeground=TEXT, relief="flat", bd=1)
        menu.add_command(label="Copy", command=self._copy_selection)
        menu.add_command(label="Copy everything", command=self._copy_all)
        menu.add_separator()
        menu.add_command(label="Select all", command=self._select_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _scrolled(self, event=None):
        self.root.after(30, self._check_follow)

    def _check_follow(self):
        try:
            self.follow = self.txt.yview()[1] > 0.995
        except tk.TclError:
            self.follow = True

    def _follow_bottom(self):
        if self.follow:
            try:
                self.txt.see("end-1c")
            except tk.TclError:
                pass

    def _entry_select_all(self, event=None):
        self.entry.tag_add("sel", "1.0", "end-1c")
        self.entry.mark_set("insert", "1.0")
        self.entry.see("insert")
        return "break"

    def _on_shift_return(self, event):
        try:
            self.entry.insert("insert", "\n")
        except tk.TclError:
            pass
        return "break"

    def _on_return(self, event):
        if event.state & 0x1:            # shift held: a new line instead
            return self._on_shift_return(event)
        self._send()
        return "break"

    def _send(self):
        if not self.ready or self.busy or self.opening or self.drawing:
            return
        text = self.entry.get("1.0", "end-1c").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        if text.startswith("/"):
            self._command(text)
            return
        self._user_message(text)
        self.busy = True
        self._set_input(False)
        threading.Thread(target=self._work, args=(text, self.agent, self.current), daemon=True).start()

    def _work(self, text, agent, current):
        """the agent's turn, off the window's thread. everything it prints comes back through the queue"""
        try:
            notes = self.workspace.take_notes() if self.workspace else []
            if notes:
                text = "\n".join(notes) + "\n\n" + text
            agent.ask(text)
        except BaseException as e:
            message = type(e).__name__ + ": " + str(e)
            if len(message) > 900:
                message = message[:900] + " …"
            self.q.put(("error", message))
        finally:
            try:
                self.conv_mod.save(current, agent)
            except BaseException:
                self.q.put(("error", "could not save the conversation:\n" + traceback.format_exc()))
            self.q.put(("done", None))

    def _set_input(self, on):
        self.entry.configure(state="normal" if on else "disabled")
        self.send_btn.configure(state="normal" if on else "disabled",
                                bg=ACCENT if on else "#D9D0C3")
        self.busy_lbl.configure(text="" if on else "working…")
        if on:
            try:
                self.entry.focus_set()
            except tk.TclError:
                pass

    # --- what comes back --------------------------------------------------------
    def _drain(self):
        for _ in range(500):
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            try:
                if kind == "print":
                    self._on_print(item[1], item[2])
                elif kind == "raw":
                    self._on_raw(item[1])
                elif kind == "note":
                    self._note(item[1])
                elif kind == "error":
                    self._on_error(item[1])
                elif kind == "fatal":
                    self._on_fatal(item[1])
                elif kind == "ready":
                    self._on_ready()
                elif kind == "opened":
                    self._on_opened(item[1])
                elif kind == "opened_none":
                    self.opening = False
                    self._set_input(True)
                elif kind == "done":
                    self._on_done()
                elif kind == "status":
                    self._update_status()
            except tk.TclError:
                pass
            except BaseException:
                traceback.print_exc(file=self.real_err)
        if self.live and self.live.get("dirty") and not self._has_selection():
            self._flush_live()        # (a selection: wait, so what was selected stays selected)

    def _on_print(self, text, end):
        """one print() from the harness, sorted into what it is"""
        stripped = text.strip("\n").strip()

        if end and stripped.startswith("TOOL CALL: "):
            self._end_block()
            payload = stripped[len("TOOL CALL: "):]
            name, _, rest = payload.partition("(")
            args = rest[:-1] if rest.endswith(")") else rest
            self._add_tool(name.strip(), args)
            return

        if end and stripped.startswith("TOOL RESULT: "):
            payload = stripped[len("TOOL RESULT: "):]
            name, sep, result = payload.partition(" -> ")
            self._add_tool_result(result if sep else payload)
            return

        if end and stripped == "THINKING:":
            self._begin("thinking")
            return
        if end and stripped == "ANSWER:":
            self._begin("answer")
            return
        if end and not stripped:                        # print(): the answer is finished
            self._end_block()
            return
        if end:                                         # a whole line from the program: a note
            self._end_block()
            self._note(stripped)
            return
        self._piece(text)                               # a piece of the answer / the thinking

    def _on_raw(self, s):
        """anything written straight to stdout or stderr: whole lines become notes"""
        self.rawbuf += s
        while "\n" in self.rawbuf:
            line, self.rawbuf = self.rawbuf.split("\n", 1)
            line = line.strip()
            if line:
                if len(line) > 600:
                    line = line[:600] + " …"
                self._note(line)
        if len(self.rawbuf) > 6000:
            self.rawbuf = self.rawbuf[-2000:]

    def _on_error(self, text):
        self.busy = False
        self._end_block()
        self._error_block(text)
        self._set_input(True)

    def _on_fatal(self, text):
        self._end_block()
        self._error_block(text)
        self._set_input(False)
        self.status_lbl.configure(text="the harness could not start", fg=BAD)
        try:
            print(text, file=self.real_err)
        except BaseException:
            pass

    def _on_done(self):
        self.busy = False
        self._end_block()
        self._set_input(True)
        self._update_tokens()
        self._refresh_sidebar()
        self._update_status()

    # --- drawing pieces ---------------------------------------------------------
    def _note(self, text):
        if not text.strip() or self.live:
            return
        self.txt.insert("end-1c", text.rstrip("\n") + "\n", ("note",))
        self._follow_bottom()

    def _error_block(self, text):
        self.txt.insert("end-1c", "\n" + text.rstrip("\n") + "\n", ("error",))
        self._follow_bottom()

    def _rule(self, text):
        self.txt.insert("end-1c", "\n" + text + "\n", ("rule",))
        self._follow_bottom()

    def _clear_chat(self):
        self.draw = None
        self.drawing = False
        self.txt.delete("1.0", "end")
        self.blocks = {}
        self.block_n = 0
        self.pending_tools = []
        self.live = None
        self.follow = True

    def _new_block(self, kind):
        """a folded block: one line, and the body under it (hidden until the line is clicked)"""
        self.block_n += 1
        n = self.block_n
        body = kind + "body_%d" % n
        hdr = kind + "hdr_%d" % n
        t = self.txt
        if kind == "think":
            t.tag_configure(body, font=self.F["small"], foreground=MUTED, lmargin1=28, lmargin2=28,
                            elide=True, spacing1=2, spacing3=2)
            t.tag_configure(hdr, font=self.F["small_italic"], foreground=MUTED, spacing1=9)
        else:
            t.tag_configure(body, font=self.F["mono_s"], foreground="#57524A", background=TOOLBG,
                            lmargin1=28, lmargin2=28, elide=True, spacing1=1, spacing3=1)
            t.tag_configure(hdr, font=self.F["mono_s"], foreground="#7A6A58", spacing1=10)
        self.blocks[n] = {"kind": kind, "hdr": hdr, "body": body, "open": False, "label": ""}
        t.tag_bind(hdr, "<Button-1>", lambda e, i=n: self._toggle(i))
        t.tag_raise("sel")
        return n

    def _set_header(self, n):
        b = self.blocks[n]
        t = self.txt
        text = ("▾  " if b["open"] else "▸  ") + b["label"]
        r = t.tag_ranges(b["hdr"])
        if r:
            start = str(r[0])
            t.delete(r[0], r[1])
        else:
            start = "end-1c"
        t.insert(start, text, (b["hdr"],))

    def _toggle(self, n):
        b = self.blocks.get(n)
        if not b:
            return
        b["open"] = not b["open"]
        self.txt.tag_configure(b["body"], elide=not b["open"])
        self._set_header(n)          # no "break": the click may also start a selection, that is fine

    def _add_tool(self, name, args):
        n = self._new_block("tool")
        b = self.blocks[n]
        short = " ".join(args.split())
        if len(short) > 90:
            short = short[:90] + " …"
        b["label"] = str(name) + "(" + short + ")"
        self._set_header(n)
        self.txt.insert("end-1c", "\n", ("body",))
        if args.strip():
            self.txt.insert("end-1c", "args: " + args.rstrip("\n") + "\n", (b["body"],))
        self.pending_tools.append(n)
        self._follow_bottom()
        return n

    def _add_tool_result(self, text):
        if not self.pending_tools:
            self._note("tool result: " + " ".join(text.split())[:300])
            return
        n = self.pending_tools.pop(0)
        b = self.blocks[n]
        self.txt.insert("end-1c", "result: " + text.rstrip("\n") + "\n", (b["body"],))
        b["label"] += "   ·  " + short_num(len(text)) + " chars"
        self._set_header(n)
        self._follow_bottom()

    def _add_thinking(self, text):
        n = self._new_block("think")
        b = self.blocks[n]
        b["label"] = "Thinking  ·  " + short_num(len(text)) + " chars"
        self._set_header(n)
        self.txt.insert("end-1c", "\n", ("body",))
        self.txt.insert("end-1c", text.rstrip("\n") + "\n", (b["body"],))
        self._follow_bottom()

    def _add_checkpoint(self, text):
        """where the conversation was emptied into a checkpoint: everything above it is history the model
        no longer carries (it has the checkpoint instead), everything below is the live context"""
        n = self._new_block("think")
        b = self.blocks[n]
        b["label"] = "checkpoint  ·  " + short_num(len(text)) + " chars  -  the conversation was emptied here"
        self._set_header(n)
        self.txt.insert("end-1c", "\n", ("body",))
        self.txt.insert("end-1c", text.rstrip("\n") + "\n", (b["body"],))
        self._follow_bottom()

    def _add_answer(self, text):
        self.txt.insert("end-1c", "\n", ("body",))
        render_markdown(self.txt, text)
        self.txt.insert("end-1c", "\n", ("body",))
        self._follow_bottom()

    def _user_message(self, text):
        self._end_block()
        w = _Writer(self.txt)
        w.put("\n", ("body",))
        w.put("You", ("you",))
        w.put("\n", ("body",))
        for line in text.split("\n"):
            if line.strip():
                insert_inline(w, line, ("user",))
            w.put("\n", ("user",))
        w.flush()
        self.follow = True
        self._follow_bottom()

    # --- the block that is streaming in right now ------------------------------
    def _begin(self, kind):
        self._end_block()
        if kind == "answer":
            self.txt.insert("end-1c", "\n", ("body",))
            self.txt.mark_set("live_start", "end-1c")
            self.txt.mark_gravity("live_start", "left")
            self.live = {"kind": "answer", "text": "", "dirty": False, "mark": "live_start"}
        else:
            n = self._new_block("think")
            b = self.blocks[n]
            b["label"] = "Thinking…"
            self._set_header(n)
            self.txt.insert("end-1c", "\n", ("body",))
            self.live = {"kind": "thinking", "text": "", "dirty": False, "n": n, "shown": 0}

    def _piece(self, text):
        if self.live is None:
            self._begin("answer")
        self.live["text"] += text
        self.live["dirty"] = True

    def _flush_live(self, done=False):
        live = self.live
        if not live:
            return
        live["dirty"] = False
        t = self.txt
        if live["kind"] == "answer":
            t.delete(live["mark"], "end-1c")
            render_markdown(t, live["text"])
            if not done:
                t.insert("end-1c", " ▌", ("body", "cursor"))
                t.tag_raise("sel")
            # the mark stays where it is: right after deleting, that IS the spot to draw the answer again
        else:
            new = live["text"][live["shown"]:]
            live["shown"] = len(live["text"])
            if new:
                t.insert("end-1c", new, (self.blocks[live["n"]]["body"],))
        self._follow_bottom()

    def _end_block(self):
        if not self.live:
            return
        if self._has_selection() and not self.live["dirty"]:
            # everything is drawn already: only the cursor has to go, so the reader keeps what they selected
            self._drop_cursor()
        else:
            self._flush_live(done=True)
        if self.live["kind"] == "thinking":
            n = self.live["n"]
            b = self.blocks[n]
            b["label"] = "Thinking  ·  " + short_num(len(self.live["text"])) + " chars"
            self._set_header(n)
            self.txt.insert("end-1c", "\n", (b["body"],))     # hidden with the body
        else:
            self.txt.insert("end-1c", "\n", ("body",))
        self.live = None
        self._follow_bottom()

    # --- showing a conversation -------------------------------------------------
    def _read_log(self, name):
        """everything ever said in a conversation, out of log.jsonl (which is only ever added to).
        None if there is no log at all. this is more than state.json has: a checkpoint empties the
        conversation to make room, but never the log"""
        path = self.conv_mod.log_of(name)
        if not os.path.isfile(path):
            return None
        entries = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue                        # a half written line (the program died mid write)
                kind = item.get("kind")
                if kind == "system":
                    text = item.get("content") or ""
                    if "<checkpoint>" in text:      # the conversation was emptied here: show the note
                        start = text.find("<checkpoint>") + len("<checkpoint>")
                        end = text.find("</checkpoint>")
                        body = text[start:end].strip() if end > start else text
                        entries.append({"role": "_checkpoint", "content": body})
                elif kind == "message":
                    message = item.get("message") or {}
                    if message.get("role"):
                        entries.append(message)
        return entries

    def _draw_history(self, start, anchor=None):
        """draw a conversation from entry `start` to the end, a few entries at a time, so the window answers
        while it happens. anchor: an entry to keep in view afterwards (used when bringing earlier ones in)"""
        self._clear_chat()
        self._rule("conversation " + (self.current or ""))
        if start > 0:
            self._earlier_line(start)
        self.draw = {"i": start, "n": len(self.history), "anchor": anchor}
        self.drawing = True
        self._draw_step()

    def _earlier_line(self, start):
        """the one line at the top: click it to bring the whole conversation in"""
        tag = "earlier_%d" % next(_link_ids)
        self.txt.tag_configure(tag, font=self.F["small_italic"], foreground=ACCENT,
                               spacing1=10, spacing3=12)
        self.txt.tag_bind(tag, "<Button-1>", lambda e, s=start: self._draw_history(0, anchor=s))
        self.txt.tag_raise("sel")
        self.txt.insert("end-1c", "▸  " + str(start) + " earlier messages - click to bring them in\n", (tag,))

    def _draw_step(self):
        job = self.draw
        if not job:
            return
        until = time.time() + 0.04                  # draw for a moment, then give the window its turn
        while job["i"] < job["n"] and time.time() < until:
            if job["anchor"] is not None and job["i"] == job["anchor"]:
                self.txt.mark_set("hist_anchor", "end-1c")
            self._draw_entry(self.history[job["i"]])
            job["i"] += 1
        if job["i"] < job["n"]:
            try:
                self.busy_lbl.configure(text="loading %d%%" % (100 * job["i"] // max(1, job["n"])))
            except tk.TclError:
                pass
            self.root.after(1, self._draw_step)
            return
        self.draw = None
        self.drawing = False
        if job["anchor"] is not None:               # stay where the reader was, not at the very end
            self.follow = False
            try:
                self.txt.see("hist_anchor")
            except tk.TclError:
                pass
        else:
            self.follow = True
            self._follow_bottom()
        try:
            self.busy_lbl.configure(text="working…" if self.busy else "")
        except tk.TclError:
            pass

    def _draw_entry(self, m):
        """one message of a saved conversation: the same shapes the window draws while the agent works"""
        role = m.get("role")
        if role == "user":
            text = m.get("content") or ""
            if text.startswith("[from the program, not the user]"):
                first = text.split("\n")[0]
                self._note("· " + (first[:180] + " …" if len(first) > 180 else first))
            else:
                self._user_message(text)
        elif role == "assistant":
            think = m.get("reasoning_content") or m.get("reasoning")
            if think:
                self._add_thinking(think)
            content = m.get("content") or ""
            if content.strip():
                self._add_answer(content)
            for call in (m.get("tool_calls") or []):
                fn = call.get("function") or {}
                self._add_tool(fn.get("name") or "?", fn.get("arguments") or "")
        elif role == "tool":
            self._add_tool_result(m.get("content") or "")
        elif role == "_checkpoint":
            self._add_checkpoint(m.get("content") or "")

    # --- the counters in the top bar -------------------------------------------
    def _update_tokens(self):
        used = 0
        if self.agent is not None:
            try:
                used = self.agent.size()
            except BaseException:
                used = getattr(self.agent, "tokens", 0) or 0
        limit = self.limit or 0
        frac = (float(used) / limit) if limit else 0.0
        frac = max(0.0, min(1.0, frac))
        colour = OK if frac < 0.6 else (WARN if frac < 0.8 else BAD)
        c = self.tok_bar
        c.delete("all")
        c.create_rectangle(0, 0, 110, 6, fill="#E6E1D7", outline="")
        if frac > 0:
            c.create_rectangle(0, 0, max(3, int(110 * frac)), 6, fill=colour, outline="")
        if limit:
            self.tok_lbl.configure(text=short_num(used) + " / " + short_num(limit) + "  ·  "
                                        + str(int(round(frac * 100))) + "%")
        else:
            self.tok_lbl.configure(text=short_num(used) + " tokens")

    def _update_status(self):
        text = ""
        if self.workspace:
            try:
                text = self.workspace.status_line()
            except BaseException:
                text = ""
        if not text:
            text = "no sandbox"
        self.status_lbl.configure(text=text)

    # --- /commands --------------------------------------------------------------
    def _command(self, text):
        words = text.split()
        cmd = words[0].lower()

        if cmd in ("/exit", "/quit"):
            self._quit()
        elif cmd == "/new":
            self._new()
        elif cmd == "/list":
            self._show_list()
        elif cmd == "/open":
            self._cmd_open(words)
        elif cmd == "/rename":
            self._cmd_rename(words)
        elif cmd == "/delete":
            self._cmd_delete(words)
        elif cmd == "/sandbox":
            self._cmd_sandbox(words)
        elif cmd == "/help":
            self._help()
        else:
            self._note("command not found: " + words[0] + "    (try /help)")

    def _cmd_open(self, words):
        name = words[1] if len(words) > 1 else None
        if name is None:
            self._picker()                      # /open with nothing after it: pick one from a little list
            return
        if not self.conv_mod.exists(name):
            self._note("no conversation called '" + name + "'. /list shows them")
            return
        self._open(name)

    def _picker(self):
        """a small window with every saved conversation: double click one to open it"""
        names = self.conv_mod.names()
        if not names:
            self._note("no saved conversations yet")
            return
        top = tk.Toplevel(self.root)
        top.title("open a conversation")
        top.configure(bg=BG)
        top.geometry("460x480")
        top.transient(self.root)
        self.hover_until = time.time() + 600      # the list stays out while this is open

        tk.Label(top, text="open a conversation", bg=BG, fg=TEXT, font=self.F["ui_bold"],
                 anchor="w").pack(side="top", fill="x", padx=14, pady=(12, 6))

        wrap = tk.Frame(top, bg=BG)
        wrap.pack(side="top", fill="both", expand=True, padx=14)
        lb = tk.Listbox(wrap, bg=BG, fg=TEXT, font=self.F["ui"], relief="flat", highlightthickness=0,
                        borderwidth=0, activestyle="none", selectbackground=SELECT,
                        selectforeground=TEXT, exportselection=False, cursor="hand2")
        lb.pack(side="left", fill="both", expand=True)
        bar = ttk.Scrollbar(wrap, orient="vertical", command=lb.yview)
        bar.pack(side="right", fill="y")
        lb.configure(yscrollcommand=bar.set)
        for name in names:
            lb.insert("end", "  " + self._pretty(name))
        if self.current in names:
            lb.selection_set(names.index(self.current))
            lb.see(names.index(self.current))

        def pick(event=None):
            sel = lb.curselection()
            if sel:
                chosen = names[int(sel[0])]
                close()
                self._open(chosen)

        def close():
            self.hover_until = time.time() + 0.3
            try:
                top.grab_release()
            except tk.TclError:
                pass
            top.destroy()

        lb.bind("<Double-Button-1>", pick)
        lb.bind("<Return>", pick)
        tk.Label(top, text="double click one, or pick it and press Open", bg=BG, fg=FAINT,
                 font=self.F["tiny"], anchor="w").pack(side="top", fill="x", padx=14, pady=(6, 0))
        row = tk.Frame(top, bg=BG)
        row.pack(side="top", fill="x", padx=14, pady=12)
        tk.Button(row, text="Open", command=pick, bg=ACCENT, fg="white", relief="flat", bd=0,
                  highlightthickness=0, activebackground=ACCENT_D, activeforeground="white",
                  cursor="hand2", padx=16, pady=5, font=self.F["ui_bold"]).pack(side="right")
        tk.Button(row, text="Cancel", command=close, bg=BG, fg=MUTED, relief="flat", bd=0,
                  highlightthickness=0, activebackground=PANEL_2, cursor="hand2", padx=12,
                  pady=5, font=self.F["ui"]).pack(side="right", padx=(0, 8))
        top.protocol("WM_DELETE_WINDOW", close)
        lb.focus_set()
        try:
            top.grab_set()
        except tk.TclError:
            pass

    def _cmd_rename(self, words):
        if len(words) == 2:
            old, new = self.current, words[1]
        elif len(words) >= 3:
            old, new = words[1], words[2]
        else:
            self._note("usage: /rename <new name>   or   /rename <old> <new>")
            return
        problem = self.conv_mod.rename(old, new)
        if problem:
            self._note(problem)
            return
        if old == self.current:
            self.current = new
            self.agent.log_file = self.conv_mod.log_of(new)
            self.agent.results_dir = self.conv_mod.results_of(new)
            self.agent.checkpoint_file = self.conv_mod.checkpoint_of(new)
        self._note("renamed " + old + " -> " + new)
        self._refresh_sidebar()

    def _cmd_delete(self, words):
        name = words[1] if len(words) > 1 else self.current
        if not self.conv_mod.exists(name):
            self._note("no conversation called '" + name + "'")
            return
        if not messagebox.askyesno("delete", "Delete '" + name + "' with everything in it?\nNo undo.",
                                   parent=self.root):
            self._note("not deleted")
            return
        problem = self.conv_mod.delete(name)
        if problem:
            self._note(problem)
            return
        self._note("deleted " + name)
        if name == self.current:
            self._new()
        else:
            self._refresh_sidebar()

    def _cmd_sandbox(self, words):
        if not self.workspace:
            self._note("podman is not installed or not running, so there are no sandboxes")
            return
        if len(words) == 1:
            self._run_bg(self.workspace.overview)
        elif words[1] == "net" and len(words) > 2 and words[2] in ("on", "off"):
            self._run_bg(lambda: self.workspace.user_network(words[2] == "on"))
        elif words[1] == "close":
            self._run_bg(self.workspace.user_close)
        elif words[1] == "shell":
            self._note("the interactive root shell only works in main.py in a terminal")
        else:
            self._note("usage: /sandbox   |   /sandbox net on|off   |   /sandbox close")

    def _run_bg(self, fn):
        def work():
            try:
                self.q.put(("note", fn()))
            except BaseException:
                self.q.put(("error", traceback.format_exc()))
            self.q.put(("status", None))
        threading.Thread(target=work, daemon=True).start()

    def _help(self):
        lines = [
            "commands:",
            "  /new                     start a new conversation",
            "  /open <name>             continue a saved one (or /open, and pick)",
            "  /list                    show the saved conversations",
            "  /rename <new>            rename this conversation",
            "  /rename <old> <new>      rename another one",
            "  /delete [name]           delete a conversation, with everything in it",
            "  /sandbox                 what runs in the sandbox, and every sandbox",
            "  /sandbox net on|off      the sandbox's internet",
            "  /sandbox close           stop the sandbox",
            "  /help                    this list",
            "  /exit  /quit             leave",
            "",
            "the mouse: click a conversation on the left to continue it (the ☰ up there pins that list),",
            "click a line with ▸ to open the thinking or a tool call.",
        ]
        self._note("\n".join(lines))

    # --- leaving ----------------------------------------------------------------
    def _quit(self):
        if self.busy:
            self.hover_until = time.time() + 60
            yes = messagebox.askokcancel("quit", "The agent is working.\nLeave anyway?", parent=self.root)
            self.hover_until = 0
            if not yes:
                return
        try:
            if self.agent is not None and self.current and self.conv_mod:
                self.conv_mod.save(self.current, self.agent)
        except BaseException:
            pass
        try:
            sys.stdout, sys.stderr = self.real_out, self.real_err
        except BaseException:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass


class _Stream:
    """stands in for sys.stdout / sys.stderr: everything written goes into the queue"""

    def __init__(self, q, name):
        self.q = q
        self.name = name
        self.encoding = "utf-8"
        self.errors = "replace"

    def write(self, s):
        if s:
            self.q.put(("raw", str(s)))
        return len(s)

    def writelines(self, lines):
        for line in lines:
            self.write(line)

    def flush(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        raise io.UnsupportedOperation("no file number: this is the window")

    closed = False


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except BaseException:
            pass
    try:
        root = tk.Tk()
    except tk.TclError as e:
        raise SystemExit("could not open a window: " + str(e) +
                         "\n(this needs a desktop: run it on your computer, not over ssh)")
    app = Gui(root)          # noqa: F841  (kept alive while the window runs)
    root.mainloop()


if __name__ == "__main__":
    main()
