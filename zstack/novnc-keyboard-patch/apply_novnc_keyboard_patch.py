#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
noVNC keyboard mapping patch for ZStack zsv-novnc bundle.

Fixes two defects in noVNC's Keyboard implementation shipped inside the
`zsv-novnc` micro-frontend bundle (chunk file name pattern: 2369.*.js):

  1. Shift-modified characters (@ # $ % ...) are sent as a bare keysym
     without the Shift modifier.  Linux text consoles rely on qemu mapping
     the keysym back to a scancode, and drop such keysyms.

  2. When an input method is active, `event.key` is a multi-character string
     (e.g. "Process"), which hits `if (1 !== e.length) return null` and the
     key press is silently discarded.

Usage (run on a ZStack management node, as root):

  python3 apply_novnc_keyboard_patch.py --check          # dry-run, report only
  python3 apply_novnc_keyboard_patch.py --apply          # apply (idempotent)
  python3 apply_novnc_keyboard_patch.py --revert DIR     # restore a backup

--apply always:
  * creates a timestamped backup next to the target (or under --backup-dir)
  * refuses to touch a file whose content matches nothing known
  * validates the result with `node --check` when node is available

Exit codes: 0 = ok / no change needed, 1 = error, 2 = target not found.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

# --- patch payload -----------------------------------------------------------
# Keysym resolution tail: replace the "give up on multi-char keys" branch with
# a fallback that derives the character from event.code + event.shiftKey.
P1_BEFORE = r'''if(1!==e.length)return null;let i=e.charCodeAt();return i?t1.lookup(i):null'''

P1_AFTER = r'''if(1!==e.length){let n=(function(q){let m={Digit1:"1!",Digit2:"2@",Digit3:"3#",Digit4:"4$",Digit5:"5%",Digit6:"6^",Digit7:"7&",Digit8:"8*",Digit9:"9(",Digit0:"0)",Minus:"-_",Equal:"=+",BracketLeft:"[{",BracketRight:"]}",Backslash:"\\|",Semicolon:";:",Quote:"'\"",Backquote:"`~",Comma:",<",Period:".>",Slash:"/?",Space:"  "};let s=m[q.code];if(!s)return null;return q.shiftKey?s.charAt(1):s.charAt(0)})(t);return n?t1.lookup(n.charCodeAt()):null}let i=e.charCodeAt();return i?t1.lookup(i):null'''

# Final key dispatch: bracket the keysym with an explicit Shift_L press/release
# for characters that need Shift on a US layout.
P2_BEFORE = r'''this._sendKeyEvent(i,e,!0)}_handleKeyUp(t){'''

P2_AFTER = r'''(t&&t.shiftKey&&i&&i<256&&"!@#$%^&*()_+{}|:<>?~".indexOf(String.fromCharCode(i))>-1&&"ShiftLeft"!==e&&"ShiftRight"!==e)?(this._sendKeyEvent(t$.A.XK_Shift_L,"ShiftLeft",!0),this._sendKeyEvent(i,e,!0),this._sendKeyEvent(i,e,!1),this._sendKeyEvent(t$.A.XK_Shift_L,"ShiftLeft",!1)):this._sendKeyEvent(i,e,!0)}_handleKeyUp(t){'''

PATCHES = [
    ("keysym-fallback (IME safe)", P1_BEFORE, P1_AFTER),
    ("shift-modifier burst", P2_BEFORE, P2_AFTER),
]

DEFAULT_GLOBS = [
    "/usr/local/zstack/zstack-ui/zstack-ui/zsv-novnc",
    "/usr/local/zstack/zstack-ui/zstack-ui",
]
TARGET_RE = re.compile(r"^2369\.[0-9a-f]+\.js$")


def find_targets(paths, explicit):
    if explicit:
        return [explicit]
    hits = []
    for base in paths:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            full = os.path.join(base, name)
            if os.path.isfile(full) and TARGET_RE.match(name):
                hits.append(full)
    return hits


def read(path):
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8", "surrogateescape")


def write(path, text):
    with open(path, "wb") as fh:
        fh.write(text.encode("utf-8", "surrogateescape"))


def node_check(path):
    node = shutil.which("node") or shutil.which("nodejs")
    if not node:
        return "skipped (node not found)"
    proc = subprocess.run([node, "--check", path],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return "OK" if proc.returncode == 0 else "FAILED\n" + proc.stdout.decode("utf-8", "replace")


def state_of(text):
    """Classify the bundle.

    Note: for patch 2 the *after* payload still contains the *before* payload as
    a substring (the original dispatch is the else-branch), so "before not in
    text" is not a valid "already patched" signal.  Presence of the after-payload
    is authoritative.
    """
    done = sum(1 for _, _before, after in PATCHES if after in text)
    if done == len(PATCHES):
        return "patched"
    original = sum(1 for _, before, after in PATCHES
                   if before in text and after not in text)
    if original == len(PATCHES):
        return "original"
    return "partial(%d/%d patched, %d/%d intact)" % (
        done, len(PATCHES), original, len(PATCHES))


def apply_to(path, backup_dir=None, dry_run=False):
    text = read(path)
    st = state_of(text)

    if st == "patched":
        print("  [skip] already patched: %s" % path)
        return 0
    if st.startswith("partial"):
        print("  [error] %s is in unexpected state %s; refusing to modify" % (path, st))
        return 1

    for name, before, after in PATCHES:
        if text.count(before) != 1:
            print("  [error] pattern not unique (%s, count=%d) in %s"
                  % (name, text.count(before), path))
            return 1

    if dry_run:
        print("  [dry-run] would patch: %s" % path)
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(backup_dir or os.path.dirname(path),
                          "2369.js.bak-%s" % stamp)
    shutil.copy2(path, backup)
    print("  backup : %s" % backup)

    for name, before, after in PATCHES:
        text = text.replace(before, after, 1)
    write(path, text)

    try:
        st_os = os.stat(path)
        os.chmod(path, st_os.st_mode)
    except OSError:
        pass

    print("  patched: %s (%d bytes)" % (path, len(text.encode("utf-8", "surrogateescape"))))
    print("  md5    : %s" % hashlib.md5(
        text.encode("utf-8", "surrogateescape")).hexdigest())
    print("  node   : %s" % node_check(path))
    print("  NOTE   : browsers cache this file name - hard refresh (Ctrl+Shift+R) "
          "or use a private window to load the patched version.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="noVNC keyboard mapping patch for ZStack zsv-novnc")
    ap.add_argument("--target", help="explicit path to the 2369.*.js bundle")
    ap.add_argument("--path", action="append", default=[],
                    help="extra directory to scan (repeatable)")
    ap.add_argument("--backup-dir", help="directory for backups (default: next to target)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="report state only, change nothing")
    g.add_argument("--apply", action="store_true", help="apply the patch")
    g.add_argument("--revert", metavar="BACKUP_FILE", help="restore a backup file over the target")
    args = ap.parse_args()

    targets = find_targets(DEFAULT_GLOBS + args.path, args.target)
    if not targets:
        print("error: no 2369.*.js bundle found; pass --target explicitly", file=sys.stderr)
        return 2

    print("targets: %d" % len(targets))
    rc = 0

    if args.revert:
        if not args.target:
            print("error: --revert requires --target", file=sys.stderr)
            return 1
        shutil.copy2(args.revert, args.target)
        print("restored %s -> %s" % (args.revert, args.target))
        print("node   : %s" % node_check(args.target))
        return 0

    for t in targets:
        print("- %s" % t)
        try:
            print("  state  : %s" % state_of(read(t)))
        except OSError as exc:
            print("  [error] %s" % exc)
            rc = 1
            continue
        if args.apply:
            rc |= apply_to(t, args.backup_dir)
    return rc


if __name__ == "__main__":
    sys.exit(main())
