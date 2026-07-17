from datetime import date, datetime
import os
import re
from typing import Any, Dict, List, Optional, Text, Tuple
from difflib import SequenceMatcher

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

load_dotenv()


# ================================
# DB
# ================================
def get_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "IC_expense"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "root"),
    )


def run_query(sql: str, params: Tuple = ()) -> List[Dict[str, Any]]:
    conn = get_connection()

    # print(conn)  # Debug log to check connection
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    finally:
        conn.close()

# =================================
# Confidence
# =================================
def name_confidence(name1, name2):
    if not name1 or not name2:
        return 0

    name1 = name1.lower().strip()
    name2 = name2.lower().strip()

    return SequenceMatcher(None, name1, name2).ratio()

# ================================
# HELPERS
# ================================
EMPLOYEE_FIELDS = {
    "id": "id",
    "tenant id": "tenant_id",
    "tenant_id": "tenant_id",
    "email": "email",
    "mail": "email",
    "email id": "email",
    "official email": "email",
    "employee email": "email",
    "name": "name",
    "department": "department",
    "dept": "department",
    "team": "department",
    "grade": "grade",
    "mobile": "mobile",
    "phone": "mobile",
    "phone number": "mobile",
    "mobile number": "mobile",
    "contact number": "mobile",
    "manager": "manager_id",
    "manager id": "manager_id",
    "manager_id": "manager_id",
    "custom fields": "custom_fields",
    "custom_fields": "custom_fields",
    "status": "status",
    "employee status": "status",
    "created": "created_at",
    "created at": "created_at",
    "created_at": "created_at",
    "updated": "updated_at",
    "updated at": "updated_at",
    "updated_at": "updated_at",
    "employee code": "employee_code",
    "employee_code": "employee_code",
    "emp code": "employee_code",
    "employee id": "employee_code",
    "emp id": "employee_code",
    "designation": "designation",
    "role": "designation",
    "position": "designation",
    "job title": "designation",
    "title": "designation",
    "cost center": "cost_center",
    "cost centre": "cost_center",
    "cost_center": "cost_center",
    "sbu": "sbu",
    "branch": "branch",
    "location": "branch",
    "office": "branch",
    "office location": "branch",
    "legal entity": "legal_entity",
    "legal_entity": "legal_entity",
    "company entity": "legal_entity",
    "company code": "company_code",
    "company_code": "company_code",
    "organization code": "company_code",
    "employment type": "employment_type",
    "employment_type": "employment_type",
    "employee type": "employment_type",
    "work type": "employment_type",
    "job level": "job_level",
    "job_level": "job_level",
    "level": "job_level",
    "employee level": "job_level",

    # custom fields
    "project": "custom_fields.project",
    "employee project": "custom_fields.project",

    "work location": "custom_fields.work_location_type",
    "work location type": "custom_fields.work_location_type",

    "cash advance": "custom_fields.cash_advance_allowed",
    "cash advance allowed": "custom_fields.cash_advance_allowed",

    "expense policy": "custom_fields.expense_policy_group",
    "expense policy group": "custom_fields.expense_policy_group",

    "profit center": "custom_fields.profit_center",
    "profit centre": "custom_fields.profit_center",

    "per diem group": "custom_fields.per_diem_group",
}

SAFE_EMPLOYEE_SELECT = {
    "id",
    "tenant_id",
    "email",
    "name",
    "department",
    "grade",
    "mobile",
    "manager_id",
    "custom_fields",
    "status",
    "created_at",
    "updated_at",
    "employee_code",
    "designation",
    "cost_center",
    "sbu",
    "branch",
    "legal_entity",
    "company_code",
    "employment_type",
    "job_level",
    # custom fields
    "custom_fields.project",
    "custom_fields.work_location_type",
    "custom_fields.cash_advance_allowed",
    "custom_fields.expense_policy_group",
    "custom_fields.profit_center",
    "custom_fields.per_diem_group",
}


def normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def first_entity_value(tracker: Tracker, entity_name: str) -> Optional[str]:
    values = list(tracker.get_latest_entity_values(entity_name))
    return values[0] if values else None


def all_entity_values(tracker: Tracker, entity_name: str) -> List[str]:
    return list(tracker.get_latest_entity_values(entity_name))


def safe_field(mapping: Dict[str, str], raw: Optional[str]) -> Optional[str]:
    key = normalize_text(raw)
    return mapping.get(key)


# def format_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
#     if not rows:
#         return {
#             "rows": [],
#             "columns": []
#         }

#     columns = list(rows[0].keys())

#     return {
#         "rows": rows,
#         "columns": columns
#     }
def format_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"rows": [], "columns": []}

    formatted_rows = []

    for row in rows:
        formatted_row = {}
        for key, value in row.items():
            if isinstance(value, (datetime, date)):
                formatted_row[key] = value.isoformat()
            else:
                formatted_row[key] = value
        formatted_rows.append(formatted_row)

    columns = list(formatted_rows[0].keys())

    return {
        "rows": formatted_rows,
        "columns": columns
    }

def send_table_response(
    dispatcher: CollectingDispatcher,
    rows: List[Dict[str, Any]],
    message: Optional[str] = None
):
    table_data = format_rows(rows)

    if not rows:
        dispatcher.utter_message(
            text="No records found.",
            json_message={
                "type": "table",
                "columns": table_data["columns"],
                "rows": table_data["rows"],
            },
        )
        return
    
    dispatcher.utter_message(
        text=message or f"Found {len(rows)} record(s).",
        json_message={
            "type": "table",
            "columns": table_data["columns"],
            "rows": table_data["rows"],
        }
    )

def get_employee_identifier(tracker: Tracker) -> Tuple[Optional[str], Optional[str]]:
    employee_name = first_entity_value(tracker, "employee_name")
    employee_email = first_entity_value(tracker, "employee_email")
    employee_code = first_entity_value(tracker, "employee_code")

    if employee_name:
        return "name", employee_name

    if employee_email:
        return "email", employee_email

    if employee_code:
        return "employee_code", employee_code

    return None, None


# ================================
# EMPLOYEE ACTIONS
# ================================
# class ActionGetEmployeeAttribute(Action):
#     def name(self) -> Text:
#         return "action_get_employee_attribute"

#     def run(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any]
#     ) -> List[Dict[Text, Any]]:

#         metadata = tracker.latest_message.get("metadata", {})
#         role = metadata.get("role")

#         print("Session Data:", metadata)
#         print("Running ActionGetEmployeeAttribute...")

#         # ✅ Block normal EMPLOYEE users
#         if role == "EMPLOYEE":
#             dispatcher.utter_message(
#                 text="No privilege for you to access other employee details."
#             )
#             return []

#         # ✅ Existing code continues only for non-EMPLOYEE roles
#         identifier_field, identifier_value = get_employee_identifier(tracker)
#         raw_fields = all_entity_values(tracker, "employee_field")

#         if not identifier_field or not identifier_value:
#             dispatcher.utter_message(
#                 text="Please recheck the prompt, include the employee name, email, or employee code."
#             )
#             return []

#         fields = []

#         for raw_field in raw_fields:
#             column = safe_field(EMPLOYEE_FIELDS, raw_field)
#             if column and column in SAFE_EMPLOYEE_SELECT and column not in fields:
#                 fields.append(column)

#         if not fields:
#             user_text = normalize_text(tracker.latest_message.get("text"))
#             for keyword, column in EMPLOYEE_FIELDS.items():
#                 if keyword in user_text and column not in fields:
#                     fields.append(column)

#         if not fields:
#             dispatcher.utter_message(
#                 text="Please specify which employee field you want. Example: email, mobile, department, designation, grade, branch, or status."
#             )
#             return []

#         select_parts = []

#         for field in fields:
#             if field.startswith("custom_fields."):
#                 json_key = field.split(".", 1)[1]
#                 select_parts.append(
#                     f"e.custom_fields::jsonb->>'{json_key}' AS {json_key}"
#                 )
#             else:
#                 select_parts.append(f"e.{field} AS {field}")

#         select_sql = ", ".join(select_parts)

#         sql = f"""
#         SELECT {select_sql}
#         FROM public.employees e
#         WHERE e.{identifier_field}::text ILIKE %s
#         LIMIT 1;
#         """

#         rows = run_query(sql, (f"%{identifier_value}%",))
#         send_table_response(dispatcher, rows)

#         return [
#             SlotSet("employee_name", first_entity_value(tracker, "employee_name")),
#             SlotSet("employee_email", first_entity_value(tracker, "employee_email")),
#             SlotSet("employee_code", first_entity_value(tracker, "employee_code")),
#         ]


class ActionGetEmployeeAttribute(Action):
    def name(self) -> Text:
        return "action_get_employee_attribute"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)
        print("Running ActionGetEmployeeAttribute...")

        if role == "EMPLOYEE":
            dispatcher.utter_message(
                text="No privilege for you to access other employee details."
            )
            return []

        # latest entity first
        current_employee_name = first_entity_value(tracker, "employee_name")
        current_employee_email = first_entity_value(tracker, "employee_email")
        current_employee_code = first_entity_value(tracker, "employee_code")

        # previous slot fallback
        employee_name = current_employee_name or tracker.get_slot("employee_name")
        employee_email = current_employee_email or tracker.get_slot("employee_email")
        employee_code = current_employee_code or tracker.get_slot("employee_code")

        print(f"Identified employee - Name: {employee_name}, Email: {employee_email}, Code: {employee_code}")  # Debug log

        if employee_name:
            identifier_field = "name"
            identifier_value = employee_name
        elif employee_email:
            identifier_field = "email"
            identifier_value = employee_email
        elif employee_code:
            identifier_field = "employee_code"
            identifier_value = employee_code
        else:
            dispatcher.utter_message(
                text="Please recheck the prompt, include the employee name, email, or employee code."
            )
            return []

        raw_fields = all_entity_values(tracker, "employee_field")

        fields = []

        for raw_field in raw_fields:
            column = safe_field(EMPLOYEE_FIELDS, raw_field)
            if column and column in SAFE_EMPLOYEE_SELECT and column not in fields:
                fields.append(column)

        if not fields:
            user_text = normalize_text(tracker.latest_message.get("text"))
            for keyword, column in EMPLOYEE_FIELDS.items():
                if keyword in user_text and column not in fields:
                    fields.append(column)

        if not fields:
            dispatcher.utter_message(
                text="Please specify which employee field you want. Example: email, mobile, department, designation, grade, branch, or status."
            )
            return []

        select_parts = []

        for field in fields:
            if field.startswith("custom_fields."):
                json_key = field.split(".", 1)[1]
                select_parts.append(
                    f"e.custom_fields::jsonb->>'{json_key}' AS {json_key}"
                )
            else:
                select_parts.append(f"e.{field} AS {field}")

        select_sql = ", ".join(select_parts)

        sql = f"""
        SELECT {select_sql}
        FROM public.employees e
        WHERE e.{identifier_field}::text ILIKE %s
        LIMIT 1;
        """

        rows = run_query(sql, (f"%{identifier_value}%",))
        send_table_response(dispatcher, rows)

        return [
            SlotSet("employee_name", employee_name),
            SlotSet("employee_email", employee_email),
            SlotSet("employee_code", employee_code),
        ]

# class ActionGetEmployeeByName(Action):
#     def name(self) -> Text:
#         return "action_get_employee_by_name"

#     def run(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any]
#     ) -> List[Dict[Text, Any]]:
        
#         metadata = tracker.latest_message.get("metadata", {})
#         role = metadata.get("role")
        
#         print("Session Data:", metadata)
#         print("Running ActionGetEmployeeByName...")  # Debug log
        
#         # ✅ Block normal EMPLOYEE users
#         # if role == "EMPLOYEE":
#         #     dispatcher.utter_message(
#         #         text="No privilege for you to access other employee details."
#         #     )
#         #     return []
        
#         employee_name = first_entity_value(tracker, "employee_name")
#         print(f"Extracted employee_name: {employee_name}")  # Debug log

#         if role == "EMPLOYEE":
#             logged_in_employee_name = metadata.get("employeeCode")

#             # If employee asks for own details, redirect to my details action
#             if employee_name and logged_in_employee_name and employee_name.lower() == logged_in_employee_name.lower():
#                 print("Success")
#                 return ActionGetMyEmployeeDetails().run(dispatcher, tracker, domain)

#             # If employee asks for someone else's details, block
#             dispatcher.utter_message(
#                 text="No privilege for you to access other employee details."
#             )
#             return []
        
#         if not employee_name:
#             # dispatcher.utter_message(text="Please provide employee name.")
#             dispatcher.utter_message(text="Please recheck the prompt, include the employee name.")
#             return []

#         # sql = """
#         # SELECT
#         #     email,
#         #     name,
#         #     department,
#         #     grade,
#         #     mobile,
#         #     status,
#         #     employee_code,
#         #     designation,
#         #     cost_center,
#         #     sbu,
#         #     branch,
#         #     legal_entity,
#         #     company_code,
#         #     employment_type,
#         #     job_level
#         # FROM public.employees
#         # WHERE LOWER(name) = LOWER(%s)
#         # LIMIT 1;
#         # """

#         sql = """SELECT
#                 email, name, department, grade, mobile, status, employee_code, designation, cost_center, sbu, branch, legal_entity, company_code, employment_type, job_level
#             FROM public.employees WHERE name ILIKE %s
#             LIMIT 1;"""
#         # print(f"Running SQL: {sql} with employee_name={employee_name}")
#         # rows = run_query(sql, (employee_name,))
#         rows = run_query(sql, (f"%{employee_name}%",))
#         send_table_response(dispatcher, rows)

#         return [SlotSet("employee_name", employee_name)]

class ActionGetEmployeeByName(Action):
    def name(self) -> Text:
        return "action_get_employee_by_name"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)
        print("Running ActionGetEmployeeByName...")

        employee_name = first_entity_value(tracker, "employee_name")
        print(f"Extracted employee_name: {employee_name}")

        if role == "EMPLOYEE":
            if employee_name:
                logged_in_employee_code = metadata.get("employeeCode")

                sql = """
                SELECT name
                FROM public.employees
                WHERE employee_code = %s
                LIMIT 1;
                """

                rows = run_query(sql, (logged_in_employee_code,))

                if not rows:
                    dispatcher.utter_message(
                        text="I could not identify your employee session. Please login again."
                    )
                    return []

                logged_in_employee_name = rows[0]["name"]

                confidence = name_confidence(employee_name, logged_in_employee_name)

                print("Requested name:", employee_name)
                print("Logged-in employee name:", logged_in_employee_name)
                print("Name confidence:", confidence)

                if confidence >= 0.75:
                    return ActionGetMyEmployeeDetails().run(dispatcher, tracker, domain)

                dispatcher.utter_message(
                    text="No privilege for you to access other employee details."
                )
                return []
            
            dispatcher.utter_message(
                text="Please recheck the prompt."
            )
            # dispatcher.utter_message(
            #     text="No privilege for you to access other employee details."
            # )
            return []

        if not employee_name:
            dispatcher.utter_message(
                text="Please recheck the prompt, include the employee name."
            )
            return []

        sql = """
        SELECT
            email, name, department, grade, mobile, status, employee_code,
            designation, cost_center, sbu, branch, legal_entity, company_code,
            employment_type, job_level
        FROM public.employees
        WHERE name ILIKE %s
        LIMIT 1;
        """

        rows = run_query(sql, (f"%{employee_name}%",))
        send_table_response(dispatcher, rows)

        return [SlotSet("employee_name", employee_name)]


class ActionGetEmployeeByEmail(Action):
    def name(self) -> Text:
        return "action_get_employee_by_email"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        print("Running ActionGetEmployeeByEmail...")  # Debug log

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)
        
        # ✅ Block normal EMPLOYEE users
        if role == "EMPLOYEE":
            dispatcher.utter_message(
                text="No privilege for you to access other employee details."
            )
            return []
        
        employee_email = first_entity_value(tracker, "employee_email")

        if not employee_email:
            dispatcher.utter_message(text="Please recheck the prompt, include the employee email.")
            return []

        sql = """
        SELECT
            id,
            tenant_id,
            email,
            name,
            department,
            grade,
            mobile,
            manager_id,
            status,
            employee_code,
            designation,
            cost_center,
            sbu,
            branch,
            legal_entity,
            company_code,
            employment_type,
            job_level
        FROM public.employees
        WHERE LOWER(email) = LOWER(%s)
        LIMIT 1;
        """

        rows = run_query(sql, (employee_email,))
        send_table_response(dispatcher, rows)

        return [SlotSet("employee_email", employee_email)]


class ActionGetEmployeeByCode(Action):  
    def name(self) -> Text:
        return "action_get_employee_by_code"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        print("Running ActionGetEmployeeByCode...")  # Debug log

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)

        # ✅ Block normal EMPLOYEE users
        # if role == "EMPLOYEE":
        #     dispatcher.utter_message(
        #         text="No privilege for you to access other employee details."
        #     )
        #     return []

        employee_code = first_entity_value(tracker, "employee_code")
        if role == "EMPLOYEE":
            logged_in_employee_code = metadata.get("employeeCode")

            # If employee asks for own details, redirect to my details action
            if employee_code and logged_in_employee_code and employee_code.lower() == logged_in_employee_code.lower():
                print("Success")
                return ActionGetMyEmployeeDetails().run(dispatcher, tracker, domain)

            # If employee asks for someone else's details, block
            dispatcher.utter_message(
                text="No privilege for you to access other employee details."
            )
            return []
        

        if not employee_code:
            dispatcher.utter_message(text="Please recheck the prompt, include the employee code.")
            return []

        sql = """
        SELECT
            id,
            tenant_id,
            email,
            name,
            department,
            grade,
            mobile,
            manager_id,
            status,
            employee_code,
            designation,
            cost_center,
            sbu,
            branch,
            legal_entity,
            company_code,
            employment_type,
            job_level
        FROM public.employees
        WHERE LOWER(employee_code) = LOWER(%s)
        LIMIT 1;
        """

        rows = run_query(sql, (employee_code,))
        send_table_response(dispatcher, rows)

        return [SlotSet("employee_code", employee_code)]


class ActionListEmployees(Action):
    def name(self) -> Text:
        return "action_list_employees"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:
        
        print("Running ActionListEmployees...")  # Debug log

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)

        # ✅ Block normal EMPLOYEE users
        if role == "EMPLOYEE":
            dispatcher.utter_message(
                text="No privilege for you to access other employee details."
            )
            return []
        
        department = first_entity_value(tracker, "department")
        branch = first_entity_value(tracker, "branch")
        # test
        employment_type = first_entity_value(tracker, "employment_type")
        designation = first_entity_value(tracker, "designation")

        user_text = normalize_text(tracker.latest_message.get("text"))

        sql = """
        SELECT
            name,
            email,
            department,
            designation,
            grade,
            mobile,
            branch,
            status,
            employee_code,
            employment_type,
            job_level
        FROM public.employees
        WHERE 1 = 1
        """

        params = []

        if department:
            sql += " AND LOWER(department) = LOWER(%s)"
            params.append(department)

        if branch:
            sql += " AND LOWER(branch) = LOWER(%s)"
            params.append(branch)

        if "active employees" in user_text or "active employee" in user_text:
            sql += " AND LOWER(status) = LOWER(%s)"
            params.append("active")

        if "inactive employees" in user_text or "inactive employee" in user_text:
            sql += " AND LOWER(status) = LOWER(%s)"
            params.append("inactive")

        if employment_type:
            sql += " AND LOWER(employment_type) = LOWER(%s)"
            params.append(employment_type)

        if designation: 
            sql += " AND LOWER(designation) = LOWER(%s)"
            params.append(designation)

        sql += """
        ORDER BY name
        LIMIT 50;
        """

        rows = run_query(sql, tuple(params))
        send_table_response(dispatcher, rows, message=f"Found {len(rows)} employee(s).")

        return [
            SlotSet("department", department),
            SlotSet("branch", branch),
            SlotSet("employment_type", employment_type),
            SlotSet("designation", designation),
        ]


class ActionGetEmployeeManager(Action):
    def name(self) -> Text:
        return "action_get_employee_manager"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        employee_name = first_entity_value(tracker, "employee_name")
        employee_code = first_entity_value(tracker, "employee_code")

        print("Running ActionGetEmployeeManager...")  # Debug log

        metadata = tracker.latest_message.get("metadata", {})
        role = metadata.get("role")

        print("Session Data:", metadata)
        
        # ✅ Block normal EMPLOYEE users
        if role == "EMPLOYEE":
            dispatcher.utter_message(
                text="No privilege for you to access other employee details."
            )
            return []
        
        if not employee_name and not employee_code:
            dispatcher.utter_message(
                # text="Please provide employee name or employee code."
                text="Please recheck the prompt, include the employee name or employee code."
            )
            return []

        if employee_name:
            sql = """
            SELECT
                e.name AS employee_name,
                e.employee_code AS employee_code,
                e.email AS employee_email,
                m.name AS manager_name,
                m.employee_code AS manager_employee_code,
                m.email AS manager_email,
                m.designation AS manager_designation
            FROM public.employees e
            LEFT JOIN public.employees m ON e.manager_id = m.id
            WHERE LOWER(e.name) = LOWER(%s)
            LIMIT 1;
            """
            params = (employee_name,)
        else:
            sql = """
            SELECT
                e.name AS employee_name,
                e.employee_code AS employee_code,
                e.email AS employee_email,
                m.name AS manager_name,
                m.employee_code AS manager_employee_code,
                m.email AS manager_email,
                m.designation AS manager_designation
            FROM public.employees e
            LEFT JOIN public.employees m ON e.manager_id = m.id
            WHERE LOWER(e.employee_code) = LOWER(%s)
            LIMIT 1;
            """
            params = (employee_code,)

        rows = run_query(sql, params)
        send_table_response(dispatcher, rows)

        return [
            SlotSet("employee_name", employee_name),
            SlotSet("employee_code", employee_code),
        ]


# Personal employee details and attribute actions (for EMPLOYEE role)
MY_EMPLOYEE_FIELDS = {
    # Email
    "email": "email",
    "mail": "email",
    "mail id": "email",
    "email id": "email",
    "official email": "email",
    "employee email": "email",

    # Name
    "name": "name",
    "employee name": "name",

    # Department
    "department": "department",
    "dept": "department",
    "team": "department",

    # Grade
    "grade": "grade",

    # Mobile
    "mobile": "mobile",
    "phone": "mobile",
    "phone number": "mobile",
    "mobile number": "mobile",
    "contact number": "mobile",

    # Manager
    "manager": "manager_id",
    "manager id": "manager_id",
    "manager_id": "manager_id",

    # Status
    "status": "status",
    "employee status": "status",

    # Dates
    "created": "created_at",
    "created at": "created_at",
    "created_at": "created_at",

    "updated": "updated_at",
    "updated at": "updated_at",
    "updated_at": "updated_at",

    # Employee Code
    "employee code": "employee_code",
    "employee_code": "employee_code",
    "emp code": "employee_code",
    "employee id": "employee_code",
    "emp id": "employee_code",

    # Designation
    "designation": "designation",
    "role": "designation",
    "position": "designation",
    "job title": "designation",
    "title": "designation",

    # Cost Center
    "cost center": "cost_center",
    "cost centre": "cost_center",
    "cost_center": "cost_center",

    # SBU
    "sbu": "sbu",

    # Branch / Office
    "branch": "branch",
    "location": "branch",
    "office": "branch",
    "office location": "branch",

    # Legal Entity
    "legal entity": "legal_entity",
    "legal_entity": "legal_entity",
    "company entity": "legal_entity",

    # Company Code
    "company code": "company_code",
    "company_code": "company_code",
    "organization code": "company_code",

    # Employment Type
    "employment type": "employment_type",
    "employment_type": "employment_type",
    "employee type": "employment_type",
    "work type": "employment_type",

    # Job Level
    "job level": "job_level",
    "job_level": "job_level",
    "level": "job_level",
    "employee level": "job_level",

    # Custom Fields
    "project": "custom_fields.project",
    "employee project": "custom_fields.project",

    "work location": "custom_fields.work_location_type",
    "work location type": "custom_fields.work_location_type",

    "cash advance": "custom_fields.cash_advance_allowed",
    "cash advance allowed": "custom_fields.cash_advance_allowed",

    "expense policy": "custom_fields.expense_policy_group",
    "expense policy group": "custom_fields.expense_policy_group",

    "profit center": "custom_fields.profit_center",
    "profit centre": "custom_fields.profit_center",

    "per diem group": "custom_fields.per_diem_group",
}

class ActionGetMyEmployeeDetails(Action):
    def name(self) -> Text:
        return "action_get_my_employee_details"

    def run(self, dispatcher, tracker, domain):
        metadata = tracker.latest_message.get("metadata", {})

        email = metadata.get("email")
        employee_code = metadata.get("employeeCode")

        print("Running ActionGetMyEmployeeDetails...")  # Debug log
        print("Session Data:", metadata)

        if not email and not employee_code:
            dispatcher.utter_message(
                text="I could not identify your employee session. Please login again."
            )
            return []

        sql = """
        SELECT
            email,
            name,
            department,
            grade,
            mobile,
            status,
            employee_code,
            designation,
            cost_center,
            sbu,
            branch,
            legal_entity,
            company_code,
            employment_type,
            job_level,
            custom_fields
        FROM public.employees
        WHERE
            LOWER(email) = LOWER(%s)
            OR employee_code = %s
        LIMIT 1;
        """

        rows = run_query(sql, (email, employee_code))
        send_table_response(dispatcher, rows, message="Here are your employee details.")

        return []
    

class ActionGetMyEmployeeAttribute(Action):
    def name(self) -> Text:
        return "action_get_my_employee_attribute"

    def run(self, dispatcher, tracker, domain):
        metadata = tracker.latest_message.get("metadata", {})

        print("Running ActionGetMyEmployeeAttribute...")  # Debug log
        print("Session Data:", metadata)

        email = metadata.get("email")
        employee_code = metadata.get("employeeCode")

        user_text = normalize_text(tracker.latest_message.get("text"))

        if not email and not employee_code:
            dispatcher.utter_message(
                text="I could not identify your employee session. Please login again."
            )
            return []

        fields = []

        # for keyword, column in MY_EMPLOYEE_FIELDS.items():
        for keyword, column in MY_EMPLOYEE_FIELDS.items():
            if keyword in user_text and column not in fields:
                fields.append(column)

        if not fields:
            dispatcher.utter_message(
                text="Please specify what detail you want. Example: email, mobile, department, designation, project, or work location."
            )
            return []

        select_parts = []

        for field in fields:
            if field.startswith("custom_fields."):
                json_key = field.split(".", 1)[1]
                select_parts.append(
                    f"e.custom_fields::jsonb->>'{json_key}' AS {json_key}"
                )
            else:
                select_parts.append(f"e.{field} AS {field}")

        select_sql = ", ".join(select_parts)

        sql = f"""
        SELECT
            {select_sql}
        FROM public.employees e
        WHERE
            LOWER(e.email) = LOWER(%s)
            OR e.employee_code = %s
        LIMIT 1;
        """

        rows = run_query(sql, (email, employee_code))
        send_table_response(dispatcher, rows, message="Here is your requested employee detail.")

        return []