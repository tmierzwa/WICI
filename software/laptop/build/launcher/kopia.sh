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

# wici_runnable <środowisko>: interpreter z kopii, a gdy się tam nie uruchamia (katalog domowy z noexec,
# AppLocker albo antywirus blokujący programy z profilu użytkownika), z pamięci. Wołane po wici_copy;
# ustawia python i root, a przy pracy z pamięci WICI_Z_PAMIECI=1 (aplikacja może wtedy prosić, żeby nie
# wyjmować pamięci). Wynik 1, gdy interpreter nie uruchamia się nigdzie.
wici_runnable() {
  python="$root/runtime/$1/bin/python3.14"
  if [ "$root" != "$src" ] && ! "$python" -c "" 2>/dev/null; then
    root=$src
    python="$root/runtime/$1/bin/python3.14"
  fi
  if [ "$root" = "$src" ]; then
    export WICI_Z_PAMIECI=1
    echo "WICI: aplikacja działa z pamięci, nie wyjmuj jej" >&2
  fi
  "$python" -c "" 2>/dev/null
}
