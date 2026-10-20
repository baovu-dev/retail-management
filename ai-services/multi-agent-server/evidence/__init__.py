"""Each feature registers one evidence provider here."""
from evidence import student1_reviews, student4_orders

PROVIDERS = {
    "student-1": student1_reviews.collect,
    "student-4": student4_orders.collect,
}
