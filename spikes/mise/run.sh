#!/bin/sh
# Re-runs the mise spike from nothing in a throwaway directory (about 1.5 GB, a minute or two with a fast network).
# Every download is checked against a SHA-256 written here; nothing leaves WORK. Linux x86_64 only.
set -eu
WORK=${1:-${TMPDIR:-/tmp}/mise-spike}
V=v2026.10.3
MISE_TAR_SHA=ff0870ddad7f8c5ba673ceb3e7659f0353da8263eabe8b82220f5816a772c786
rm -rf "$WORK"; mkdir -p "$WORK/bootstrap" "$WORK/provider/.config/mise/conf.d"; cd "$WORK"
export MISE_DATA_DIR=$WORK/data MISE_CACHE_DIR=$WORK/cache MISE_STATE_DIR=$WORK/state MISE_CONFIG_DIR=$WORK/config MISE_YES=1

say() { printf '\n== %s\n' "$*"; }

say "1 bootstrap: the pinned mise release, verified before it is unpacked"
curl -fsSL -o mise.tar.xz "https://mise.jdx.dev/$V/mise-$V-linux-x64.tar.xz"
echo "$MISE_TAR_SHA  mise.tar.xz" | sha256sum -c -
tar -xJf mise.tar.xz -C bootstrap
export PATH=$WORK/bootstrap/mise/bin:$PATH
mise --version

say "2 a provider's declarations: one file per entry in .config/mise/conf.d, each pinned by URL and SHA-256"
C=provider/.config/mise/conf.d
printf '[settings]\nlockfile = true\n' > $C/00-settings.toml
cat > $C/jre.toml <<'T'
[tools."http:jre"]
version = "21.0.12.1+1"
strip_components = 1
[tools."http:jre".platforms]
linux-x64 = { url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz", checksum = "sha256:2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500" }
T
cat > $C/asciidoctorj.toml <<'T'
[tools."http:asciidoctorj"]
version = "3.0.1"
strip_components = 1
[tools."http:asciidoctorj".platforms]
linux-x64 = { url = "https://repo1.maven.org/maven2/org/asciidoctor/asciidoctorj/3.0.1/asciidoctorj-3.0.1-bin.zip", checksum = "sha256:18b085b7f67a7f872abe00352be5caacd9b436400aec27f838c6380077cb88bf" }
T
cat > $C/tinytex.toml <<'T'
[tools."http:tinytex"]
version = "2026.03"
strip_components = 1
bin_path = "bin/x86_64-linux"
[tools."http:tinytex".platforms]
linux-x64 = { url = "https://github.com/rstudio/tinytex-releases/releases/download/v2026.03/TinyTeX-v2026.03.tar.gz", checksum = "sha256:3bb654f650582508155ea2027fc0fd6b2fdc3cd7413f986a66714662cff8bdc2" }
T
cat > $C/chromium.toml <<'T'
[tools."http:chromium"]
version = "1.50.0"
[tools."http:chromium".platforms]
linux-x64 = { url = "https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/1155/chromium-linux.zip", checksum = "sha256:cadb84ee9dd3b3a5ce435175c2e39c585c90457292358534acf6e6f2f1fa248d" }
T
mise trust provider >/dev/null

say "3 lock, then install exactly what the lock says, with project code switched off (MISE_SAFE=1)"
MISE_SAFE=1 mise -C provider lock --platform linux-x64 2>&1 | tail -1
MISE_SAFE=1 mise -C provider install --locked 2>&1 | tail -1

say "4 the provider's own PATH: nothing global"
mise -C provider exec -- sh -c 'which java asciidoctorj xelatex; "$(mise where http:chromium)/chrome" --version'

say "5 tamper: a wrong checksum installs nothing"
mise uninstall http:jre@21.0.12.1+1 >/dev/null 2>&1
sed -i 's/2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500/0000000000000000000000000000000000000000000000000000000000000000/' $C/jre.toml
rm -f provider/.config/mise/mise.lock
mise -C provider install 2>&1 | grep -m1 'Checksum mismatch' || echo "UNEXPECTED: tamper was not caught"
[ -d "$MISE_DATA_DIR/installs/http-jre/21.0.12.1+1" ] && echo "UNEXPECTED: tampered tool is installed" || echo "nothing installed"

say "6 hazard: a second provider that reuses a name and version with a different artifact is not checked against the first install"
sed -i 's/0000000000000000000000000000000000000000000000000000000000000000/2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500/' $C/jre.toml
mise -C provider install 2>&1 | tail -1
mkdir -p other; cat > other/mise.toml <<'T'
[tools."http:jre"]
version = "21.0.12.1+1"
strip_components = 1
[tools."http:jre".platforms]
linux-x64 = { url = "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jre_aarch64_linux_hotspot_21.0.12.1_1.tar.gz", checksum = "sha256:14be1f35ebdbd1f6e8d57eb911a3ffb74d6d9aa255abc5daf2b1302002cf2cf2" }
T
mise trust other >/dev/null
mise -C other install 2>&1 | grep -v '░\|██' | tail -2   # says "already installed": the other checksum was never compared

say "6b the fix: the SHA-256 prefix is part of the tool's name, so different content never shares an install and the same content always does"
mkdir -p hash-a hash-b
J=https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1
printf '[tools."http:jre-2413149700df"]\nversion = "21.0.12.1+1"\nstrip_components = 1\n[tools."http:jre-2413149700df".platforms]\nlinux-x64 = { url = "%s/OpenJDK21U-jre_x64_linux_hotspot_21.0.12.1_1.tar.gz", checksum = "sha256:2413149700df0f7d440500a84a8f764c535f21e5a5e87d38328b64eec2c5b500" }\n' "$J" > hash-a/mise.toml
printf '[tools."http:jre-14be1f35ebdb"]\nversion = "21.0.12.1+1"\nstrip_components = 1\n[tools."http:jre-14be1f35ebdb".platforms]\nlinux-x64 = { url = "%s/OpenJDK21U-jre_aarch64_linux_hotspot_21.0.12.1_1.tar.gz", checksum = "sha256:14be1f35ebdbd1f6e8d57eb911a3ffb74d6d9aa255abc5daf2b1302002cf2cf2" }\n' "$J" > hash-b/mise.toml
mise trust hash-a >/dev/null; mise trust hash-b >/dev/null
MISE_SAFE=1 mise -C hash-a install 2>&1 | tail -1; MISE_SAFE=1 mise -C hash-b install 2>&1 | tail -1
ls "$MISE_DATA_DIR/installs" | grep '^http-jre'

say "7 the host environment is not scrubbed by mise; the caller must"
TEXMFHOME=/host/texmf mise -C provider exec -- sh -c 'echo TEXMFHOME=$TEXMFHOME'
echo done
