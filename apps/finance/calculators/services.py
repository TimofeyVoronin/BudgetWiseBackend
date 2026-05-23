from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


CALCULATOR_CREDIT = "credit"
CALCULATOR_MORTGAGE = "mortgage"
CALCULATOR_INSTALLMENT = "installment"
CALCULATOR_DEPOSIT = "deposit"
CALCULATOR_PENSION = "pension"
CALCULATOR_INFLATION = "inflation"

CALCULATOR_IDS = {
    CALCULATOR_CREDIT,
    CALCULATOR_MORTGAGE,
    CALCULATOR_INSTALLMENT,
    CALCULATOR_DEPOSIT,
    CALCULATOR_PENSION,
    CALCULATOR_INFLATION,
}

PAYMENT_ANNUITY = "annuity"
PAYMENT_DIFFERENTIATED = "differentiated"

DEPOSIT_CAPITALIZATION_NONE = "none"
DEPOSIT_CAPITALIZATION_MONTHLY = "monthly"
DEPOSIT_CAPITALIZATION_QUARTERLY = "quarterly"
DEPOSIT_CAPITALIZATION_YEARLY = "yearly"

DEPOSIT_TOP_UP_NONE = "none"
DEPOSIT_TOP_UP_MONTHLY = "monthly"

CARD_ANNUAL_RATE_PCT = Decimal("29.9")
CARD_MIN_PAYMENT_PCT = Decimal("3")
PENSION_PAYOUT_MONTHS = Decimal("240")

MONEY_QUANT = Decimal("0.01")
PERCENT_QUANT = Decimal("0.01")


CALCULATOR_CATALOG: list[dict[str, Any]] = [
    {
        "id": CALCULATOR_CREDIT,
        "title": "Кредит",
        "description": "Рассчитайте ежемесячный платёж и переплату по кредиту",
        "icon": "percent",
        "iconBg": "#F3E8FF",
        "iconColor": "#4F46E5",
        "category": "credit",
        "routeTitle": "Кредитный калькулятор",
        "subtitle": "Рассчитайте ежемесячный платёж и переплату по кредиту",
    },
    {
        "id": CALCULATOR_MORTGAGE,
        "title": "Ипотека",
        "description": "Оцените условия ипотеки и рассчитайте график платежей",
        "icon": "home",
        "iconBg": "#DBEAFE",
        "iconColor": "#2563EB",
        "category": "credit",
        "routeTitle": "Ипотечный калькулятор",
        "subtitle": "Рассчитайте условия и платежи по ипотеке",
    },
    {
        "id": CALCULATOR_INSTALLMENT,
        "title": "Рассрочка",
        "description": "Рассчитайте стоимость покупки и график платежей по рассрочке",
        "icon": "cart",
        "iconBg": "#D1FAE5",
        "iconColor": "#10B981",
        "category": "credit",
        "routeTitle": "Рассрочка",
        "subtitle": "Рассчитайте условия рассрочки и сравните с оплатой кредитной картой",
    },
    {
        "id": CALCULATOR_DEPOSIT,
        "title": "Вклад",
        "description": "Рассчитайте доход по вкладу с учётом процентной ставки",
        "icon": "piggy-bank",
        "iconBg": "#FCE7F3",
        "iconColor": "#EC4899",
        "category": "saving",
        "routeTitle": "Вклад",
        "subtitle": "Рассчитайте доходность вклада с учётом капитализации и пополнения",
    },
    {
        "id": CALCULATOR_PENSION,
        "title": "Пенсия",
        "description": "Оцените будущую пенсию и необходимые накопления",
        "icon": "chess-king",
        "iconBg": "#FFEDD5",
        "iconColor": "#EA580C",
        "category": "pension",
        "routeTitle": "Пенсионный калькулятор",
        "subtitle": "Оцените будущий капитал и размер пенсионных выплат",
    },
    {
        "id": CALCULATOR_INFLATION,
        "title": "Инфляция",
        "description": "Оцените влияние инфляции на ваши сбережения и доходы",
        "icon": "trending-up",
        "iconBg": "#CCFBF1",
        "iconColor": "#0D9488",
        "category": "saving",
        "routeTitle": "Инфляция",
        "subtitle": "Оцените влияние инфляции на покупательную способность сбережений",
    },
]


DEFAULTS_BY_CALCULATOR: dict[str, dict[str, Any]] = {
    CALCULATOR_CREDIT: {
        "amount": 1500000,
        "ratePct": 12.5,
        "termMonths": 36,
        "paymentType": PAYMENT_ANNUITY,
        "issueDate": date.today().isoformat(),
    },
    CALCULATOR_MORTGAGE: {
        "propertyPrice": 6500000,
        "downPaymentPct": 20,
        "ratePct": 8.7,
        "termYears": 20,
        "withInsurance": True,
        "isFamilyMortgage": False,
    },
    CALCULATOR_INSTALLMENT: {
        "price": 89990,
        "termMonths": 12,
        "bankFeePct": 0,
        "downPayment": 0,
        "zeroOverpayment": True,
    },
    CALCULATOR_DEPOSIT: {
        "amount": 500000,
        "ratePct": 16,
        "termMonths": 12,
        "capitalization": DEPOSIT_CAPITALIZATION_MONTHLY,
        "topUp": DEPOSIT_TOP_UP_NONE,
        "monthlyTopUp": 0,
    },
    CALCULATOR_PENSION: {
        "currentAge": 32,
        "retireAge": 65,
        "monthlyContribution": 15000,
        "returnRatePct": 8,
        "inflationPct": 5,
        "initialSaved": 240000,
    },
    CALCULATOR_INFLATION: {
        "amount": 1000000,
        "years": 10,
        "inflationPct": 5,
    },
}


class CalculatorNotFoundError(ValueError):
    pass


def get_calculators_catalog(query: str | None = None) -> list[dict[str, Any]]:
    if not query:
        return CALCULATOR_CATALOG

    normalized_query = query.strip().casefold()
    if not normalized_query:
        return CALCULATOR_CATALOG

    return [
        item
        for item in CALCULATOR_CATALOG
        if normalized_query in item["id"].casefold()
        or normalized_query in item["title"].casefold()
        or normalized_query in item["description"].casefold()
    ]


def get_calculator_defaults(calculator_id: str) -> dict[str, Any]:
    if calculator_id not in DEFAULTS_BY_CALCULATOR:
        raise CalculatorNotFoundError(f"Unsupported calculator: {calculator_id}")

    defaults = DEFAULTS_BY_CALCULATOR[calculator_id].copy()
    if calculator_id == CALCULATOR_CREDIT:
        defaults["issueDate"] = date.today().isoformat()
    return {
        "calculatorId": calculator_id,
        "defaults": defaults,
    }


def calculate_financial_calculator(calculator_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    if calculator_id == CALCULATOR_CREDIT:
        return calculate_credit(payload)
    if calculator_id == CALCULATOR_MORTGAGE:
        return calculate_mortgage(payload)
    if calculator_id == CALCULATOR_INSTALLMENT:
        return calculate_installment(payload)
    if calculator_id == CALCULATOR_DEPOSIT:
        return calculate_deposit(payload)
    if calculator_id == CALCULATOR_PENSION:
        return calculate_pension(payload)
    if calculator_id == CALCULATOR_INFLATION:
        return calculate_inflation(payload)

    raise CalculatorNotFoundError(f"Unsupported calculator: {calculator_id}")


def decimal_value(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def percent(value: Decimal) -> float:
    return float(value.quantize(PERCENT_QUANT, rounding=ROUND_HALF_UP))


def add_months(source_date: date, months: int) -> date:
    month_index = source_date.month - 1 + months
    year = source_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def monthly_rate_from_annual(rate_pct: Any) -> Decimal:
    return decimal_value(rate_pct) / Decimal("100") / Decimal("12")


def build_credit_schedule(
    amount: Decimal,
    annual_rate_pct: Decimal,
    term_months: int,
    payment_type: str,
    start_date: date | None = None,
) -> tuple[list[dict[str, Any]], Decimal, Decimal, Decimal]:
    monthly_rate = monthly_rate_from_annual(annual_rate_pct)
    remaining = amount
    schedule: list[dict[str, Any]] = []

    if payment_type == PAYMENT_ANNUITY:
        if monthly_rate == 0:
            base_payment = amount / Decimal(term_months)
        else:
            factor = (Decimal("1") + monthly_rate) ** term_months
            base_payment = amount * monthly_rate * factor / (factor - Decimal("1"))

        for month in range(1, term_months + 1):
            interest_part = remaining * monthly_rate
            principal_part = base_payment - interest_part
            if month == term_months or principal_part > remaining:
                principal_part = remaining
                current_payment = principal_part + interest_part
            else:
                current_payment = base_payment

            remaining = max(Decimal("0"), remaining - principal_part)
            row = {
                "month": month,
                "payment": money(current_payment),
                "principalPart": money(principal_part),
                "interestPart": money(interest_part),
                "remaining": money(remaining),
            }
            if start_date:
                row["date"] = add_months(start_date, month).isoformat()
            schedule.append(row)
    else:
        principal_part = amount / Decimal(term_months)
        for month in range(1, term_months + 1):
            interest_part = remaining * monthly_rate
            if month == term_months:
                principal_for_month = remaining
            else:
                principal_for_month = min(principal_part, remaining)
            current_payment = principal_for_month + interest_part
            remaining = max(Decimal("0"), remaining - principal_for_month)
            row = {
                "month": month,
                "payment": money(current_payment),
                "principalPart": money(principal_for_month),
                "interestPart": money(interest_part),
                "remaining": money(remaining),
            }
            if start_date:
                row["date"] = add_months(start_date, month).isoformat()
            schedule.append(row)

    total_payment = sum(decimal_value(row["payment"]) for row in schedule)
    overpayment = total_payment - amount
    first_payment = decimal_value(schedule[0]["payment"]) if schedule else Decimal("0")
    last_payment = decimal_value(schedule[-1]["payment"]) if schedule else Decimal("0")
    return schedule, total_payment, first_payment, last_payment if last_payment else first_payment


def calculate_credit(payload: dict[str, Any]) -> dict[str, Any]:
    amount = decimal_value(payload["amount"])
    rate_pct = decimal_value(payload["ratePct"])
    term_months = int(payload["termMonths"])
    payment_type = payload["paymentType"]
    issue_date = payload.get("issueDate")

    schedule, total_payment, first_payment, last_payment = build_credit_schedule(
        amount=amount,
        annual_rate_pct=rate_pct,
        term_months=term_months,
        payment_type=payment_type,
        start_date=issue_date,
    )
    overpayment = total_payment - amount

    return {
        "monthlyPayment": money(first_payment),
        "firstPayment": money(first_payment),
        "lastPayment": money(last_payment),
        "totalPayment": money(total_payment),
        "overpayment": money(overpayment),
        "schedule": schedule,
    }


def calculate_mortgage(payload: dict[str, Any]) -> dict[str, Any]:
    property_price = decimal_value(payload["propertyPrice"])
    down_payment_pct = decimal_value(payload["downPaymentPct"])
    rate_pct = decimal_value(payload["ratePct"])
    term_years = int(payload["termYears"])
    with_insurance = bool(payload.get("withInsurance", False))

    loan_amount = property_price * (Decimal("100") - down_payment_pct) / Decimal("100")
    term_months = term_years * 12
    schedule, base_total_payment, first_payment, _last_payment = build_credit_schedule(
        amount=loan_amount,
        annual_rate_pct=rate_pct,
        term_months=term_months,
        payment_type=PAYMENT_ANNUITY,
    )

    insurance_total = Decimal("0")
    monthly_insurance = Decimal("0")
    if with_insurance:
        insurance_total = loan_amount * Decimal("0.01") * Decimal(term_years)
        monthly_insurance = insurance_total / Decimal(term_months)

    monthly_payment = first_payment + monthly_insurance
    total_payment = base_total_payment + insurance_total
    total_interest = total_payment - loan_amount
    recommended_income = monthly_payment * Decimal("2")

    if total_payment > 0:
        principal_share = loan_amount / total_payment
        interest_share = total_interest / total_payment
    else:
        principal_share = Decimal("0")
        interest_share = Decimal("0")

    return {
        "loanAmount": money(loan_amount),
        "monthlyPayment": money(monthly_payment),
        "recommendedIncome": money(recommended_income),
        "totalPayment": money(total_payment),
        "totalInterest": money(total_interest),
        "principalShare": percent(principal_share),
        "interestShare": percent(interest_share),
    }


def calculate_installment_slice(amount: Decimal, term_months: int, fee_pct: Decimal) -> dict[str, Any]:
    fee = amount * fee_pct / Decimal("100")
    total_to_pay = amount + fee
    monthly_payment = total_to_pay / Decimal(term_months)
    overpayment_pct = Decimal("0") if amount == 0 else fee / amount * Decimal("100")
    return {
        "monthlyPayment": money(monthly_payment),
        "totalToPay": money(total_to_pay),
        "overpayment": money(fee),
        "overpaymentPct": percent(overpayment_pct),
    }


def calculate_installment(payload: dict[str, Any]) -> dict[str, Any]:
    price = decimal_value(payload["price"])
    term_months = int(payload["termMonths"])
    bank_fee_pct = decimal_value(payload["bankFeePct"])
    down_payment = decimal_value(payload.get("downPayment", 0))
    zero_overpayment = bool(payload.get("zeroOverpayment", False))

    financed_amount = price - down_payment
    installment_fee_pct = Decimal("0") if zero_overpayment else bank_fee_pct
    installment = calculate_installment_slice(financed_amount, term_months, installment_fee_pct)

    schedule, card_total, card_first_payment, _last_payment = build_credit_schedule(
        amount=financed_amount,
        annual_rate_pct=CARD_ANNUAL_RATE_PCT,
        term_months=term_months,
        payment_type=PAYMENT_ANNUITY,
    )
    card_overpayment = card_total - financed_amount
    card_overpayment_pct = Decimal("0") if financed_amount == 0 else card_overpayment / financed_amount * Decimal("100")
    credit_card = {
        "monthlyPayment": money(card_first_payment),
        "totalToPay": money(card_total),
        "overpayment": money(card_overpayment),
        "overpaymentPct": percent(card_overpayment_pct),
    }

    return {
        "installment": installment,
        "creditCard": credit_card,
        "comparisonMeta": {
            "annualRatePct": float(CARD_ANNUAL_RATE_PCT),
            "minPaymentPct": float(CARD_MIN_PAYMENT_PCT),
            "footerNote": "Расчёт для кредитной карты: ставка 29,9% годовых, минимальный платёж 3%.",
        },
    }


def capitalization_interval(capitalization: str) -> int | None:
    if capitalization == DEPOSIT_CAPITALIZATION_MONTHLY:
        return 1
    if capitalization == DEPOSIT_CAPITALIZATION_QUARTERLY:
        return 3
    if capitalization == DEPOSIT_CAPITALIZATION_YEARLY:
        return 12
    return None


def calculate_deposit(payload: dict[str, Any]) -> dict[str, Any]:
    amount = decimal_value(payload["amount"])
    rate_pct = decimal_value(payload["ratePct"])
    term_months = int(payload["termMonths"])
    capitalization = payload["capitalization"]
    top_up = payload["topUp"]
    monthly_top_up = decimal_value(payload.get("monthlyTopUp") or 0)

    monthly_rate = monthly_rate_from_annual(rate_pct)
    interval = capitalization_interval(capitalization)
    balance = amount
    accrued_interest = Decimal("0")
    total_top_ups = Decimal("0")
    series = [{"month": 0, "label": "Старт", "total": money(amount)}]

    for month in range(1, term_months + 1):
        interest = balance * monthly_rate
        accrued_interest += interest

        if interval and month % interval == 0:
            balance += accrued_interest
            accrued_interest = Decimal("0")

        if top_up == DEPOSIT_TOP_UP_MONTHLY and monthly_top_up > 0:
            balance += monthly_top_up
            total_top_ups += monthly_top_up

        current_total = balance + accrued_interest
        series.append(
            {
                "month": month,
                "label": f"{month} мес.",
                "total": money(current_total),
            }
        )

    final_amount = balance + accrued_interest
    income = final_amount - amount - total_top_ups
    effective_rate_pct = calculate_effective_deposit_rate(rate_pct, capitalization)

    return {
        "income": money(income),
        "finalAmount": money(final_amount),
        "effectiveRatePct": percent(effective_rate_pct),
        "series": series,
    }


def calculate_effective_deposit_rate(rate_pct: Decimal, capitalization: str) -> Decimal:
    nominal = rate_pct / Decimal("100")
    if capitalization == DEPOSIT_CAPITALIZATION_MONTHLY:
        return (((Decimal("1") + nominal / Decimal("12")) ** 12) - Decimal("1")) * Decimal("100")
    if capitalization == DEPOSIT_CAPITALIZATION_QUARTERLY:
        return (((Decimal("1") + nominal / Decimal("4")) ** 4) - Decimal("1")) * Decimal("100")
    return rate_pct


def calculate_pension(payload: dict[str, Any]) -> dict[str, Any]:
    current_age = int(payload["currentAge"])
    retire_age = int(payload["retireAge"])
    monthly_contribution = decimal_value(payload["monthlyContribution"])
    return_rate_pct = decimal_value(payload["returnRatePct"])
    inflation_pct = decimal_value(payload["inflationPct"])
    initial_saved = decimal_value(payload.get("initialSaved", 0))

    years = retire_age - current_age
    months = years * 12
    monthly_return = monthly_rate_from_annual(return_rate_pct)
    monthly_inflation = monthly_rate_from_annual(inflation_pct)
    balance = initial_saved
    total_contributions = initial_saved
    series: list[dict[str, Any]] = [
        {
            "age": current_age,
            "contributions": money(total_contributions),
            "growth": money(Decimal("0")),
            "total": money(balance),
        }
    ]

    for month in range(1, months + 1):
        balance = balance * (Decimal("1") + monthly_return) + monthly_contribution
        total_contributions += monthly_contribution
        age = current_age + month // 12
        is_full_year = month % 12 == 0
        years_passed = month // 12
        should_add_point = is_full_year and (years_passed % 3 == 0 or age == retire_age)
        if should_add_point:
            growth = balance - total_contributions
            series.append(
                {
                    "age": age,
                    "contributions": money(total_contributions),
                    "growth": money(growth),
                    "total": money(balance),
                }
            )

    capital_at_retirement = balance
    real_discount_factor = (Decimal("1") + monthly_inflation) ** months if monthly_inflation > 0 else Decimal("1")
    real_capital = capital_at_retirement / real_discount_factor
    monthly_pension_real = real_capital / PENSION_PAYOUT_MONTHS

    return {
        "capitalAtRetirement": money(capital_at_retirement),
        "monthlyPensionReal": money(monthly_pension_real),
        "series": series,
    }


def calculate_inflation(payload: dict[str, Any]) -> dict[str, Any]:
    amount = decimal_value(payload["amount"])
    years = int(payload["years"])
    inflation_pct = decimal_value(payload["inflationPct"])
    factor = (Decimal("1") + inflation_pct / Decimal("100")) ** years
    future_value = amount / factor if factor else amount
    purchasing_power_loss = amount - future_value
    loss_pct = Decimal("0") if amount == 0 else purchasing_power_loss / amount * Decimal("100")

    return {
        "futureValue": money(future_value),
        "purchasingPowerLoss": money(purchasing_power_loss),
        "lossPct": percent(loss_pct),
    }
