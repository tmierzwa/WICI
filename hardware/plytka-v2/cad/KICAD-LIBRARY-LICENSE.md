### KiCad Libraries License

The KiCad libraries are licensed under the [Creative Commons CC-BY-SA 4.0 License](https://creativecommons.org/licenses/by-sa/4.0/legalcode), with the following exception:

---------

_To the extent that the creation of electronic designs that use 'Licensed Material' can be considered to be 'Adapted Material', then the copyright holder waives article 3 of the license with respect to these designs and any generated files which use data provided as part of the 'Licensed Material'._

---------

You can read more about KiCad library licensing [here](http://kicad.org/libraries/license).

**What does this mean?**

KiCad libraries are licensed in such a way to ensure free use of library data for commercial, closed, and non-commercial projects without restriction. KiCad does not wish to exert any control over designs produced using the library data, or force users to reveal proprietary information contained in their designs. Neither do we wish to force users to attribute the KiCad libraries _within their design_.

Use of the library data in a project does not (by itself) require that the design or any files generated from the design are licensed under the CC-BY-SA 4.0 License. You are free to use the library data in your own projects without the obligation to share your project files under this or any other license agreement.

However, if you wish to redistribute the KiCad libraries, or parts thereof (including in modified form) as a collection then the exception above does not apply. Redistributed library collections must be shared under the same license agreement. Under these circumstances, the libraries must also retain attribution information, including the license documents which are distributed with the library files.

----------------------

**Warranty**

The KiCad libraries are provided in the hope that they will be useful, but are provided without warranty of any kind, express or implied.

The KiCad libraries are compiled by the KiCad community - if you find an error in the library data, please help the community and contribute a fix!
Project provenance: `cad/symbols/` holds the subset of KiCad 10.0.6 symbols used by the schematic, written by `tools/make_schematic.py`; `WICI.kicad_sym` there is project-authored. `cad/fp-lib-table` points to the footprint libraries of the KiCad 10.0.6 installation; nothing is copied until the PCB exists. In `cad/footprints/WICI.pretty`, `LTC3115-1_FE20_CA` is taken from the JLC test board and derives from the KiCad `Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm` with an added exposed pad, so it keeps the library terms above; `L_Bourns_SRP1038A` and `Toggle_ESwitch_100SP1T1B4M2QE` are project-authored. The library terms above are unchanged.
