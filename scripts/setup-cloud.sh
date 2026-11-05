#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"
setup=/workspace/.setup
python3 -m venv "$setup/voice-venv"
"$setup/voice-venv/bin/python" -m pip install -r requirements.txt
mkdir -p "$setup/apt/lists/partial" "$setup/apt/cache/archives/partial" "$setup/portaudio"
cat > "$setup/apt/sources.list" <<'SOURCES'
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://deb.debian.org/debian trixie main
deb [signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://security.debian.org/debian-security trixie-security main
SOURCES
apt_options=(-o Dir::Etc::parts=- -o Dir::Etc::sourcelist="$setup/apt/sources.list" -o Dir::Etc::sourceparts=- -o Dir::State::lists="$setup/apt/lists" -o Dir::Cache="$setup/apt/cache")
/usr/bin/apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
cd "$setup"
/usr/bin/apt-get "${apt_options[@]}" download libportaudio2
for pkg in "$setup"/libportaudio2_*.deb; do dpkg-deb -x "$pkg" "$setup/portaudio"; done
ln -sf libportaudio.so.2 "$setup/portaudio/usr/lib/x86_64-linux-gnu/libportaudio.so"
export LIBRARY_PATH="$setup/portaudio/usr/lib/x86_64-linux-gnu${LIBRARY_PATH:+:$LIBRARY_PATH}"
export LD_LIBRARY_PATH="$setup/portaudio/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cd "$project_root"
"$setup/voice-venv/bin/python" -c 'import sounddevice as sd; print("PortAudio:", sd.get_portaudio_version())'
"$setup/voice-venv/bin/python" -m unittest discover -s tests -v
