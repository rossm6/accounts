# Accounts

Accounts is an open source accountancy web app, on which you can build.

### Try It Out For Yourself
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy)

### Includes

1. Cash Book ledger
2. Nominal ledger
3. Purchase ledger
4. Sales ledger
5. Vat ledger
6. Users
7. Groups
8. Permissions
9. Audit
10. Transaction locking (transactions can only be posted into the previous, current and next period)
11. Financial years consisting of accounting periods
12. Trial Balance report
13. Aged balance reports
14. Dashboard

### Nice Features -

1. Matching - Purchase and Sales transactions can be matched.  This way a user can see which transactions are matched to each other.  For example what a payment is paying.

2. Financial years can be adjusted retrospectively.  Finalised financial years can also be rolled back.

### Essential Features It Lacks -

1. While sales transactions can be entered, there are no documents produced (e.g. invoice and credit note templates)
2. Customer Statements
3. Supplier remittances
4. Supplier payment run which generates a bank file
5. Discounts

### Recommended Features It Lacks -

1. Purchase ordering.

### Considerations -

1. Auditing is provided with the help of the simplehistory package.  For performance reasons
it saves the model state with EVERY save.  A periodic task which cleans up the unnecessary duplicate
model states is surely recommended.  The package already provides the command.  See https://django-simple-history.readthedocs.io/en/latest/utils.html

2. Transactions CAN be voided.  This means the vat, cash book and nominals transactions are deleted but enough is left untouched so that a new function which undoes the void could easily be implemented.

3. Single objects like cash books, nominals, vat codes, users, groups etc cannot be deleted.  Either allow the user to delete the object and check all the consequences; or add an "active"
flag to the model and use this to hide the object from the standard lists.  Should you opt to allow nominals to be deleted make sure the user cannot delete the purchase, sales, vat and suspense control accounts, and the retained earnings account, because these accounts are assumed to always exist in the software.

### Browser Support -

All UI testing has so far been manual and limited to the latest version of Chrome and Firefox,
and to a far lesser extent Edge.  I'm not supporting IE11 because it's a nightmare.  Safari hasn't
been tested but should be supported.

# Technology Stack
- Python 3.8.x
- Django Web Framework
- PostgreSQL
- Docker (local development)
- docker-compose (local development)
- WhiteNoise
- Bootstrap 4
- jQuery 3
- Heroku (production)