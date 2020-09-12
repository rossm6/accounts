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
  
Transactions on the purchase and sales ledger can also be "matched".  This way the user can see which transactions are matched to each other.  
For example which invoices a payment is matched to i.e. the invoices the payment pays. Matches can also be edited or removed altogether.
Surprisingly, Xero, appears to lack this matching feature.

## Todo

  1. REST API
  2. Make the system more configurable
  3. User module with basic user permissions
  4. Audit