# Confirmed tables go here

One JSON file per printed table of the owner's copy of ABYC E-11, in the
shape described by `../schema/e11-table.schema.json`. The loader refuses a
file without `source.page`, a row without `page`, and anything whose
`status` is not `confirmed`. The three catalog tables (`cable_dimensions`,
`heat_shrink`, `lugs`) are typed from the owner's cable, tubing and lug
catalogs instead; they name the catalog in `source.document` and their
pages are optional.

This folder is empty until the owner has imported, corrected and confirmed
each table in the desktop app (Calculators → ABYC E-11 reference) and copied
the download here. The desktop app itself reads the confirmed tables from its
own data folder first, then from here.

Do not type values into these files from memory. That is the one thing this
library exists to prevent.
