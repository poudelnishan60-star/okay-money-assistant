"""HTTP-level tests for the REST API (seeded data, today pinned to 2026-11-09)."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

# --- meta ---------------------------------------------------------------------------------


def test_me_and_unknown_user(client: TestClient) -> None:
    me = client.get("/me").json()
    assert me == {
        "id": "demo_user",
        "name": "Anjali Thapa",
        "balance_paisa": 23_944_86,
        "balance_hidden": False,
    }
    assert client.get("/me", headers={"X-User-Id": "nobody"}).status_code == 404


def test_categories(client: TestClient) -> None:
    cats = {c["name"]: c for c in client.get("/categories").json()}
    assert len(cats) == 14
    assert cats["Bills & Utilities"]["subcategories"] == ["Electricity", "Khanepani", "Internet/TV"]
    assert cats["Transfers"]["counts_as_spending"] is False
    assert cats["Food & Dining"]["counts_as_spending"] is True


def test_operation_ids_are_readable(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert {
        "list_transactions",
        "set_transaction_category",
        "get_dashboard",
        "upsert_budget",
        "create_goal",
        "get_bills",
        "update_bill_status",
    } <= ops


# --- transactions -------------------------------------------------------------------------


def test_list_transactions_newest_first_and_paged(client: TestClient) -> None:
    page = client.get("/transactions").json()
    assert page["total"] == 154 and page["limit"] == 50 and len(page["items"]) == 50
    times = [i["occurred_at"] for i in page["items"]]
    assert times == sorted(times, reverse=True)
    assert times[0].endswith("+05:45")
    second = client.get("/transactions", params={"offset": 50, "limit": 50}).json()
    assert second["items"][0]["id"] != page["items"][0]["id"]
    assert {i["id"] for i in second["items"]}.isdisjoint({i["id"] for i in page["items"]})


def test_period_chips_and_custom_range(client: TestClient) -> None:
    week = client.get("/transactions", params={"period": "7d", "limit": 200}).json()
    assert (week["start"], week["end"]) == ("2026-11-03", "2026-11-09")
    assert all("2026-11-03" <= i["occurred_at"][:10] <= "2026-11-09" for i in week["items"])
    month = client.get("/transactions", params={"period": "this_month"}).json()
    assert month["start"] == "2026-11-01"
    custom = client.get(
        "/transactions", params={"start": "2026-10-01", "end": "2026-10-31", "limit": 200}
    ).json()
    assert all(i["occurred_at"].startswith("2026-10") for i in custom["items"])
    assert (
        client.get("/transactions", params={"start": "2026-10-31", "end": "2026-10-01"}).status_code
        == 422
    )
    assert client.get("/transactions", params={"period": "9d"}).status_code == 422


def test_transaction_filters_and_totals(client: TestClient) -> None:
    food = client.get("/transactions", params={"category": "Food & Dining", "limit": 200}).json()
    assert food["total"] > 0 and all(i["category"] == "Food & Dining" for i in food["items"])
    assert food["total_debit_paisa"] == sum(i["amount_paisa"] for i in food["items"])
    momo = client.get("/transactions", params={"merchant": "momo"}).json()
    assert all("Momo" in i["merchant"] for i in momo["items"])
    bills = client.get("/transactions", params={"type": "bill_payment"}).json()
    assert bills["total"] == 12
    big = client.get("/transactions", params={"min_paisa": 10_000_00, "limit": 200}).json()
    assert all(i["amount_paisa"] >= 10_000_00 for i in big["items"])
    assert client.get("/transactions", params={"category": "Nope"}).status_code == 422


def test_get_and_recategorize(client: TestClient) -> None:
    mart = client.get("/transactions", params={"merchant": "Ratna Mart", "limit": 200}).json()
    first = mart["items"][0]
    assert client.get(f"/transactions/{first['id']}").json() == first
    assert client.get("/transactions/txn_9999").status_code == 404

    one = client.patch(
        f"/transactions/{first['id']}/category", json={"category": "Shopping"}
    ).json()
    assert one["updated_ids"] == [first["id"]]
    assert one["transaction"]["category"] == "Shopping"
    assert one["transaction"]["category_source"] == "user"

    every = client.patch(
        f"/transactions/{first['id']}/category",
        json={"category": "Groceries", "apply_to_merchant": True},
    ).json()
    assert len(every["updated_ids"]) == mart["total"]
    after = client.get("/transactions", params={"merchant": "Ratna Mart", "limit": 200}).json()
    assert {i["category_source"] for i in after["items"]} == {"user"}

    bad = client.patch(
        f"/transactions/{first['id']}/category",
        json={"category": "Food & Dining", "subcategory": "Electricity"},
    )
    assert bad.status_code == 422
    assert (
        client.patch(
            "/transactions/txn_9999/category", json={"category": "Food & Dining"}
        ).status_code
        == 404
    )


# --- insights -----------------------------------------------------------------------------


def _spending(client: TestClient, start: str, end: str) -> int:
    cats = {c["name"]: c["counts_as_spending"] for c in client.get("/categories").json()}
    items = client.get(
        "/transactions", params={"start": start, "end": end, "direction": "debit", "limit": 200}
    ).json()["items"]
    return sum(i["amount_paisa"] for i in items if cats[i["category"]])


def test_summary_current_month_matches_the_transactions(client: TestClient) -> None:
    s = client.get("/insights/summary").json()
    assert s["period"]["label"] == "Nov 2026" and s["in_progress"]
    assert s["comparison_basis"] == "same_days"
    assert s["total_spent_paisa"] == _spending(client, "2026-11-01", "2026-11-09")
    assert s["previous_compare_paisa"] == _spending(client, "2026-10-01", "2026-10-09")
    assert len(s["daily"]) == 9
    assert sum(d["spent_paisa"] for d in s["daily"]) == s["total_spent_paisa"]
    assert abs(sum(c["share_percent"] for c in s["by_category"]) - 100) < 0.5


def test_summary_past_month_bs_month_and_week(client: TestClient) -> None:
    oct_ = client.get("/insights/summary", params={"month": "2026-10"}).json()
    assert oct_["comparison_basis"] == "full_period"
    assert oct_["total_spent_paisa"] == _spending(client, "2026-10-01", "2026-10-31")
    assert oct_["previous_total_spent_paisa"] == _spending(client, "2026-09-01", "2026-09-30")
    spent = [c["spent_paisa"] for c in oct_["by_category"]]
    assert spent == sorted(spent, reverse=True)

    kartik = client.get("/insights/summary", params={"month": "2083-07", "calendar": "BS"}).json()
    assert kartik["period"] == {
        "start": "2026-10-18",
        "end": "2026-11-16",
        "label": "Kartik 2083",
        "days": 30,
    }
    assert kartik["previous_period"]["label"] == "Aswin 2083"

    week = client.get("/insights/summary", params={"period": "week"}).json()
    assert week["period"]["days"] == 7 and week["previous_period"]["end"] == "2026-11-02"


def test_summary_validation(client: TestClient) -> None:
    assert client.get("/insights/summary", params={"month": "2026-13"}).status_code == 422
    assert client.get("/insights/summary", params={"month": "Oct"}).status_code == 422
    assert (
        client.get(
            "/insights/summary", params={"period": "custom", "start": "2026-10-01"}
        ).status_code
        == 422
    )
    custom = client.get(
        "/insights/summary", params={"period": "custom", "start": "2026-10-01", "end": "2026-10-10"}
    ).json()
    assert custom["period"]["days"] == 10 and custom["previous_period"]["end"] == "2026-09-30"


def test_dashboard_past_month_flags_festival_shopping(client: TestClient) -> None:
    d = client.get("/insights/dashboard", params={"month": "2026-10"}).json()
    assert d["forecast"] is None  # forecasts only for the month in progress
    [shopping] = d["unusual"]
    assert shopping["category"] == "Shopping" and shopping["ratio"] >= 2
    assert d["highlights"][0]["kind"] == "unusual_category"
    assert "Shopping" in d["highlights"][0]["message"]
    assert (
        "Sep 2026" in next(h for h in d["highlights"] if h["kind"] == "month_over_month")["message"]
    )


def test_dashboard_current_month_has_forecast(client: TestClient) -> None:
    d = client.get("/insights/dashboard").json()
    f = d["forecast"]
    assert f["horizon_end"] == "2026-11-30" and f["current_balance_paisa"] == 23_944_86
    kinds = [h["kind"] for h in d["highlights"]]
    assert ("low_balance" in kinds) != ("month_end_balance" in kinds)


def test_forecast_endpoint(client: TestClient) -> None:
    f = client.get("/insights/forecast").json()
    assert f["horizon_end"] == "2026-11-30" and len(f["points"]) == 21
    week = client.get("/insights/forecast", params={"days": 7}).json()
    assert len(week["points"]) == 7
    high = client.get("/insights/forecast", params={"threshold_paisa": 50_000_00}).json()
    assert high["below_threshold"] is True
    assert client.get("/insights/forecast", params={"days": 0}).status_code == 422


# --- budgets ------------------------------------------------------------------------------


def test_budget_crud(client: TestClient) -> None:
    budgets = client.get("/budgets").json()
    assert budgets[0]["category"] is None and len(budgets) == 4

    food = client.post("/budgets", json={"category": "Food & Dining", "limit_paisa": 6_000_00})
    assert food.status_code == 200
    food_b = food.json()
    assert food_b["level"] == "ok" and food_b["period"]["label"] == "Nov 2026"
    assert food_b["spent_paisa"] == next(
        c["spent_paisa"]
        for c in client.get("/insights/summary").json()["by_category"]
        if c["category"] == "Food & Dining"
    )

    # posting again for the same category updates instead of duplicating
    again = client.post(
        "/budgets", json={"category": "Food & Dining", "limit_paisa": 1_000_00, "calendar": "BS"}
    ).json()
    assert again["id"] == food_b["id"] and again["calendar"] == "BS"
    assert again["level"] in {"warning", "over"} and 80 in again["alerts_reached"]
    assert len(client.get("/budgets").json()) == 5

    patched = client.patch(f"/budgets/{food_b['id']}", json={"limit_paisa": 50_000_00}).json()
    assert patched["limit_paisa"] == 50_000_00 and patched["level"] == "ok"

    assert client.delete(f"/budgets/{food_b['id']}").status_code == 204
    assert client.patch(f"/budgets/{food_b['id']}", json={"limit_paisa": 1}).status_code == 404
    assert client.post("/budgets", json={"limit_paisa": 0}).status_code == 422


def test_overall_budget_upsert(client: TestClient) -> None:
    overall = client.post("/budgets", json={"category": None, "limit_paisa": 35_000_00}).json()
    assert overall["category"] is None and overall["limit_paisa"] == 35_000_00
    assert len(client.get("/budgets").json()) == 4  # replaced the seeded overall budget


# --- goals --------------------------------------------------------------------------------


def test_goal_crud(client: TestClient) -> None:
    goals = client.get("/goals").json()
    assert [g["name"] for g in goals] == ["New laptop", "Emergency fund"]
    assert goals[0]["required_monthly_paisa"] == 10_200_00

    created = client.post(
        "/goals",
        json={"name": " Dashain trip ", "target_paisa": 25_000_00, "deadline": "2027-09-15"},
    )
    assert created.status_code == 201
    g = created.json()
    assert g["name"] == "Dashain trip" and g["state"] == "active" and g["months_left"] == 11
    assert g["required_monthly_paisa"] * g["months_left"] >= 25_000_00

    done = client.patch(f"/goals/{g['id']}", json={"saved_paisa": 25_000_00}).json()
    assert done["state"] == "done" and done["required_monthly_paisa"] == 0

    assert client.delete(f"/goals/{g['id']}").status_code == 204
    assert client.delete(f"/goals/{g['id']}").status_code == 404
    assert (
        client.post(
            "/goals", json={"name": "", "target_paisa": 1, "deadline": "2027-01-01"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/goals", json={"name": "x", "target_paisa": -5, "deadline": "2027-01-01"}
        ).status_code
        == 422
    )


def test_smart_deposits(client: TestClient) -> None:
    [plan] = client.get("/smart-deposits").json()
    assert plan["installment_paisa"] == 2_000_00
    assert dt.date.fromisoformat(plan["next_date"]) > dt.date(2026, 11, 9)


# --- bills --------------------------------------------------------------------------------


def test_bills_list_and_status(client: TestClient) -> None:
    bills = client.get("/bills").json()
    assert bills[0]["merchant"] == "Ncell" and bills[0]["days_until_due"] == 1
    assert [b["due_date"] for b in bills] == sorted(b["due_date"] for b in bills)
    assert all(b["status"] == "detected" for b in bills)
    nea = next(b for b in bills if b["service"] == "electricity")
    assert (nea["due_date"], nea["cadence"]) == ("2026-11-14", "monthly")

    bid = bills[0]["id"]
    r = client.put(f"/bills/{bid}/status", json={"status": "dismissed"})
    assert r.status_code == 200 and r.json()["status"] == "dismissed"
    assert bid not in {b["id"] for b in client.get("/bills").json()}
    shown = client.get("/bills", params={"include_dismissed": True}).json()
    assert next(b for b in shown if b["id"] == bid)["status"] == "dismissed"

    client.put(f"/bills/{bid}/status", json={"status": "confirmed"})
    assert client.get("/bills").json()[0]["status"] == "confirmed"
    client.put(f"/bills/{bid}/status", json={"status": "detected"})
    assert client.get("/bills").json()[0]["status"] == "detected"

    assert client.put("/bills/nope/status", json={"status": "confirmed"}).status_code == 404
    assert client.put(f"/bills/{bid}/status", json={"status": "paid"}).status_code == 422


def test_cors_allows_local_dev_origins_only(client: TestClient) -> None:
    ok = client.options(
        "/me", headers={"Origin": "http://localhost:51234", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:51234"
    bad = client.options(
        "/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in bad.headers
