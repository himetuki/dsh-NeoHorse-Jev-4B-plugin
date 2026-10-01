#!/bin/sh
set -eu
mkdir -p /app
cd /app
git init -q
printf 'base\n' > answer.txt
git add answer.txt
GIT_AUTHOR_NAME='DSH Eval' GIT_AUTHOR_EMAIL='eval@invalid.local' \
GIT_COMMITTER_NAME='DSH Eval' GIT_COMMITTER_EMAIL='eval@invalid.local' \
GIT_AUTHOR_DATE='2020-01-01T00:00:00Z' GIT_COMMITTER_DATE='2020-01-01T00:00:00Z' \
git commit -q -m base
