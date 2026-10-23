"""Release 2 post-commit endpoint tests.

These run against the live Student 3
backend started through Docker Compose.

Two backend endpoint functions are tested:

1. get_customer
   GET /customers/<customer_id>

2. get_all_customers
   GET /customers
"""

import os

import requests


BASE_URL = os.getenv(
    "CUSTOMER_API_URL",
    "http://localhost:5003",
)

TIMEOUT = 10


# ---------------------------------------------------------
# Endpoint 1:
# get_customer
# GET /customers/<customer_id>
# ---------------------------------------------------------


def test_get_customer_returns_safe_customer_record():

    response = requests.get(
        f"{BASE_URL}/customers/1",
        timeout=TIMEOUT,
    )

    assert (
        response.status_code
        == 200
    )

    customer = response.json()

    assert (
        customer[
            "customer_id"
        ]
        == 1
    )

    assert customer[
        "first_name"
    ]

    assert customer[
        "last_name"
    ]

    assert customer[
        "email"
    ]

    assert (
        "password_hash"
        not in customer
    )


def test_get_customer_unknown_id_returns_404():

    response = requests.get(
        f"{BASE_URL}/customers/999999",
        timeout=TIMEOUT,
    )

    assert (
        response.status_code
        == 404
    )

    assert (
        response
        .json()
        .get("error")
        == "Customer not found"
    )


# ---------------------------------------------------------
# Endpoint 2:
# get_all_customers
# GET /customers
# ---------------------------------------------------------


def test_get_all_customers_returns_seeded_records():

    response = requests.get(
        f"{BASE_URL}/customers",
        timeout=TIMEOUT,
    )

    assert (
        response.status_code
        == 200
    )

    customers = response.json()

    assert isinstance(
        customers,
        list,
    )

    assert len(
        customers
    ) >= 10

    assert (
        customers[0][
            "customer_id"
        ]
        == 1
    )


def test_get_all_customers_never_exposes_password_hashes():

    response = requests.get(
        f"{BASE_URL}/customers",
        timeout=TIMEOUT,
    )

    assert (
        response.status_code
        == 200
    )

    customers = response.json()

    assert all(
        "password_hash"
        not in customer
        for customer
        in customers
    )