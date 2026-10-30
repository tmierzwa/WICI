# SPDX-License-Identifier: MIT
# runtime/kopia.sh: wspólna część START-LINUX.sh i START-MAC (wczytywana przez „.”, więc nie musi być
# wykonywalna na pamięci FAT). Kopiuje środowisko Pythona swojego systemu, wspólną bibliotekę i aplikację
# z pamięci do katalogu podręcznego użytkownika, żeby wyjęcie pamięci nie zamykało aplikacji
# (docs/spec/oprogramowanie.md, „Pakiet USB”). Katalog kopii nosi wersję i sumę build-manifest.json:
# inna budowa dostaje własny i nie rusza kopii, z której może działać uruchomiona aplikacja. Kopia
# powstaje w katalogu tymczasowym, manifest trafia do niej na końcu, a gotowa dostaje swoją nazwę
# jednym przemianowaniem, więc przerwane kopiowanie nigdy nie wygląda na pełną kopię.

# wici_copy <katalog pamięci> <środowisko> <katalog podręczny>
# Ustawia root na kopię na dysku; gdy kopiowanie się nie uda, root wskazuje pamięć i wynik to 1.
wici_copy() {
  src=$1 rt=$2 base=$3
  version=$(cat "$src/runtime/VERSION" 2>/dev/null || echo unknown)
  build=$(cksum < "$src/build-manifest.json" 2>/dev/null | cut -d' ' -f1)
  dest="$base/$version-${build:-0}"
  root=$src
  if ! cmp -s "$src/build-manifest.json" "$dest/build-manifest.json"; then
    tmp="$dest.tmp.$$"
    rm -rf "$tmp"
    mkdir -p "$tmp/runtime" "$tmp/app" &&
      cp -R "$src/runtime/$rt" "$src/runtime/python314.zip" "$src/runtime/VERSION" "$tmp/runtime/" &&
      cp "$src/app/wici.pyz" "$tmp/app/" &&
      chmod -R u+rwX "$tmp" && chmod +x "$tmp/runtime/$rt/bin/python3.14" &&
      cp "$src/build-manifest.json" "$tmp/" || { rm -rf "$tmp"; return 1; }
    if ! cmp -s "$src/build-manifest.json" "$dest/build-manifest.json"; then
      rm -rf "$dest"   # bez zgodnego manifestu to nie jest pełna kopia tej budowy, więc nic z niej nie działa
      mv "$tmp" "$dest" 2>/dev/null
    fi
    rm -rf "$tmp" "$dest/${tmp##*/}"   # inny START zdążył pierwszy: zostaje jego kopia
    cmp -s "$src/build-manifest.json" "$dest/build-manifest.json" || return 1
  fi
  root=$dest
}
