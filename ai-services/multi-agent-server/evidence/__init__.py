"""Each feature registers one evidence provider here."""
from evidence import student1_reviews, student2_products, student4_orders, student5_recommendations

PROVIDERS = {
    "student-1": student1_reviews.collect,
    "student-2": student2_products.collect,
    "student-4": student4_orders.collect,
    "student-5": student5_recommendations.collect,
}
