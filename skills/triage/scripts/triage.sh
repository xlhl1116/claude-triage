#!/bin/sh
# Run triage.py with whichever Python 3.9+ is installed: python3 (Linux, macOS), python or
# the py launcher (Windows, where "python3" is often only the Microsoft Store stub).
# Plain POSIX sh with no external commands, so it works in Git Bash on Windows too.
here=${0%/*}
[ "$here" = "$0" ] && here=.
for py in python3 python "py -3"; do
  if $py -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
    exec $py "$here/triage.py" "$@"
  fi
done
echo "claude-triage: Python 3.9 or later not found (tried python3, python, py -3)" >&2
exit 1
