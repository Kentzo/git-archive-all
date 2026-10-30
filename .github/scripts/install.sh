#!/usr/bin/env bash
# Install interpreters with pyenv.
#
# Usage: install.sh <version>...
#
# <version> is an exact pyenv version such as "3.12.11" or "pypy3.12-7.3.20".
set -euo pipefail

openssl_root=${CI_OPENSSL_ROOT:-$HOME/.cache/ci-openssl}

install_openssl() {
    local version=$1 prefix=$openssl_root/$1 package sha256 src
    [ -d "$prefix/lib" ] && return
    # Prebuilt conda-forge package and its sha256 for this machine.
    case "$version-$(uname -m)" in
        1.1.1w-x86_64)
            package=linux-64/openssl-1.1.1w-hd590300_0.conda
            sha256=4fe19885c77f0758084feb54954bd1977dfeeab7134fba0a1d9c0cfff821d6bd ;;
        1.1.1w-aarch64)
            package=linux-aarch64/openssl-1.1.1w-h31becfc_0.conda
            sha256=48c86f591261ae589c2a2feda8ee85a98302e6dd50c0d697a065cfa5a53f896b ;;
        *)
            echo "::error::no OpenSSL $version package for $(uname -m)" >&2
            exit 1 ;;
    esac
    src=$(mktemp -d)
    curl -fsSL -o "$src/openssl.conda" "https://conda.anaconda.org/conda-forge/$package"
    echo "$sha256  $src/openssl.conda" | sha256sum -c -
    # A .conda file is a zip archive holding the package files as a zstd tarball.
    python3 -I -m zipfile -e "$src/openssl.conda" "$src"
    mkdir -p "$prefix"
    tar --zstd -xf "$src"/pkg-*.tar.zst -C "$prefix"
    rm -rf "$src"
}

install_python() {
    local version=$1 ssl
    [ -d "$(pyenv root)/versions/$version" ] && return
    # These don't support the system's OpenSSL 3.
    if [[ $version == 3.[7-9].* ]]; then
        ssl=1.1.1w
        install_openssl "$ssl"
        local -x CPPFLAGS="-I$openssl_root/$ssl/include"
        local -x LDFLAGS="-L$openssl_root/$ssl/lib -Wl,-rpath,$openssl_root/$ssl/lib"
    fi
    pyenv install "$version"
    PYENV_VERSION=$version pyenv exec python -c 'import ssl; print(ssl.OPENSSL_VERSION)'
}

if [[ $# == 0 ]]; then
    echo "usage: $0 <version>..." >&2
    exit 2
fi

for version; do
    install_python "$version"
done
