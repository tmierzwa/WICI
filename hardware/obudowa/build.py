# SPDX-License-Identifier: MIT
"""Entry point of the enclosure generator; refuses to build while measurements are missing.

Geometry (STEP/STL, drill template 1:1) is written only after the fit check fills every
value in zalozenia.MEASUREMENTS. Until then the script lists what is missing and exits 2,
so no enclosure part is designed from guessed heights.
"""
import sys

from zalozenia import MEASUREMENTS, missing_measurements


def main() -> int:
    missing = missing_measurements()
    if missing:
        print("Obudowa nie jest generowana: brak pomiarów z przymiarki.")
        for name in missing:
            description, source, _ = MEASUREMENTS[name]
            print(f"- {name}: {description} ({source})")
        return 2
    print("Wszystkie pomiary są wpisane. Generator geometrii (build123d) dopisuje się po przymiarce.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
