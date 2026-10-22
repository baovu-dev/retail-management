"""The Product evidence provider must supply readable source text to agents."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[2] / "ai-services/multi-agent-server/evidence/student2_products.py"
spec = importlib.util.spec_from_file_location("student2_products_evidence", SOURCE)
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


def test_product_record_text_is_one_string():
    product = {"product_id": 103, "name": "Test Sneaker", "category": "Shoes", "brand": "KICKLAB",
               "price": 99, "status": "active", "description": "A test product"}
    with patch.object(provider.requests, "get", return_value=Mock(**{"json.return_value": product})) as get:
        result = provider.collect("review product 103")
    assert result["status"] == "success"
    assert result["scope"] == "product 103"
    assert result["records"][0]["id"] == "product 103"
    assert isinstance(result["records"][0]["text"], str)
    for value in ("Test Sneaker", "Shoes", "KICKLAB", "99", "active", "A test product"):
        assert value in result["records"][0]["text"]
    get.assert_called_once_with(f"{provider.PRODUCTS_DB_API}/products/103", timeout=provider.TIMEOUT)
