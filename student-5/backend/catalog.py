"""Sample men's sneaker catalog used for content-based and collaborative filtering."""

PRODUCT_CATALOG = [
    {
        "product_id": 101,
        "name": "Nike Air Jordan 1 Retro High",
        "brand": "Nike",
        "category": "basketball",
        "price": 149.99,
        "image": "https://cdn.dummyjson.com/product-images/mens-shoes/nike-air-jordan-1-red-and-black/1.webp",
        "tags": ["jordan", "basketball", "street"],
    },
    {
        "product_id": 102,
        "name": "Puma Future Rider Trainers",
        "brand": "Puma",
        "category": "everyday",
        "price": 89.99,
        "image": "https://cdn.dummyjson.com/product-images/mens-shoes/puma-future-rider-trainers/1.webp",
        "tags": ["training", "everyday", "retro"],
    },
    {
        "product_id": 103,
        "name": "Nike Baseball Cleats",
        "brand": "Nike",
        "category": "active",
        "price": 79.99,
        "image": "https://cdn.dummyjson.com/product-images/mens-shoes/nike-baseball-cleats/1.webp",
        "tags": ["sport", "cleats", "active"],
    },
    {
        "product_id": 104,
        "name": "New Balance 550",
        "brand": "New Balance",
        "category": "everyday",
        "price": 110.00,
        "image": "https://image.goat.com/transform/v1/attachments/product_template_pictures/images/091/190/375/original/1229872_00.png.png",
        "tags": ["lifestyle", "everyday", "classic"],
    },
    {
        "product_id": 105,
        "name": "Sports Sneakers Off White Red",
        "brand": "Off White",
        "category": "street",
        "price": 119.99,
        "image": "https://cdn.dummyjson.com/product-images/mens-shoes/sports-sneakers-off-white-red/1.webp",
        "tags": ["street", "designer", "hype"],
    },
    {
        "product_id": 106,
        "name": "Adidas Yeezy Boost 350 V2",
        "brand": "Adidas",
        "category": "running",
        "price": 129.99,
        "image": "https://image.goat.com/transform/v1/attachments/product_template_pictures/images/075/775/173/original/924555_00.png.png",
        "tags": ["running", "active", "boost"],
    },
    {
        "product_id": 107,
        "name": "Jordan 4 Retro Military Black",
        "brand": "Jordan",
        "category": "basketball",
        "price": 210.00,
        "image": "https://image.goat.com/transform/v1/attachments/product_template_pictures/images/071/333/263/original/895934_00.png.png",
        "tags": ["jordan", "basketball", "street"],
    },
    {
        "product_id": 108,
        "name": "Nike Air Force 1 Low",
        "brand": "Nike",
        "category": "street",
        "price": 99.99,
        "image": "https://image.goat.com/transform/v1/attachments/product_template_pictures/images/048/340/054/original/712867_00.png.png",
        "tags": ["street", "everyday", "classic"],
    },
]


def get_product(product_id):
    for product in PRODUCT_CATALOG:
        if product["product_id"] == product_id:
            return product
    return None


def get_all_products():
    return PRODUCT_CATALOG
