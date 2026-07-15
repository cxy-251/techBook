#!/bin/sh

set -u

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <audit-verified-through>" >&2
    exit 2
fi

case "$1" in
    ''|*[!0-9]*)
        echo "audit-verified-through must be a chapter number" >&2
        exit 2
        ;;
esac

limit=$(awk -v value="$1" 'BEGIN { print value + 0 }')
if [ "$limit" -lt 1 ] || [ "$limit" -gt 999 ]; then
    echo "audit-verified-through must be between 1 and 999" >&2
    exit 2
fi

if ! command -v rg >/dev/null 2>&1; then
    echo "rg is required" >&2
    exit 2
fi

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
chapter_dir="$root/docs/tracks/linux-kernel"
errors=0

fail()
{
    echo "ERROR: $*" >&2
    errors=$((errors + 1))
}

n=1
while [ "$n" -le "$limit" ]; do
    id=$(printf '%03d' "$n")
    matches=$(find "$chapter_dir" -maxdepth 1 -type f -name "$id-*.rst" -print | sort)
    count=$(printf '%s\n' "$matches" | awk 'NF { count++ } END { print count + 0 }')

    if [ "$count" -ne 1 ]; then
        fail "chapter $id has $count files in the audited range"
        n=$((n + 1))
        continue
    fi

    file=$matches
    previous=0
    for section in '本章结束状态' '关键边界' '下一入口' '资料'; do
        section_matches=$(rg -n "^${section}$" "$file" || true)
        section_count=$(printf '%s\n' "$section_matches" | awk 'NF { count++ } END { print count + 0 }')
        if [ "$section_count" -ne 1 ]; then
            fail "$id must contain exactly one '$section' section"
            continue
        fi
        line=$(printf '%s\n' "$section_matches" | awk -F: 'NR == 1 { print $1 }')
        if [ "$line" -le "$previous" ]; then
            fail "$id section '$section' is out of order"
        fi
        previous=$line
    done

    if ! rg -q 'c2a33ad9ad1452e23b41c4ac44a3bc6be8ebc4cf|a759542a2c62f0fd3b65f5a66ad9868201014669|d38d6a1a9b79427848976f53d474392cd29c2a71|7404ce51637231382873d0b55edabc2f3b841a9d' "$file"; then
        fail "$id has no fixed source commit"
    fi

    if rg -q 'Linux 6\.12\.95' "$file"; then
        fail "$id still contains the retired Linux 6.12.95 label"
    fi

    n=$((n + 1))
done

duplicates=$(find "$chapter_dir" -maxdepth 1 -type f -name '[0-9][0-9][0-9]-*.rst' -print |
    awk -F/ '{ id = substr($NF, 1, 3); count[id]++; names[id] = names[id] " " $NF }
               END { for (id in count) if (count[id] > 1) print id ":" names[id] }' |
    sort)

if [ -n "$duplicates" ]; then
    echo "KNOWN DEBT: duplicate chapter files outside or inside the audited range:" >&2
    printf '%s\n' "$duplicates" >&2
fi

if [ "$errors" -ne 0 ]; then
    echo "linux-kernel audit check failed with $errors error(s)" >&2
    exit 1
fi

echo "linux-kernel chapters 001-$limit passed structural audit checks"
