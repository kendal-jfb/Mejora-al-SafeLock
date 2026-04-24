#!/bin/bash

TAILSCALE_LOCK_FILE="/run/tailscale-recovery.lock"
TAILSCALE_AUTHKEY_FILE="/etc/tailscale-authkey"
TAILSCALE_HOSTNAME_FILE="/etc/hostname"
TAILSCALE_NET_IF="${TAILSCALE_NET_IF:-end0}"
TAILSCALE_NETWORK_TIMEOUT="${TAILSCALE_NETWORK_TIMEOUT:-120}"
TAILSCALE_BACKOFF_SEC="${TAILSCALE_BACKOFF_SEC:-5}"

ts_log() {
    local log_file="$1"
    shift
    mkdir -p "$(dirname "$log_file")"
    touch "$log_file"
    chmod 644 "$log_file"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$log_file"
}

ts_get_hostname() {
    local mac_address

    if [ ! -r "/sys/class/net/$TAILSCALE_NET_IF/address" ]; then
        return 1
    fi

    mac_address="$(tr -d ':\r\n' < "/sys/class/net/$TAILSCALE_NET_IF/address")"
    [ -n "$mac_address" ] || return 1
    printf 'safelock-%s\n' "$mac_address"
}

ts_set_static_hostname() {
    local new_hostname="$1"
    local current_hostname

    current_hostname="$(cat "$TAILSCALE_HOSTNAME_FILE" 2>/dev/null || hostname 2>/dev/null || true)"

    if [ "$current_hostname" != "$new_hostname" ]; then
        printf '%s\n' "$new_hostname" > "$TAILSCALE_HOSTNAME_FILE"
        hostname "$new_hostname" || true
    fi
}

ts_tailscaled_active() {
    systemctl is-active --quiet tailscaled
}

ts_backend_state() {
    tailscale status --json 2>/dev/null | sed -n 's/.*"BackendState"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1
}

ts_running_with_ipv4() {
    if ip -4 addr show tailscale0 2>/dev/null | grep -q 'inet '; then
        return 0
    fi

    [ "$(ts_backend_state)" = "Running" ] && tailscale ip -4 2>/dev/null | grep -q '.'
}

ts_wait_for_tailscaled() {
    local timeout="${1:-30}"
    local elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if ts_tailscaled_active; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    return 1
}

ts_wait_for_network() {
    local timeout="${1:-$TAILSCALE_NETWORK_TIMEOUT}"
    local elapsed=0

    while [ "$elapsed" -lt "$timeout" ]; do
        if ip -4 route show default 2>/dev/null | grep -q '^default ' && \
           getent ahostsv4 controlplane.tailscale.com >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    return 1
}

ts_start_daemon_if_needed() {
    if ts_tailscaled_active; then
        return 0
    fi

    systemctl start tailscaled
    ts_wait_for_tailscaled 30
}

ts_needs_login() {
    case "$(ts_backend_state)" in
        NeedsLogin|NoState)
            return 0
            ;;
    esac
    return 1
}

ts_authkey_available() {
    [ -s "$TAILSCALE_AUTHKEY_FILE" ]
}

ts_authkey() {
    tr -d '\r\n' < "$TAILSCALE_AUTHKEY_FILE"
}

ts_run_up() {
    local hostname="$1"
    local authkey="$2"

    tailscale up \
        --authkey="$authkey" \
        --hostname="$hostname" \
        --accept-dns=false \
        --advertise-tags=tag:safelock
}
