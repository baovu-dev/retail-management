"""Each feature registers one evidence provider here."""
from evidence import student1_reviews, student3_customers, student5_recommendations

PROVIDERS = {
    "student-1": student1_reviews.collect,
    "student-3": student3_customers.collect,
    "student-5": student5_recommendations.collect,
}