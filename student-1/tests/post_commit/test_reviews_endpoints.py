"""Post-commit endpoint tests for the Student 1 Reviews & Ratings backend.

These run against the live backend started by docker compose in student-1-ci.yml.
They cover two endpoint functions:
  1. list_reviews      GET /reviews/<product_id>
  2. get_review_stats  GET /reviews/stats
"""
import os

import requests

BASE_URL = os.getenv("REVIEWS_API_URL", "http://localhost:5001")
TIMEOUT = 10


# Endpoint 1: list_reviews (GET /reviews/<product_id>)

def test_list_reviews_returns_reviews_for_product():
    response = requests.get(f"{BASE_URL}/reviews/101", timeout=TIMEOUT)
    assert response.status_code == 200
    reviews = response.json()
    assert isinstance(reviews, list)
    assert len(reviews) > 0
    for review in reviews:
        assert review["product_id"] == 101
        assert 1 <= review["rating"] <= 5


def test_list_reviews_unknown_product_returns_empty_list():
    response = requests.get(f"{BASE_URL}/reviews/999999", timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json() == []


def test_list_reviews_rejects_non_numeric_product_id():
    response = requests.get(f"{BASE_URL}/reviews/abc", timeout=TIMEOUT)
    assert response.status_code == 404


# Endpoint 2: get_review_stats (GET /reviews/stats)

def test_review_stats_returns_expected_fields():
    response = requests.get(f"{BASE_URL}/reviews/stats", timeout=TIMEOUT)
    assert response.status_code == 200
    stats = response.json()
    assert {"total_reviews", "average_rating", "flagged_count"} <= set(stats)


def test_review_stats_values_are_consistent():
    stats = requests.get(f"{BASE_URL}/reviews/stats", timeout=TIMEOUT).json()
    assert stats["total_reviews"] > 0
    assert 0 <= stats["flagged_count"] <= stats["total_reviews"]
    assert 1 <= stats["average_rating"] <= 5