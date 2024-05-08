#!/bin/bash

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

revert_to_backup() {
    if os-config join "$(cat /tmp/config.json.backup)"; then
        log "Successfully executed 'balena join config.json.backup'"
        return 1
    else
        log "Could not revert to backup"
        return 0
    fi
}

# Step 1: Copy /mnt/boot/config.json to /tmp/config.json.backup
if [[ -f /mnt/boot/config.json ]]; then
    cp /mnt/boot/config.json /tmp/config.json.backup
    log "Copied /mnt/boot/config.json to /tmp/config.json.backup"
else
    log "Error: /mnt/boot/config.json does not exist."
    exit 1
fi

# Step 3: Execute 'os-config join config.json'
if os-config join "$(cat /tmp/config.json)"; then
    log "Successfully executed 'balena join config.json'"
else
    log "Error: Failed to execute 'balena join config.json'. Reverting to backup"
    revert_to_backup
    exit 1
fi

# Step 4: Loop 5 times, every minute, to check for /tmp/baton and then do something
for i in {1..9}; do
    if [[ -f /tmp/baton ]]; then
        log "File /tmp/baton found, executing curl"
        # e.g. curl -s http://example.com/api/trigger && log "Curl executed successfully"
        exit 0
    else
        log "File /tmp/baton NOT found. Round $i."
    fi
    sleep 60
done

# If loop completes without finding /tmp/baton, copy backup back
if [[ ! -f /tmp/baton ]]; then
        log "File /tmp/baton NOT found, joining back to backup"
        revert_to_backup
        return $?
fi
