#!/bin/sh

if [ -n "$TZ" ]; then
    if [ -f "/usr/share/zoneinfo/$TZ" ]; then
        cp "/usr/share/zoneinfo/$TZ" /etc/localtime
        echo "$TZ" > /etc/timezone
    else
        echo "Warning: Timezone $TZ not found, using default"
    fi
else
    echo "No TZ environment variable set, using default"
fi

# Join whatever group owns the mounted docker socket; host docker GIDs vary (image default is 988).
if [ -S /var/run/docker.sock ]; then
    SOCK_GID=$(stat -c %g /var/run/docker.sock)
    SOCK_GROUP=$(awk -F: -v gid="$SOCK_GID" '$3 == gid {print $1}' /etc/group)
    if [ -z "$SOCK_GROUP" ]; then
        SOCK_GROUP=dockerhost
        addgroup -g "$SOCK_GID" "$SOCK_GROUP"
    fi
    # Errors only when already a member (e.g. on container restart)
    addgroup nonroot "$SOCK_GROUP" 2>/dev/null || true
fi

exec su-exec nonroot "$@"