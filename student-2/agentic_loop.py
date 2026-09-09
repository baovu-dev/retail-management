import requests

PRODUCT_API = "http://localhost:5002"

def plan():
    print("\n" + "=" * 60)
    print("PLAN")
    print("=" * 60)

    plan_data = {
        "goal": "Validate the Product Management microservice",
        "checks": [
            "Check that the Product API is available",
            "Check that products can be retrieved",
            "Check that product data contains required fields",
            "Check that the AI description endpoint is available"
        ]
    }

    print("Goal:", plan_data["goal"])

    for check in plan_data["checks"]:
        print("-", check)

    return plan_data

def act():
    print("\n" + "=" * 60)
    print("ACT")
    print("=" * 60)

    results = {}

    try:
        response = requests.get(f"{PRODUCT_API}/products", timeout=5)
        response.raise_for_status()

        products = response.json()

        results["api_available"] = True
        results["products"] = products

        print("Product API request completed successfully.")

    except requests.RequestException as error:
        results["api_available"] = False
        results["products"] = []
        results["api_error"] = str(error)

        print("Product API request failed:", error)


    products = results.get("products",[])

    if products:
            product_id = products[0].get("product_id")

            try:
                response = requests.post(
                    f"{PRODUCT_API}/products/{product_id}/generate-description",
                    timeout=60
                )
                response.raise_for_status()

                ai_result = response.json()

                results["ai_available"] = True
                results["ai_description"] = ai_result.get("description", "")

                print("AI description request completed successfully.")

            except requests.RequestException as error:
                results["ai_available"] = False
                results["ai_error"] = str(error)

                print("AI description request failed:", error)

    else:
            results["ai_available"] = False
            results["ai_error"] = "No product available for AI validation."

    return results

def observe(results):
        print("\n" + "=" * 60)
        print("OBSERVE")
        print("=" * 60)

        observations = []

        if results.get("api_available"):
            observations.append("PASS: Product API is available.")
        else:
            observations.append("FAIL: Product API is unavailable.")

        products = results.get("products", [])

        if products:
            observations.append(
                f"PASS: Retrieved {len(products)} product record(s)."
            )

            required_fields = {
                "product_id",
                "name",
                "category",
                "price",
                "status"

            }

            missing_fields = required_fields - set(products[0].keys())

            if not missing_fields:
                observations.append(
                    "PASS: Product data contains the required fields."
    
                )
            else:
                observations.append(
                    "FAIL: Missing product fields: "
                    +",".join(sorted(missing_fields))
                )
        else:
            observations.append("FAIL: No products were retrieved.")

        if results.get("ai_available") and results.get("ai_description"):
            observations.append(
                "PASS: AI generated a product description."
            )

        else:
            observations.append(
                "FAIL: AI description generation was not successful."

            )

        for observation in observations:
                print(observation)

        return observations

def adapt(observations):
        print("\n" + "=" * 60)
        print("ADAPT")
        print("=" * 60)

        failures = [
            observation
            for observation in observations
            if observation.startswith("FAIL")
        ]

        if not failures:
            print(
                "No corrective action required."
                "The Product Management workflow passed all validation checks."
        
            )
            print(
                "Recommended next step: continue monitoring API, "
                "database and AI integration through CI/CD."
            )
        else:
            print("The follwing improvements are recommended:")

            for failure in failures:
                print("-", failure)

            print(
                "- Review the affected Product Management service"
                "and repeat the validation loop after correction."
            )

def main():
    print("=" * 60)
    print("STUDENT 2 - PRODUCT MANAGEMENT AGENTIC LOOP")
    print("=" * 60)

    plan()
    results = act()
    observations = observe(results)
    adapt(observations)

    print("\n" + "=" * 60)
    print("AGENTIC LOOP COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
        