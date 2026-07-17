from datetime import datetime, timedelta
from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from actions.actions_employees.actions import (
    run_query,
    send_table_response,
    first_entity_value,
    all_entity_values,
    normalize_text,
    safe_field,
)


EXPENSE_CLAIM_FIELDS = {
    "title": "title",
    "currency": "currency",
    "total amount": "total_amount",
    "amount": "total_amount",
    "claim amount": "total_amount",
    "status": "status",
    "submitted date": "submitted_at",
    "submitted at": "submitted_at",
    "approved date": "approved_at",
    "approved at": "approved_at",
    "rejected date": "rejected_at",
    "rejected at": "rejected_at",
    "reject reason": "reject_reason",
    "rejection reason": "reject_reason",
    "payment status": "payment_status",
    "payment method": "payment_method",
    "payment comment": "payment_comment",
    "paid date": "paid_at",
    "paid at": "paid_at",
    "paid by": "paid_by_email",
    "paid by email": "paid_by_email",
}

SAFE_EXPENSE_SELECT = set(EXPENSE_CLAIM_FIELDS.values())

CATEGORY_KEYWORDS = [
    "metro city", "metro", "car", "bike", "taxi", "bus", "flight", "fuel",
    "hotel", "other", "lunch", "dinner", "breakfast", "tea", "coffee",
    "refreshments", "rapido", "ola", "ii ac", "air travel", "train",
    "train travel"
]


class ActionGetMyExpenseClaims(Action):
    def name(self) -> Text:
        return "action_get_my_expense_claims"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        metadata = tracker.latest_message.get("metadata", {})
        print("Running ActionGetMyExpenseClaims...")
        print("Session Data:", metadata)

        logged_email = metadata.get("email")
        employee_code = metadata.get("employeeCode")
        role = str(metadata.get("role") or "").upper()

        if not logged_email and not employee_code:
            dispatcher.utter_message(
                text="I could not identify your session. Please login again."
            )
            return []

        user_text = normalize_text(tracker.latest_message.get("text"))
        intent_name = tracker.latest_message.get("intent", {}).get("name")

        expense_status = first_entity_value(tracker, "expense_status")
        payment_status = first_entity_value(tracker, "payment_status")
        expense_category = first_entity_value(tracker, "expense_category")
        raw_fields = all_entity_values(tracker, "expense_claim_field")

        if not expense_category:
            expense_category = self.detect_category(user_text)

        if intent_name == "ask_my_expense_claim_attribute":
            print("ask_my_expense_claim_attribute")  # Debug log
            rows = self.run_attribute_query(
                dispatcher,
                user_text,
                raw_fields,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        elif intent_name == "ask_my_expense_claim_summary":
            print("ask_my_expense_claim_summary")  # Debug log
            rows = self.run_summary_query(
                user_text,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        elif intent_name == "ask_my_expense_claim_count":
            print("ask_my_expense_claim_count")  # Debug log
            rows = self.run_count_query(
                user_text,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        elif intent_name == "ask_my_expense_claim_average":
            print("ask_my_expense_claim_average")  # Debug log
            rows = self.run_average_query(
                user_text,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        elif intent_name == "ask_my_expense_claim_comparison":
            print("ask_my_expense_claim_comparison")  # Debug log
            rows = self.run_comparison_query(
                user_text,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        else:
            print("else block")  # Debug log
            rows = self.run_list_query(
                user_text,
                logged_email,
                employee_code,
                expense_status,
                payment_status,
                expense_category,
            )

        if rows is None:
            return []

        send_table_response(dispatcher, rows, message=f"Found {len(rows)} record(s).")
        
        return [
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

    def add_self_filter(
        self,
        sql: str,
        params: List[Any],
        logged_email: str = None,
        employee_code: str = None,
    ):
        sql += """
        AND (
            LOWER(ec.employee_email) = LOWER(%s)
            OR emp.employee_code = %s
        )
        """
        params.append(logged_email)
        params.append(employee_code)
        return sql, params

    def add_common_filters(
        self,
        sql: str,
        params: List[Any],
        user_text: str,
        logged_email: str = None,
        employee_code: str = None,
        expense_status: str = None,
        payment_status: str = None,
        expense_category: str = None,
    ):
        sql, params = self.add_self_filter(sql, params, logged_email, employee_code)

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
        if "latest" in user_text or "last claim" in user_text or "only one" in user_text:
            return 1
        if "recent" in user_text or "last 5" in user_text or "top 5" in user_text:
            return 5
        if "last 10" in user_text or "top 10" in user_text:
            return 10
        return 20

    def run_list_query(
        self,
        user_text,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
    ):
        params = []

        sql = f"""
        SELECT
            emp.name AS Name,
            ec.title,
            ec.currency,
            ec.total_amount,
            ec.status,
            ec.submitted_at,
            ec.approved_at,
            ec.rejected_at,
            ec.reject_reason,
            ec.payment_status,
            ec.payment_method,
            ec.payment_comment,
            ec.paid_at,
            ec.paid_by_email,
            eci.category,
            eci.description,
            eci.amount AS item_amount,
            eci.expense_date,
            eci.distance_km,
            eci.per_km_rate,
            eci.travel_amount
        {self.base_from_sql()}
        """

        sql, params = self.add_common_filters(
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        limit = self.get_limit(user_text)

        sql += f"""
        ORDER BY ec.created_at DESC NULLS LAST, eci.expense_date DESC NULLS LAST
        LIMIT {limit};
        """

        return run_query(sql, tuple(params))

    def run_attribute_query(
        self,
        dispatcher,
        user_text,
        raw_fields,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
    ):
        fields = []

        for raw_field in raw_fields:
            column = safe_field(EXPENSE_CLAIM_FIELDS, raw_field)
            if column and column in SAFE_EXPENSE_SELECT and column not in fields:
                fields.append(column)

        if not fields:
            for keyword, column in EXPENSE_CLAIM_FIELDS.items():
                if keyword in user_text and column not in fields:
                    fields.append(column)

        if not fields:
            dispatcher.utter_message(
                text="Please specify which claim field you want. Example: status, total amount, payment status, paid date, or reject reason."
            )
            return None

        select_parts = [
            "ec.title",
            "ec.total_amount",
            "ec.currency",
        ]

        for field in fields:
            column = f"ec.{field} AS {field}"
            if column not in select_parts:
                select_parts.append(column)

        select_sql = ", ".join(select_parts)
        params = []

        sql = f"""
        SELECT
            {select_sql}
        {self.base_from_sql()}
        """

        sql, params = self.add_common_filters(
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        sql += """
        ORDER BY ec.created_at DESC NULLS LAST
        LIMIT 5;
        """

        return run_query(sql, tuple(params))

    def run_summary_query(
        self,
        user_text,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
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
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        sql += group_by + ";"
        return run_query(sql, tuple(params))

    def run_count_query(
        self,
        user_text,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
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

        else:
            sql = f"""
            SELECT
                COUNT(DISTINCT ec.id) AS claim_count,
                COUNT(eci.id) AS item_count
            {self.base_from_sql()}
            """
            group_by = ""

        sql, params = self.add_common_filters(
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        sql += group_by + ";"
        return run_query(sql, tuple(params))

    def run_average_query(
        self,
        user_text,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
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
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        sql += group_by + ";"
        return run_query(sql, tuple(params))

    def run_comparison_query(
        self,
        user_text,
        logged_email,
        employee_code,
        expense_status,
        payment_status,
        expense_category,
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
            start_current,
            current_label,
            start_previous,
            end_previous,
            previous_label,
            start_current,
            start_previous,
            end_previous,
        ])

        sql, params = self.add_common_filters(
            sql,
            params,
            user_text,
            logged_email,
            employee_code,
            expense_status,
            payment_status,
            expense_category,
        )

        sql += """
        ) x
        WHERE period IS NOT NULL
        GROUP BY period
        ORDER BY period;
        """

        return run_query(sql, tuple(params))