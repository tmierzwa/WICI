# Wskazówki dla Claude Code

- Atrybucja: w commitach tylko `Co-Authored-By: Claude …`, w opisach PR tylko „🤖 Generated with [Claude Code](https://claude.com/claude-code)”. Nie dodawać linku do sesji (`claude.ai/code/session_…`) ani linii `Claude-Session:` w commitach, PR i komentarzach.
- Materiały prywatne: działanie, komunikacja, plany, finanse i kontakty fundacji nigdy nie trafiają do tego repozytorium, issue, opisów PR ani komentarzy. Sesja w tym repozytorium nie czyta `../fundacja/`; pracę nad fundacją prowadzi sesja otwarta w `fundacja/`, a tekst do publikacji przenosi właściciel. Gdy `tools/check_private.py` zablokuje commit lub push, nie omijaj go (`--no-verify`), nie uruchamiaj go z `--show` i zgłoś blokadę właścicielowi ([CONTRIBUTING.md](CONTRIBUTING.md#materiały-prywatne)).
