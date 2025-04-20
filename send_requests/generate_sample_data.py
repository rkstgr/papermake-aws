import random
import json
import datetime
from faker import Faker
import uuid
from decimal import Decimal, ROUND_HALF_UP

# Initialize Faker for generating realistic personal data
fake = Faker("de_DE")  # German locale


def generate_company():
    """For now, we use a fixed company"""

    return {
        "logo": None,
        "name": "MoneyBank",
        "address": "Kantstraße 123, 10623 Berlin, Germany",
        "phone": "+49 30 8765 4321",
    }


def generate_customer(customer_id=None):
    """Generate a random customer, or a specific one based on customer_id"""
    # If customer_id is provided, seed the random generator to get consistent results
    if customer_id is not None:
        random.seed(customer_id)
        fake.seed_instance(customer_id)

    first_name = fake.first_name()
    last_name = fake.last_name()
    email = f"{first_name[0].lower()}.{last_name.lower()}@{fake.free_email_domain()}"

    # Reset the random seed if we set it
    if customer_id is not None:
        random.seed()
        fake.seed_instance()

    return {
        "name": f"{first_name} {last_name}",
        "address": f"{fake.street_address()}, {fake.postcode()} {fake.city()}, Germany",
        "email": email,
    }


def generate_transaction():
    """Generate transaction details"""
    # Generate a date in the past month
    date = datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 30))
    date_str = date.strftime("%d %B %Y")

    # Generate reference number
    ref_prefix = "MB-TR-"
    ref_number = f"{ref_prefix}{date.strftime('%y%m%d')}{random.randint(10, 99)}"

    # Generate client code
    client_prefix = ref_prefix.replace("-TR-", "-C")
    client_code = f"{client_prefix}{random.randint(10000, 99999)}"

    return {
        "date": date_str,
        "reference": ref_number,
        "currency": "EUR",
        "client_code": client_code,
        "commission_percent": f"{random.randint(5, 20) / 100:.2f}",
        "minimum_fee": f"{random.randint(495, 1295) / 100:.2f}",
    }


def format_amount(amount):
    """Format amount with thousand separators"""
    if isinstance(amount, str) and amount == "":
        return ""

    # Convert to Decimal for proper rounding
    decimal_amount = Decimal(str(amount))
    # Round to 2 decimal places
    rounded = decimal_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Format with thousand separators
    formatted = f"{rounded:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return formatted


def generate_stock_details(num_trades=4):
    """Generate stock transaction details"""
    german_stocks = [
        {"symbol": "SIE.DE", "name": "Siemens AG", "price_range": (150, 200)},
        {"symbol": "SAP.DE", "name": "SAP SE", "price_range": (180, 220)},
        {"symbol": "BAS.DE", "name": "BASF SE", "price_range": (40, 60)},
        {"symbol": "DTE.DE", "name": "Deutsche Telekom AG", "price_range": (18, 25)},
        {
            "symbol": "BMW.DE",
            "name": "Bayerische Motoren Werke AG",
            "price_range": (80, 100),
        },
        {"symbol": "ALV.DE", "name": "Allianz SE", "price_range": (200, 250)},
        {"symbol": "BAYN.DE", "name": "Bayer AG", "price_range": (30, 50)},
        {"symbol": "DAI.DE", "name": "Daimler AG", "price_range": (60, 80)},
        {"symbol": "DBK.DE", "name": "Deutsche Bank AG", "price_range": (10, 15)},
        {"symbol": "DPW.DE", "name": "Deutsche Post AG", "price_range": (40, 50)},
    ]

    details = []
    total_buy = Decimal("0")
    total_sell = Decimal("0")

    # Randomly select stocks without replacement
    selected_stocks = random.sample(german_stocks, min(num_trades, len(german_stocks)))

    for stock in selected_stocks:
        # Randomly decide if this is a buy or sell
        is_buy = random.choice([True, False])

        lots = random.randint(1, 3)
        shares = random.randint(1, 5) * 25  # 25, 50, 75, 100, 125
        price = Decimal(
            str(random.uniform(stock["price_range"][0], stock["price_range"][1]))
        )
        amount = price * Decimal(str(shares))

        # Format as required
        buy_amount = "" if not is_buy else format_amount(amount)
        sell_amount = "" if is_buy else format_amount(amount)

        # Update totals
        if is_buy:
            total_buy += amount
        else:
            total_sell += amount

        details.append(
            {
                "stock": f"{stock['name']} ({stock['symbol']})",
                "lots": str(lots),
                "shares": str(shares),
                "price": format_amount(price),
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
            }
        )

    # Calculate the gross amount
    gross_amount = total_sell - total_buy

    return details, gross_amount, total_buy, total_sell


def generate_summary(gross_amount, commission_percent, minimum_fee):
    """Generate financial summary based on transaction details"""
    # Convert commission_percent to a decimal
    commission_rate = Decimal(commission_percent)
    min_fee = Decimal(minimum_fee)

    # Calculate brokerage fee (commission based on gross amount)
    brokerage_fee = Decimal(str(abs(gross_amount))) * commission_rate / Decimal("100")
    # Apply minimum fee if necessary
    if brokerage_fee < min_fee:
        brokerage_fee = min_fee

    # VAT on brokerage fee (19% in Germany)
    vat_rate = Decimal("0.19")
    vat_brokerage_fee = brokerage_fee * vat_rate

    # Total charges
    total_charges = brokerage_fee + vat_brokerage_fee

    # Sales tax (assuming 0 for this example)
    sales_tax = Decimal("0.00")

    # Withholding tax (approximately 25% of gains in Germany)
    withholding_tax = Decimal("0.00")
    if gross_amount > 0:  # Only apply on profits
        withholding_tax = gross_amount * Decimal("0.25")

    return (
        {
            "gross_amount": format_amount(gross_amount),
            "brokerage_fee": format_amount(brokerage_fee),
            "vat_brokerage_fee": format_amount(vat_brokerage_fee),
            "total_charges": format_amount(total_charges),
            "sales_tax": format_amount(sales_tax),
            "withholding_tax": format_amount(withholding_tax),
        },
        total_charges,
        withholding_tax,
    )


def generate_trade_confirmation(customer_id=None, confirmation_id=None):
    """Generate a complete trade confirmation"""
    # Use the seed for consistent but different results
    if confirmation_id is not None:
        random.seed(confirmation_id)

    company = generate_company()
    customer = generate_customer(customer_id)
    transaction = generate_transaction()

    # Generate stock details and get the gross amount
    details, gross_amount, total_buy, total_sell = generate_stock_details()

    # Generate summary
    summary, total_charges, withholding_tax = generate_summary(
        gross_amount, transaction["commission_percent"], transaction["minimum_fee"]
    )

    # Calculate total amount
    if gross_amount > 0:
        # If selling more than buying, subtract fees and taxes
        total_amount = gross_amount - total_charges - withholding_tax
    else:
        # If buying more than selling, add fees
        total_amount = gross_amount - total_charges

    # Due amount is the same as total amount in this example
    due_amount = total_amount

    # Reset the random seed if we set it
    if confirmation_id is not None:
        random.seed()

    return {
        "company": company,
        "customer": customer,
        "transaction": transaction,
        "details": details,
        "summary": summary,
        "total_amount": format_amount(total_amount),
        "due_amount": format_amount(due_amount),
    }


def generate_multiple_confirmations(customer_id=None, count=5):
    """Generate multiple trade confirmations for a customer"""
    return [
        generate_trade_confirmation(customer_id, f"{customer_id}-{i}")
        for i in range(count)
    ]


def generate_for_multiple_customers(num_customers=5, confirmations_per_customer=5):
    """Generate confirmations for multiple customers"""
    all_confirmations = []
    for i in range(num_customers):
        customer_id = f"customer-{i}"
        customer_confirmations = generate_multiple_confirmations(
            customer_id, confirmations_per_customer
        )
        all_confirmations.extend(customer_confirmations)
    return all_confirmations


# Generate a single confirmation

if __name__ == "__main__":
    confirmation = generate_trade_confirmation()
    print(json.dumps(confirmation, indent=2, ensure_ascii=False))

    with open("sample_trade_data.json", "w") as f:
        json.dump(confirmation, f, indent=2, ensure_ascii=False)
