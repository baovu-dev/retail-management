"""Each feature registers one evidence provider here."""
from evidence import student1_reviews

PROVIDERS = {
    "student-1": student1_reviews.collect,
}