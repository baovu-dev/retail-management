# KICKLAB Review Policy

Only verified purchases can be reviewed. A customer can review a product only if
they have a CONFIRMED order containing that product. The Reviews backend checks
this by calling the Order Management API before accepting a review.

Each customer can leave one review per product. A second review for the same
product is rejected with the message "You've already reviewed this product."

Each review has a rating from 1 to 5 and an optional written comment.

Staff can search reviews by product ID and delete reviews from the staff
Reviews page. Flagged reviews are listed on the moderation page at /moderate.