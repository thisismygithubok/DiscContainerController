#!/bin/sh
# DiscContainerController: export the values users picked (settings.env, next to this script), then run the
# container's real entrypoint. Use as `entrypoint: ["/dcc/dcc-env.sh", "<image entrypoint>"]` plus `command:`.
# Lines are KEY=VALUE and are never executed, so a value can't run as code.
f="$(dirname "$0")/settings.env"
if [ -f "$f" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        key=${line%%=*}
        [ "$key" = "$line" ] && continue    # no "="
        case $key in ''|[0-9]*|*[!A-Za-z0-9_]*) continue ;; esac
        export "$key=${line#*=}"
    done < "$f"
fi
exec "$@"
