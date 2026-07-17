#!/usr/bin/env sh
# git commit with signing fallback when GPG/SSH signing key is unavailable.
set -e
if ! git commit "$@"; then
  git -c commit.gpgsign=false commit "$@"
fi
