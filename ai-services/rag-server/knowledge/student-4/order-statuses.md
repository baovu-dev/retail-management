# KICKLAB Orders: supported statuses

Orders have exactly three supported statuses: PENDING, CONFIRMED and CANCELLED.
A newly created order starts as PENDING. Staff can select Confirm on a PENDING
order to set CONFIRMED. Cancellation sets CANCELLED and keeps the order record.
CONFIRMED does not mean shipped or delivered; no shipping or delivery status
is implemented. The update API accepts only these three status values.

Source: student-4/database/schema.sql; student-4/database/app.py; student-4/frontend/templates/admin.html.
