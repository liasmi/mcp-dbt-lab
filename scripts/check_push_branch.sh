#!/bin/sh
set -eu

branch=$(git symbolic-ref --quiet --short HEAD || true)
if [ "$branch" = "main" ]; then
    echo "Direct pushes from main are blocked. Switch to a feature branch and open a pull request." >&2
    exit 1
fi
