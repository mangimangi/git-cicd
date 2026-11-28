# create-issue takes a long issue body as one quoted argument

> Captured: 2026-11-28

## What was happening

While refining epic gcd-1dec into gcd-1dec.1–.3 with `/create-issue "<title>" <type> <parent> "<body>"`, each body was 4–9 KB of markdown containing backticks, JSON and double quotes. To get it through intact, the body had to be written to a scratch file and handed to the forked executor (a "pass it as --body \"$(cat file)\"" note), and then checked afterwards with `prl show` against the source file.

## Headache

create-issue takes the whole issue body as one quoted skill argument. Long markdown bodies with backticks, JSON and double quotes have to be passed in as a file path with a note to the forked executor, and checked afterwards. A `--body-file` option (on `prl create` and on the skill) would remove the guesswork.
