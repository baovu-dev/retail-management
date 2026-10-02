# KICKLAB Orders: cancellation behavior

The Orders screen offers Cancel for orders whose status is not CANCELLED.
Customers and staff confirm a dialog before cancellation. The current API sets
an existing order to CANCELLED regardless of its previous status, including
CONFIRMED. It preserves the order and its items instead of deleting them.
Cancelling an unknown order returns Order not found. No refund amount or
refund processing is implemented by this operation.

Source: student-4/database/app.py; student-4/frontend/templates/index.html; student-4/frontend/templates/admin.html.
