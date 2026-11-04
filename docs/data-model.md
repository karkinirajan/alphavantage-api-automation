# The data model

## Now

One table, `user`: `id`, `username` (unique, stored in lower case), `email` (unique, lower case), `first_name`,
`last_name`, `password_hash` (scrypt or pbkdf2, from Werkzeug) and `created_at`.

## In the first version

`app/dbs.py` defined 13 tables (the committed database also held a 14th, `stocks`, left over from an earlier
version of the code): `user`, `settings` (profile picture, colour scheme, font), `stocklist`,
`BrentOil`, `Copper`, `Coffee`, `TopGainers`, `TopLosers`, `intraday`, `DailyAdj`, `MonthlyAdj`, `ordertype`
and a purchase-history table. Only `user` was ever read or written by the application. `seed.py`, meant to fill the
stock and price tables, could not run (it opened a dictionary as a file and indexed a list with a string), and the
database that was committed had rows in `user` only.

They describe a stock-trading simulator (a wallet, buying and selling, order types). `docs/erd.png` is the
entity-relationship diagram that came with the project; it is kept as it was. None of it is built: there is no
wallet, no portfolio and no order. If the simulator is still wanted, it starts from that diagram.

The `user` table changed: `fname` and `lname` are now `first_name` and `last_name`, and `wallet_funds` is gone.
The database file of the first version is therefore not compatible and was not migrated.
