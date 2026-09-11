# e11-calc

Conductor sizing and overcurrent protection for small-craft DC circuits,
computed from ABYC E-11 tables **that you supply**. A dependency-free
TypeScript/JavaScript library (plain ESM) that drops into any web app.

It is the calculation engine behind the *Circuit: conductor and protection*
calculator in Marine Electrical Document Intelligence, and it ships so the
same calculation can run in another web app of yours.

## The rule it rests on

**Nothing in this code is a value from the standard.** The tables come from
the owner's own copy of ABYC E-11, one JSON file per printed table, each
value with the page it was copied from, each table confirmed against that
page by a person before the engine will use it. A case the tables do not
cover is a **blank**: the result says what is missing, cites the page the
table stops at, and names the value you can type instead. A value you type
is reported as *yours*, never as the standard's.

Two things are not table values and are labelled as such in every result:
unit conversions (circular mils to mm²) and industry lists (standard fuse
sizes, standard metric conductor sizes, how load types behave and what
protects them - `profiles/device_profiles.json`).

## Use

```js
import { loadTables, loadCheatSheet, sizeCircuit } from "e11-calc";

// In a browser: import or fetch the JSON files yourself.
const tables = loadTables({
  "constants.json": await (await fetch("tables/constants.json")).json(),
  "circular_mils.json": await (await fetch("tables/circular_mils.json")).json(),
  // ... one entry per file in tables/
});
const sheet = loadCheatSheet(await (await fetch("cheatsheet/cheatsheet.json")).json());

const result = sizeCircuit(
  {
    system_voltage: 24,          // any nominal voltage
    current: 30,                 // A, continuous
    length: 6, length_unit: "m", // one way, source to load
    max_drop_percent: 3,         // 3 or 10 use the printed grid too; any other value, the formula only
    insulation_rating_c: 105,
    engine_space: false,
    bundled_conductors: 2,       // current-carrying conductors bundled together, this circuit's two included
    load_type: "inverter",       // a key of DEVICE_PROFILES
    short_circuit_a: 5000,       // optional, from the battery datasheet
  },
  tables,
  {},                            // your own values in answer to blanks: { ampacity_a, bundling_factor, k, short_circuit_a }
  sheet,                         // optional: the reminders that apply come back in result.reminders
);

result.conductor.size_awg;       // "4", or null with result.blanks explaining
result.conductor.parallel;       // 1, or how many conductors in parallel
result.conductor.size_mm2;       // the same area in mm² (unit conversion)
result.protection.fuse_a;        // never above the conductor's derated ampacity
result.blanks;                   // [{ field, reason, ask: { field: "own.…", unit, prompt } }]
result.steps;                    // the working, with a page for every number
```

In Node, `import { loadTablesFromDir } from "e11-calc/node"` reads a folder.

## The procedure

1. **Voltage drop.** `CM = K × I × L / E`, with `L` as the constants table's
   page defines it (round trip or one way), for any voltage. The smallest
   listed size with at least that area. At 12 V with a 3 % or 10 % limit the
   printed grid is read too; if it asks for more, it governs.
2. **Ampacity.** The allowable-current table for inside or outside engine
   spaces, the column for the insulation rating, times the bundling factor
   for the number of conductors. The smallest size that carries the current.
3. **The larger wins.** `governed_by` says which. When no single listed size
   meets both, the fewest conductors of the smallest size in parallel that do.
4. **Protection.** At least the load times its load-type factor (or the
   maker's stated rating), rounded up to a standard size, never above the
   conductor's derated ampacity. The interrupting rating of the fuse must
   exceed the source's short-circuit current, which you type from the
   battery datasheet; the fuse classes you have entered are listed.
5. **Reminders.** Cheat-sheet entries whose tags fit the situation
   (`always`, `engine_space`, `bundled`, `parallel`, the load type).

## Files

- `tables/` - the confirmed tables. Empty until the owner confirms them in
  the desktop app (Calculators → ABYC E-11 reference → Download for the web
  app) and copies them here. `schema/e11-table.schema.json` describes the
  shape; `tests/fixtures/tables/` is a synthetic example with made-up
  numbers that the loader refuses outside a test.
- `cheatsheet/` - `cheatsheet.json` plus the rendered `.md` and `.html`
  (`npm run cheatsheet`).
- `profiles/device_profiles.json` - the industry guidance, the one copy the
  TypeScript and Python implementations are both tested against.
- `tests/test-vectors.json` - the cases both implementations must agree on.

## Publishing

The tables and the cheat sheet are copied from a paid standard: for private
use only. To publish a web app built on this library, delete `tables/` and
`cheatsheet/`; the engine then answers every case with a blank that says the
tables are not installed.

```
npm install
npm test          # builds dist/ and runs node --test
```
