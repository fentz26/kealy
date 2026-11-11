#!/bin/sh
# SPDX-License-Identifier: MIT
#
# Kealy installer bootstrap for the base M3 MacBook Pro (Mac15,3 / J504AP).
#
# Run from macOS on the Mac you want to install on:
#
#   curl -fsSL https://raw.githubusercontent.com/fentz26/kealy/main/install.sh | sh
#
# It downloads a Kealy release and the pinned Asahi Alarm installer, verifies
# their SHA-256 hashes, stages them on the internal disk and then starts the
# interactive Asahi installer, which asks before it resizes anything.
#
# Environment:
#   KEALY_TAG            release tag to install (default: newest release)
#   KEALY_STAGE          staging directory (default: ~/.cache/kealy-install)
#   KEALY_DOWNLOAD_ONLY  set to 1 to download and verify without starting

# Truncation guard: nothing runs unless the whole script arrived.
main() {
    set -eu

    REPO="fentz26/kealy"
    INSTALLER_VERSION="v0.9.2"
    INSTALLER_SHA256="b35fdd7e5e700003bf4f43d2a484eca618ad971dd4266207315cbfa6fe826fad"
    INSTALLER_MIRROR="https://github.com/$REPO/releases/download/upstream-base-61153885/installer-$INSTALLER_VERSION.tar.gz"
    INSTALLER_UPSTREAM="https://asahi-alarm.org/installer-$INSTALLER_VERSION.tar.gz"
    PAYLOAD="arch-m3-minimal.zip"

    export LC_ALL=en_US.UTF-8
    export LANG=en_US.UTF-8
    export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

    say() { printf '%s\n' "$*"; }
    die() { printf 'Kealy installer: %s\n' "$*" >&2; exit 1; }

    [ -e /System/Library/CoreServices/SystemVersion.plist ] \
        || die "this must run from macOS on the target Mac."
    [ "$(uname -m)" = arm64 ] || die "this must run natively on Apple Silicon (not under Rosetta)."

    model=$(sysctl -n hw.model)
    board=$(ioreg -d1 -c IOPlatformExpertDevice -r | tr -d '\000' \
        | sed -n 's/.*"compatible" = <"\(J[0-9]*[A-Z]*AP\)".*/\1/p' | head -1)
    if [ "$model" != "Mac15,3" ] || [ "$board" != "J504AP" ]; then
        die "this build only supports the 14-inch MacBook Pro with the base M3 (Mac15,3 / J504AP). Found: $model / ${board:-unknown board}."
    fi

    fetch() { # url destination
        curl -fL --retry 3 --no-progress-meter -o "$2" "$1"
    }
    check() { # expected-sha256 file
        actual=$(shasum -a 256 "$2" | cut -d' ' -f1)
        [ "$actual" = "$1" ] || die "hash mismatch for $2 (expected $1, got $actual)."
    }

    tag="${KEALY_TAG:-}"
    if [ -z "$tag" ]; then
        tag=$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=30" \
            | sed -n 's/^ *"tag_name": *"\(v[^"]*\)".*/\1/p' | head -1)
        [ -n "$tag" ] || die "no Kealy release found. Set KEALY_TAG to a release tag."
    fi
    base="https://github.com/$REPO/releases/download/$tag"

    stage="${KEALY_STAGE:-$HOME/.cache/kealy-install}"
    say
    say "Kealy $tag for $model ($board)"
    say "Staging in $stage"
    say

    mkdir -p "$stage"
    # The installer ships framework symlinks, so the staging area must keep them.
    probe="$stage/.kealy-probe"
    rm -f "$probe" "$probe.link"
    : > "$probe"
    ln -s .kealy-probe "$probe.link" 2>/dev/null && [ -L "$probe.link" ] \
        || die "$stage cannot hold symlinks. Choose a folder on the internal disk with KEALY_STAGE."
    rm -f "$probe" "$probe.link"

    free_kb=$(df -k "$stage" | awk 'NR==2 {print $4}')
    [ "$free_kb" -ge 3145728 ] || die "need at least 3 GB free in $stage for the download."

    runtime="$stage/runtime"
    rm -rf "$runtime"
    mkdir -p "$runtime/os"
    cd "$stage"

    say "Downloading release checksums..."
    fetch "$base/SHA256SUMS" SHA256SUMS
    payload_sha=$(awk -v f="$PAYLOAD" '$2 == f {print $1}' SHA256SUMS)
    data_sha=$(awk '$2 == "installer_data.json" {print $1}' SHA256SUMS)
    [ "${#payload_sha}" -eq 64 ] && [ "${#data_sha}" -eq 64 ] || die "release checksums are incomplete."

    say "Downloading the Asahi Alarm installer $INSTALLER_VERSION..."
    fetch "$INSTALLER_MIRROR" installer.tar.gz || fetch "$INSTALLER_UPSTREAM" installer.tar.gz
    check "$INSTALLER_SHA256" installer.tar.gz

    say "Downloading the Kealy image (about 1.5 GB)..."
    if [ -f "$PAYLOAD" ] && [ "$(shasum -a 256 "$PAYLOAD" | cut -d' ' -f1)" = "$payload_sha" ]; then
        say "  already downloaded."
    else
        curl -fL --retry 3 -C - -o "$PAYLOAD" "$base/$PAYLOAD" || fetch "$base/$PAYLOAD" "$PAYLOAD"
        check "$payload_sha" "$PAYLOAD"
    fi
    fetch "$base/installer_data.json" installer_data.json
    check "$data_sha" installer_data.json

    say "Preparing..."
    tar xf installer.tar.gz -C "$runtime"
    [ "$(cat "$runtime/version.tag")" = "$INSTALLER_VERSION" ] || die "unexpected installer version."
    cp installer_data.json "$runtime/installer_data.json"
    ln "$PAYLOAD" "$runtime/os/$PAYLOAD" 2>/dev/null || cp "$PAYLOAD" "$runtime/os/$PAYLOAD"
    check "$payload_sha" "$runtime/os/$PAYLOAD"

    if [ "${KEALY_DOWNLOAD_ONLY:-0}" = 1 ]; then
        say
        say "Downloaded and verified. Nothing was installed."
        say "To start the installer later: cd \"$runtime\" && sudo REPO_BASE=\"$runtime\" ./install.sh"
        exit 0
    fi

    cat <<EOF

Before you continue:

  * Kealy is experimental and has not been booted on real hardware yet.
    The built-in screen, keyboard, trackpad and Wi-Fi may not work on first boot.
  * The installer will shrink your macOS volume to make room for Linux.
    It asks how much space to use and confirms before changing the disk.
  * Have a current backup of this Mac. macOS stays installed and bootable.
  * The image is not encrypted. USB-C display output is on the left-back port.
  * There is no graphics acceleration on the M3 yet.

EOF
    printf 'Type "install" to start the Asahi installer, anything else to stop: '
    read -r answer </dev/tty
    [ "$answer" = "install" ] || { say "Stopped. Nothing was installed."; exit 0; }

    cd "$runtime"
    # Local payload only; no usage report is sent for this unofficial build.
    unset REPORT REPORT_TAG INSTALLER_DATA INSTALLER_BASE VERSION_FLAG
    export REPO_BASE="$runtime"
    if [ "$(id -u)" -ne 0 ]; then
        say "The installer needs to run as root. Enter your password if asked."
        exec caffeinate -dis sudo -E ./install.sh "$@"
    else
        exec caffeinate -dis ./install.sh "$@"
    fi
}

main "$@"
