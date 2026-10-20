"""Post-commit endpoint tests for the Student 5 recommendation backend.

These run against the live backend started by docker compose in student-5-ci.yml.
They cover two endpoint functions:
  1. get_product_recommendations  GET /api/recommendations/product/<product_id>
  2. recommendation_metrics       GET /api/recommendations/metrics
"""
import os

import requests

BASE_URL = os.getenv("RECOMMENDATIONS_API_URL", "http://localhost:5005")
TIMEOUT = 10


# Endpoint 1: get_product_recommendations (GET /api/recommendations/product/<product_id>)

def test_product_recommendations_returns_similar_products():
    response = requests.get(f"{BASE_URL}/api/recommendations/product/101", timeout=TIMEOUT)
    assert response.status_code == 200
    recommendations = response.json()
    assert isinstance(recommendations, list)
    assert len(recommendations) > 0
    for item in recommendations:
        assert item["recommended_product_id"] != 101
        assert item["product"]["product_id"] == item["recommended_product_id"]
        assert item["recommendation_score"] > 0


def test_product_recommendations_unknown_product_returns_empty_list():
    response = requests.get(f"{BASE_URL}/api/recommendations/product/999999", timeout=TIMEOUT)
    assert response.status_code == 200
    assert response.json() == []


# Endpoint 2: recommendation_metrics (GET /api/recommendations/metrics)

def test_recommendation_metrics_returns_expected_fields():
    response = requests.get(f"{BASE_URL}/api/recommendations/metrics", timeout=TIMEOUT)
    assert response.status_code == 200
    metrics = response.json()
    assert {
        "total_recommendations",
        "total_feedback",
        "helpful_rate_percent",
    } <= set(metrics)


def test_recommendation_metrics_counts_are_consistent():
    metrics = requests.get(f"{BASE_URL}/api/recommendations/metrics", timeout=TIMEOUT).json()
    assert metrics["total_recommendations"] >= 0
    assert metrics["total_feedback"] >= 0
    assert 0 <= metrics["helpful_rate_percent"] <= 100
