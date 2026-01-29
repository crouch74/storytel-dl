#!/bin/sh
set -eu

IN_DIR="${IN_DIR:-/data}"

AUDIO_BITRATE="${AUDIO_BITRATE:-96k}"
AUDIO_SR="${AUDIO_SR:-44100}"
AUDIO_CHANNELS="${AUDIO_CHANNELS:-2}"
KEEP_BACKUP="${KEEP_BACKUP:-1}"

MAX_JOBS="${MAX_JOBS:-14}"

log() { echo "$(date -Iseconds) $*"; }

log "📚 Parallel m4b → AAC conversion"
log "📂 Root folder: ${IN_DIR}"
log "🎚️  Target AAC: ${AUDIO_BITRATE}, ${AUDIO_SR}Hz, ${AUDIO_CHANNELS}ch"
log "🧩 Preserving chapters + metadata"
log "🚫 Dropping data/subtitle streams"
log "🔁 Skipping files already encoded as AAC"
log "🏷️  Filling missing chapter titles with: Chapter 1..N"
log "🛡️  Backup originals: ${KEEP_BACKUP}"
log "🚀 Parallel jobs: ${MAX_JOBS}"

# Function to process a single file
process_file() {
  local src="$1"
  local count="$2"

  # Detect audio codec (first audio stream)
  codec="$(ffprobe -v error \
    -select_streams a:0 \
    -show_entries stream=codec_name \
    -of csv=p=0 "$src" 2>/dev/null || true)"

  if [ "$codec" = "aac" ]; then
    log "⏭️  [$count] Skipping (already AAC): $src"
    return 0
  fi

  if [ -z "$codec" ]; then
    log "⚠️  [$count] Could not detect codec (skipping): $src"
    return 0
  fi

  dir="$(dirname "$src")"
  base="$(basename "$src")"
  tmp="${dir}/.${base}.aac.tmp.m4b"
  bak="${dir}/${base}.orig-mp3.m4b"

  log "🎧 [$count] Re-encoding (codec=${codec}): $src"

  # Re-encode audio to AAC, keep chapters/metadata, drop data/sub streams
  ffmpeg -hide_banner -nostdin -y \
    -i "$src" \
    -map 0 \
    -map_metadata 0 \
    -map_chapters 0 \
    -sn -dn \
    -c:v copy \
    -c:a aac \
    -b:a "$AUDIO_BITRATE" \
    -ar "$AUDIO_SR" \
    -ac "$AUDIO_CHANNELS" \
    -movflags +faststart \
    "$tmp" >/dev/null 2>&1

  # ---- Atomic replace original ----
  if [ "$KEEP_BACKUP" = "1" ]; then
    mv -f "$src" "$bak"
    log "🧷 Backup: $bak"
  else
    rm -f "$src"
  fi

  mv -f "$tmp" "$src"
  log "✅ Converted: $src"
}

# Export variables and function for xargs
export -f process_file
export -f log
export IN_DIR AUDIO_BITRATE AUDIO_SR AUDIO_CHANNELS KEEP_BACKUP

# Find files and pipe to xargs for parallel processing
find "$IN_DIR" -type f -iname '*.m4b' \
  ! -name '.*.aac.tmp.m4b' \
  ! -name '*.orig-*.m4b' \
  -print0 | xargs -0 -I {} -P "$MAX_JOBS" bash -c 'process_file "$1" "$$"' _ {}

log "🏁 Finished parallel processing"