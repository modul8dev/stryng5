#!/bin/sh
set -e

ensure_owned() {
  target="$1"
  if [ -z "$target" ]; then
    return
  fi

  if [ "$(id -u)" -ne 0 ]; then
    sudo mkdir -p "$target"
    sudo chown -R vscode:vscode "$target"
  else
    mkdir -p "$target"
    chown -R vscode:vscode "$target"
  fi
}

if [ -d /home/vscode ]; then
  ensure_owned /home/vscode/.config/Code/User/globalStorage
fi

exec "$@"
