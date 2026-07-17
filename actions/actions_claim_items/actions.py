from datetime import datetime, timedelta
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from actions.actions_employees.actions import (
    run_query,
    send_table_response,
    first_entity_value,
    normalize_text,
)


CATEGORY_KEYWORDS = [
    "metro city", "metro", "car", "bike", "taxi", "bus", "flight", "fuel",
    "hotel", "other", "lunch", "dinner", "breakfast", "tea", "coffee",
    "refreshments", "rapido", "ola", "ii ac", "air travel", "train",
    "train travel"
]


class ActionGetExpenseClaimsItems(Action):
    def name(self) -> Text:
        return "action_get_expense_claims_Items"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        print("Running ActionGetExpenseClaimsItems")

        metadata = tracker.latest_message.get("metadata", {})
        role = str(metadata.get("role") or "").upper()

        employee_name = first_entity_value(tracker, "employee_name")
        employee_email = first_entity_value(tracker, "employee_email")
        expense_status = first_entity_value(tracker, "expense_status")
        payment_status = first_entity_value(tracker, "payment_status")
        expense_category = first_entity_value(tracker, "expense_category")

        user_text = normalize_text(tracker.latest_message.get("text"))
        intent_name = tracker.latest_message.get("intent", {}).get("name")

        # Optional security: block employees from viewing everyone else's data.
        if role == "EMPLOYEE" and not ("my" in user_text):
            dispatcher.utter_message(text="No privilege for you to access other claim details.")
            return []

        if not expense_category:
            expense_category = self.detect_category(user_text)

        if intent_name == "ask_expense_claim_summary":
            rows = self.run_summary_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        elif intent_name == "ask_expense_claim_count":
            rows = self.run_count_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        elif intent_name == "ask_expense_claim_average":
            rows = self.run_average_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        elif intent_name == "ask_expense_claim_comparison":
            rows = self.run_comparison_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        elif intent_name == "ask_expense_claim_top_analysis":
            rows = self.run_top_analysis_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        else:
            rows = self.run_list_query(
                user_text, employee_name, employee_email, expense_status,
                payment_status, expense_category
            )

        send_table_response(dispatcher, rows, message=f"Found {len(rows)} record(s).")

        return [
            SlotSet("employee_name", employee_name),
            SlotSet("employee_email", employee_email),
            SlotSet("expense_status", expense_status),
            SlotSet("payment_status", payment_status),
            SlotSet("expense_category", expense_category),
        ]

    def base_from_sql(self) -> str:
        return """
        FROM public.expense_claims ec
        LEFT JOIN public.expense_claim_items eci
            ON ec.id = eci.claim_id
        LEFT JOIN public.employees emp
            ON LOWER(ec.employee_email) = LOWER(emp.email)
        WHERE 1 = 1
        """

    def add_common_filters(
        self,
        sql: str,
        params: List[Any],
        user_text: str,
        employee_name: str = None,
        employee_email: str = None,
        expense_status: str = None,
        payment_status: str = None,
        expense_category: str = None,
    ):
        if employee_name:
            sql += " AND emp.name ILIKE %s"
            params.append(f"%{employee_name}%")

        if employee_email:
            sql += " AND ec.employee_email ILIKE %s"
            params.append(f"%{employee_email}%")

        if expense_status:
            sql += " AND ec.status ILIKE %s"
            params.append(f"%{expense_status}%")
        else:
            if "approved" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%approved%")
            elif "rejected" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%rejected%")
            elif "submitted" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%submitted%")
            elif "pending" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%pending%")

        if payment_status:
            sql += " AND ec.payment_status ILIKE %s"
            params.append(f"%{payment_status}%")
        else:
            if "unpaid" in user_text or "pending payment" in user_text:
                sql += """
                AND (
                    ec.payment_status IS NULL
                    OR ec.payment_status ILIKE %s
                    OR ec.paid_at IS NULL
                )
                """
                params.append("%unpaid%")
            elif "paid" in user_text:
                sql += " AND ec.payment_status ILIKE %s"
                params.append("%paid%")

        if expense_category:
            sql += """
            AND (
                eci.category ILIKE %s
                OR eci.description ILIKE %s
            )
            """
            params.append(f"%{expense_category}%")
            params.append(f"%{expense_category}%")

        today = datetime.now().date()

        if "today" in user_text:
            sql += " AND DATE(ec.submitted_at) = %s"
            params.append(today)

        elif "yesterday" in user_text:
            sql += " AND DATE(ec.submitted_at) = %s"
            params.append(today - timedelta(days=1))

        elif "this week" in user_text:
            start_week = today - timedelta(days=today.weekday())
            sql += " AND DATE(ec.submitted_at) >= %s"
            params.append(start_week)

        elif "last week" in user_text:
            start_this_week = today - timedelta(days=today.weekday())
            start_last_week = start_this_week - timedelta(days=7)
            sql += " AND DATE(ec.submitted_at) >= %s AND DATE(ec.submitted_at) < %s"
            params.append(start_last_week)
            params.append(start_this_week)

        elif "this month" in user_text:
            start_month = today.replace(day=1)
            sql += " AND DATE(ec.submitted_at) >= %s"
            params.append(start_month)

        elif "previous month" in user_text or "last month" in user_text:
            start_this_month = today.replace(day=1)
            last_month_end = start_this_month - timedelta(days=1)
            start_last_month = last_month_end.replace(day=1)
            sql += " AND DATE(ec.submitted_at) >= %s AND DATE(ec.submitted_at) < %s"
            params.append(start_last_month)
            params.append(start_this_month)

        return sql, params

    def detect_category(self, user_text: str):
        for keyword in CATEGORY_KEYWORDS:
            if keyword in user_text:
                return keyword
        return None

    def get_limit(self, user_text: str) -> int:
        if "top 5" in user_text or "last 5" in user_text or "recent" in user_text:
            return 5
        if "top 10" in user_text or "last 10" in user_text:
            return 10
        if "latest" in user_text or "only one" in user_text:
            return 1
        return 20

    def run_list_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        sql = f"""
        SELECT
            emp.name AS employee_name,
            ec.employee_email,
            ec.title,
            ec.currency,
            ec.total_amount,
            ec.status,
            ec.submitted_at,
            ec.payment_status,
            eci.expense_date,
            eci.category,
            eci.description,
            eci.amount AS item_amount,
            eci.distance_km,
            eci.per_km_rate,
            eci.travel_amount
        {self.base_from_sql()}
        """

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        limit = self.get_limit(user_text)

        sql += f"""
        ORDER BY ec.created_at DESC NULLS LAST, eci.expense_date DESC NULLS LAST
        LIMIT {limit};
        """

        return run_query(sql, tuple(params))

    def run_summary_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        if "category wise" in user_text or "category-wise" in user_text:
            sql = f"""
            SELECT
                eci.category,
                COUNT(DISTINCT ec.id) AS claim_count,
                SUM(eci.amount) AS total_item_amount,
                SUM(ec.total_amount) AS total_claim_amount
            {self.base_from_sql()}
            """
            group_by = " GROUP BY eci.category ORDER BY total_item_amount DESC NULLS LAST"

        elif "employee wise" in user_text or "employee-wise" in user_text:
            sql = f"""
            SELECT
                emp.name AS employee_name,
                ec.employee_email,
                COUNT(DISTINCT ec.id) AS claim_count,
                SUM(ec.total_amount) AS total_claim_amount
            {self.base_from_sql()}
            """
            group_by = " GROUP BY emp.name, ec.employee_email ORDER BY total_claim_amount DESC NULLS LAST"

        elif "payment method" in user_text:
            sql = f"""
            SELECT
                ec.payment_method,
                COUNT(DISTINCT ec.id) AS claim_count,
                SUM(ec.total_amount) AS total_claim_amount
            {self.base_from_sql()}
            """
            group_by = " GROUP BY ec.payment_method ORDER BY total_claim_amount DESC NULLS LAST"

        else:
            sql = f"""
            SELECT
                COUNT(DISTINCT ec.id) AS claim_count,
                SUM(ec.total_amount) AS total_claim_amount,
                SUM(eci.amount) AS total_item_amount,
                SUM(eci.travel_amount) AS total_travel_amount,
                SUM(eci.distance_km) AS total_distance_km
            {self.base_from_sql()}
            """
            group_by = ""

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        sql += group_by + ";"

        return run_query(sql, tuple(params))

    def run_count_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        if "category" in user_text:
            sql = f"""
            SELECT
                eci.category,
                COUNT(DISTINCT ec.id) AS claim_count,
                COUNT(eci.id) AS item_count
            {self.base_from_sql()}
            """
            group_by = " GROUP BY eci.category ORDER BY claim_count DESC"

        elif "employee" in user_text or "people" in user_text:
            sql = f"""
            SELECT
                emp.name AS employee_name,
                ec.employee_email,
                COUNT(DISTINCT ec.id) AS claim_count
            {self.base_from_sql()}
            """
            group_by = " GROUP BY emp.name, ec.employee_email ORDER BY claim_count DESC"

        else:
            sql = f"""
            SELECT
                COUNT(DISTINCT ec.id) AS claim_count,
                COUNT(DISTINCT ec.employee_email) AS employee_count,
                COUNT(eci.id) AS item_count
            {self.base_from_sql()}
            """
            group_by = ""

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        sql += group_by + ";"

        return run_query(sql, tuple(params))

    def run_average_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        if "category" in user_text:
            sql = f"""
            SELECT
                eci.category,
                AVG(eci.amount) AS average_item_amount,
                AVG(ec.total_amount) AS average_claim_amount
            {self.base_from_sql()}
            """
            group_by = " GROUP BY eci.category ORDER BY average_item_amount DESC NULLS LAST"

        elif "employee" in user_text:
            sql = f"""
            SELECT
                emp.name AS employee_name,
                ec.employee_email,
                AVG(ec.total_amount) AS average_claim_amount
            {self.base_from_sql()}
            """
            group_by = " GROUP BY emp.name, ec.employee_email ORDER BY average_claim_amount DESC NULLS LAST"

        else:
            sql = f"""
            SELECT
                AVG(ec.total_amount) AS average_claim_amount,
                AVG(eci.amount) AS average_item_amount,
                AVG(eci.distance_km) AS average_distance_km,
                AVG(eci.travel_amount) AS average_travel_amount
            {self.base_from_sql()}
            """
            group_by = ""

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        sql += group_by + ";"

        return run_query(sql, tuple(params))

    def run_top_analysis_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        limit = 5
        if "top 10" in user_text:
            limit = 10

        if "category" in user_text:
            metric = "SUM(eci.amount)" if "amount" in user_text or "highest" in user_text else "COUNT(eci.id)"
            metric_alias = "total_item_amount" if "amount" in user_text or "highest" in user_text else "item_count"

            sql = f"""
            SELECT
                eci.category,
                COUNT(DISTINCT ec.id) AS claim_count,
                COUNT(eci.id) AS item_count,
                SUM(eci.amount) AS total_item_amount
            {self.base_from_sql()}
            """
            group_by = f" GROUP BY eci.category ORDER BY {metric_alias} DESC NULLS LAST LIMIT {limit}"

        else:
            metric_alias = "total_claim_amount" if "amount" in user_text or "highest" in user_text else "claim_count"

            sql = f"""
            SELECT
                emp.name AS employee_name,
                ec.employee_email,
                COUNT(DISTINCT ec.id) AS claim_count,
                SUM(ec.total_amount) AS total_claim_amount
            {self.base_from_sql()}
            """
            group_by = f" GROUP BY emp.name, ec.employee_email ORDER BY {metric_alias} DESC NULLS LAST LIMIT {limit}"

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        sql += group_by + ";"

        return run_query(sql, tuple(params))

    def run_comparison_query(
        self, user_text, employee_name, employee_email, expense_status,
        payment_status, expense_category
    ):
        params = []

        today = datetime.now().date()

        if "week" in user_text:
            start_current = today - timedelta(days=today.weekday())
            start_previous = start_current - timedelta(days=7)
            end_previous = start_current

            current_label = "This Week"
            previous_label = "Last Week"
        else:
            start_current = today.replace(day=1)
            previous_month_end = start_current - timedelta(days=1)
            start_previous = previous_month_end.replace(day=1)
            end_previous = start_current

            current_label = "This Month"
            previous_label = "Previous Month"

        sql = f"""
        SELECT
            period,
            COUNT(DISTINCT claim_id) AS claim_count,
            SUM(total_amount) AS total_claim_amount,
            SUM(item_amount) AS total_item_amount
        FROM (
            SELECT
                ec.id AS claim_id,
                ec.total_amount,
                eci.amount AS item_amount,
                CASE
                    WHEN DATE(ec.submitted_at) >= %s THEN %s
                    WHEN DATE(ec.submitted_at) >= %s AND DATE(ec.submitted_at) < %s THEN %s
                END AS period
            {self.base_from_sql()}
            AND (
                DATE(ec.submitted_at) >= %s
                OR (DATE(ec.submitted_at) >= %s AND DATE(ec.submitted_at) < %s)
            )
        """

        params.extend([
            start_current, current_label,
            start_previous, end_previous, previous_label,
            start_current, start_previous, end_previous
        ])

        sql, params = self.add_common_filters(
            sql, params, user_text, employee_name, employee_email,
            expense_status, payment_status, expense_category
        )

        sql += """
        ) x
        WHERE period IS NOT NULL
        GROUP BY period
        ORDER BY period;
        """

        return run_query(sql, tuple(params))