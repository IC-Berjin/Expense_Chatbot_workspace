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
    "id": "id",
    "tenant id": "tenant_id",
    "employee email": "employee_email",
    "email": "employee_email",
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
    "meta": "meta",
    "expense form": "expense_form_id",
    "expense form id": "expense_form_id",
    "payment status": "payment_status",
    "payment method": "payment_method",
    "payment comment": "payment_comment",
    "paid date": "paid_at",
    "paid at": "paid_at",
    "paid by": "paid_by_email",
    "paid by email": "paid_by_email",
}

SAFE_EXPENSE_SELECT = set(EXPENSE_CLAIM_FIELDS.values())


class ActionGetExpenseClaims(Action):
    def name(self) -> Text:
        return "action_get_expense_claims"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        print("Running ActionGetExpenseClaims...")
        
        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")
        employeeCode = metadata.get("employeeCode")

        print("Session Data:", metadata)
        
        # ✅ Block normal EMPLOYEE users
        if role == "EMPLOYEE":
            dispatcher.utter_message(
                text="No privilege for you to access other claim details."
            )
            return []
        
        # added by Berjin for testing, reverse the commented code
        # employee_name = first_entity_value(tracker, "employee_name")
        # employee_email = first_entity_value(tracker, "employee_email")
        # expense_status = first_entity_value(tracker, "expense_status")
        # payment_status = first_entity_value(tracker, "payment_status")
        # currency = first_entity_value(tracker, "currency")

        current_employee_name = first_entity_value(tracker, "employee_name")
        current_employee_email = first_entity_value(tracker, "employee_email")
        current_expense_status = first_entity_value(tracker, "expense_status")
        current_payment_status = first_entity_value(tracker, "payment_status")
        current_currency = first_entity_value(tracker, "currency")

        employee_name = current_employee_name or tracker.get_slot("employee_name")
        employee_email = current_employee_email or tracker.get_slot("employee_email")
        expense_status = current_expense_status or tracker.get_slot("expense_status")
        payment_status = current_payment_status or tracker.get_slot("payment_status")
        currency = current_currency or tracker.get_slot("currency")
        # added by Berjin for testing

        raw_fields = all_entity_values(tracker, "expense_claim_field")

        user_text = normalize_text(tracker.latest_message.get("text"))
        intent_name = tracker.latest_message.get("intent", {}).get("name")

        fields = []

        if intent_name == "ask_expense_claim_attribute":
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
                return []

            # select_sql = ", ".join([f"ec.{field} AS {field}" for field in fields])
            base_columns = [
                "emp.name AS employee_name",
                "ec.title",
                "ec.total_amount",
                "ec.currency"
            ]

            # add requested fields
            for field in fields:
                column = f"ec.{field} AS {field}"
                if column not in base_columns:
                    base_columns.append(column)

            select_sql = ", ".join(base_columns)    
        else:
            select_sql = self.build_select_columns(user_text)

        # sql = f"""
        # SELECT
        #     {select_sql}
        # FROM public.expense_claims ec
        # WHERE 1 = 1
        # """

        # for setting the employee that been assigned to that manager
        # employeeCode_id = None

        # if employeeCode:
        #     emp_sql = """
        #         SELECT id
        #         FROM public.employees
        #         WHERE employee_code = %s
        #         LIMIT 1
        #     """

        #     emp_rows = run_query(emp_sql, (employeeCode,))

        #     if emp_rows:
        #         employeeCode_id = emp_rows[0]["id"]

        # if not employeeCode_id:
        #     dispatcher.utter_message(
        #         text="I could not identify your employee session. Please login again."
        #     )
        #     return []


        # if employee_name:
        #     emp_manager_verification_sql = """
        #         SELECT
        #             id,
        #             name,
        #             employee_code,
        #             manager_id
        #         FROM public.employees
        #         WHERE name ILIKE %s
        #         LIMIT 1;
        #     """

        #     requested_emp_rows = run_query(emp_manager_verification_sql,(f"%{employee_name}%",))

        #     if not requested_emp_rows:
        #         dispatcher.utter_message(
        #             text="Employee details not found. Please recheck the employee name."
        #         )
        #         return []

        #     requested_employee = requested_emp_rows[0]
        #     requested_employee_manager_id = requested_employee["manager_id"]

        #     if requested_employee_manager_id != employeeCode_id:
        #         dispatcher.utter_message(
        #             text="No privilege for you to access this employee details."
        #         )
        #         return []


        # print("========== Manager Privilege Verification Started ==========")

        employeeCode_id = None


        if employeeCode:

            emp_sql = """
                SELECT id
                FROM public.employees
                WHERE employee_code = %s
                LIMIT 1
            """


            emp_rows = run_query(emp_sql, (employeeCode,))


            if emp_rows:
                employeeCode_id = emp_rows[0]["id"]

        if not employeeCode_id:

            dispatcher.utter_message(
                text="I could not identify your employee session. Please login again."
            )
            return []


        if employee_name:

            emp_manager_verification_sql = """
                SELECT
                    id,
                    name,
                    employee_code,
                    manager_id
                FROM public.employees
                WHERE name ILIKE %s
                LIMIT 1;
            """


            requested_emp_rows = run_query(
                emp_manager_verification_sql,
                (f"%{employee_name}%",)
            )


            if not requested_emp_rows:

                dispatcher.utter_message(
                    text="Employee details not found. Please recheck the employee name."
                )
                return []

            requested_employee = requested_emp_rows[0]


            requested_employee_id = requested_employee["id"]
            requested_employee_name = requested_employee["name"]
            requested_employee_code = requested_employee["employee_code"]
            requested_employee_manager_id = requested_employee["manager_id"]


            if requested_employee_manager_id != employeeCode_id:

                dispatcher.utter_message( 
                    text="No privilege for you to access this employee details."
                )
                return []


        # print("========== Manager Privilege Verification Ended ==========")
        # ends ************************************************************************************************

        # sql = f"""
        # SELECT
        #     {select_sql}
        # FROM public.expense_claims ec
        # LEFT JOIN public.employees emp
        #     ON LOWER(ec.employee_email) = LOWER(emp.email)
        # WHERE 1 = 1
        # """

        sql = f"""
        SELECT
            {select_sql}
        FROM public.expense_claims ec
        LEFT JOIN public.employees emp
            ON LOWER(ec.employee_email) = LOWER(emp.email)
        WHERE manager_id = %s
        """

        params = [employeeCode_id]  # Start with the employeeCode_id as the first parameter

        if employee_name:
            sql += " AND emp.name ILIKE %s"
            params.append(f"%{employee_name}%")

        if employee_email:
            sql += " AND ec.employee_email ILIKE %s"
            params.append(f"%{employee_email}%")

        if expense_status:
            sql += " AND ec.status ILIKE %s"
            params.append(f"%{expense_status}%")

        if payment_status:
            sql += " AND ec.payment_status ILIKE %s"
            params.append(f"%{payment_status}%")

        if currency:
            sql += " AND ec.currency ILIKE %s"
            params.append(f"%{currency}%")

        if not expense_status:
            if "approved" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%approved%")
            elif "rejected" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%rejected%")
            elif "submitted" in user_text:
                sql += " AND ec.status ILIKE %s"
                params.append("%submitted%")

        if not payment_status:
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

        limit = self.get_limit(user_text)

        sql += f"""
        ORDER BY ec.submitted_at DESC NULLS LAST, ec.created_at DESC NULLS LAST
        LIMIT {limit};
        """

        rows = run_query(sql, tuple(params))
        print(rows)
        send_table_response(dispatcher, rows, message=f"Found {len(rows)} expense claim record(s).")

        return [
            SlotSet("employee_name", employee_name),#added by Berjin for testing, 
            SlotSet("employee_email", employee_email),
            SlotSet("expense_status", expense_status),
            SlotSet("payment_status", payment_status),
            SlotSet("currency", currency),
        ]

    def get_limit(self, user_text: str) -> int:
        if "latest" in user_text or "last claim" in user_text or "only one" in user_text:
            return 1
        if "recent" in user_text or "last 5" in user_text or "top 5" in user_text:
            return 5
        if "last 10" in user_text or "top 10" in user_text:
            return 10
        return 20

    def build_select_columns(self, user_text: str) -> str:
        if "payment" in user_text or "paid" in user_text or "unpaid" in user_text:
            return """
                emp.name AS employee_name,
                ec.employee_email,
                ec.title,
                ec.total_amount,
                ec.currency,
                ec.payment_status,
                ec.payment_method,
                ec.payment_comment,
                ec.paid_at,
                ec.paid_by_email
            """

        if "rejected" in user_text or "reject reason" in user_text:
            return """
                ec.employee_email,
                ec.title,
                ec.total_amount,
                ec.currency,
                ec.status,
                ec.rejected_at,
                ec.reject_reason
            """

        if "approved" in user_text:
            return """
                ec.employee_email,
                ec.title,
                ec.total_amount,
                ec.currency,
                ec.status,
                ec.submitted_at,
                ec.approved_at
            """

        if "amount" in user_text or "total" in user_text:
            return """
                ec.employee_email,
                ec.title,
                ec.total_amount,
                ec.currency,
                ec.status
            """

        return """
            ec.employee_email,
            ec.title,
            ec.currency,
            ec.total_amount,
            ec.status,
            ec.submitted_at,
            ec.payment_status
        """