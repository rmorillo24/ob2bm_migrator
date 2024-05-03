#!/bin/bash

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
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
    log "Error: Failed to execute 'balena join config.json'"
    exit 1
fi

# Step 4: Loop 5 times, every minute, to check for /tmp/batton and then curl
for i in {1..9}; do
    if [[ -f /tmp/batton ]]; then
        log "File /tmp/batton found, executing curl"
        curl -s http://example.com/api/trigger && log "Curl executed successfully"
        exit 0
    else
        log "File /tmp/batton NOT found. Round $i."
    fi
    sleep 60
done

# If loop completes without finding /tmp/batton, copy backup back
if [[ ! -f /tmp/batton ]]; then
        log "File /tmp/batton NOT found, joining back to backup"
        os-config join "$(cat /tmp/config.json.backup)"
        exit 0
fi
