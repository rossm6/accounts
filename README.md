# Accounts
General Ledger Accountancy CRUD system


### Still in development

Out of the box this software gives you the following ledgers -

  1. Purchase
  2. Sales
  3. Cash Book
  4. Nominal
  
All transactions can be -

  1. Created
  2. Edited
  3. Read (in a list or individually)
  4. Voided (rather than delete transactions the software will change the status to 'void'.  Such transactions are then automatically
  invisible from the usual views).
  
Transactions on the purchase and sales ledger can also be "matched".  This is a nice feature, which, surprisingly, Xero, a major accountancy providers, appears to lack.
This way the user can see which transactions are matched to each other.  For example which invoices a payment is matched to i.e. which invoices the payment pays.
Matches can also be edited or removed altogether.

  
## Todo

  1. REST API.  I've made a start at creating custom Django REST views for the nominal ledger only.  Before going any further I wanted to see how tricky it would be to
  create the OpenAPI / Swagger documentation for the API.
  2. Make the system more configurable.  For example at the moment there is no discount field available for any transaction.
  Now that the basics have created I will extend the software so that new fields, the most obvious being "discount", can be added easily.  
  As it stands any developer using this software would have to spend quite a bit of time reading through the code to see how the software works.  
