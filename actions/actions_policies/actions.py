import json
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


def explain_policy_rule(rule: Any) -> Dict[str, Any]:
    if isinstance(rule, str):
        try:
            rule = json.loads(rule)
        except Exception:
            return {"summary": "Unable to parse policy rule.", "raw_rule": rule}

    conditions = rule.get("when", [])
    validations = rule.get("validations", [])

    condition_text = []
    for c in conditions:
    #     condition_text.append(
    #         f"{c.get('field')} {c.get('op')} {c.get('value')}"
    #     )

        # OPERATOR_MAP = {
        #     "eq": "=",
        #     "ne": "!=",
        #     "gt": ">",
        #     "gte": ">=",
        #     "lt": "<",
        #     "lte": "<=",
        # }
        OPERATOR_MAP = {
            "eq": "is equal to",
            "ne": "is not equal to",
            "gt": "is greater than",
            "gte": "is greater than or equal to",
            "lt": "is less than",
            "lte": "is less than or equal to",
        }

        FIELD_MAP = {
            "claim.total_amount": "Claim Amount",
            "employee.job_level": "Job Level",
            "employee.designation": "Designation",
            "claim.category": "Category",
        }

        field = FIELD_MAP.get(c.get("field"), c.get("field"))
        op = c.get("op", "")
        value = c.get("value", "")

        symbol = OPERATOR_MAP.get(op, op)

        condition_text.append(f"{field} {symbol} {value}")

    validation_text = []
    blocked_categories = []

    for v in validations:
        params = v.get("params", {})
        categories = params.get("categories", [])
        if categories:
            blocked_categories.extend(categories)

        validation_text.append(v.get("message", ""))

    return {
        # "applies_to": rule.get("appliesTo"),
        # "when_logic": rule.get("whenLogic"),
        "conditions": "; ".join(condition_text) if condition_text else "-",
        # "validation_type": validations[0].get("type") if validations else "-",
        "blocked_categories": ", ".join(blocked_categories) if blocked_categories else "-",
        "message": "; ".join([m for m in validation_text if m]) if validation_text else "-",
        # "severity": validations[0].get("severity") if validations else "-",
        # "workflow": rule.get("selectWorkflowName", "-"),
        # "priority": rule.get("priority", "-"),
        "description": rule.get("description", "-"),
    }


# def explain_policy_rule(rule: Any) -> Dict[str, Any]:
#     # if isinstance(rule, str):
#     #     try:
#     #         rule = json.loads(rule)
#     #     except Exception:
#     #         return {"summary": "Unable to parse policy rule.", "raw_rule": rule}

#     if isinstance(rule, str):
#         try:
#             # Fix double quotes issue
#             rule = rule.replace('""', '"')
#             rule = json.loads(rule)
#         except Exception as e:
#             print("JSON ERROR:", e)
#             print("RAW RULE:", rule)
#             return {"conditions": "-", "message": "Invalid policy format"}

#     conditions = rule.get("when", [])
#     validations = rule.get("validations", [])

#     OPERATOR_WORDS = {
#         "eq": "is equal to",
#         "ne": "is not equal to",
#         "gt": "is greater than",
#         "gte": "is greater than or equal to",
#         "lt": "is less than",
#         "lte": "is less than or equal to",
#     }

#     FIELD_MAP = {
#         "claim.total_amount": "Claim Amount",
#         "claim.category": "Claim Category",
#         "employee.job_level": "Employee Job Level",
#         "employee.designation": "Employee Designation",
#     }

#     condition_text = []

#     for c in conditions:
#         raw_field = c.get("field", "")
#         raw_op = c.get("op", "")
#         value = c.get("value", "")

#         field = FIELD_MAP.get(raw_field, raw_field)
#         operator = OPERATOR_WORDS.get(raw_op, raw_op)

#         condition_text.append(f"{field} {operator} {value}")

#     logic = rule.get("whenLogic", "AND")
#     separator = " AND " if logic == "AND" else " OR "

#     validation_text = []
#     blocked_categories = []

#     for v in validations:
#         params = v.get("params", {})
#         categories = params.get("categories", [])

#         if categories:
#             blocked_categories.extend(categories)

#         message = v.get("message", "")
#         if message:
#             validation_text.append(message)

#     return {
#         "conditions": separator.join(condition_text) if condition_text else "-",
#         "blocked_categories": ", ".join(blocked_categories) if blocked_categories else "-",
#         "message": "; ".join(validation_text) if validation_text else "-",
#         "description": rule.get("description", "-"),
#     }

class ActionGetPolicies(Action):
    def name(self) -> Text:
        return "action_get_policies"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        
        print("Running ActionGetPolicies")  # Debug log to confirm action is triggered

        policy_name = first_entity_value(tracker, "policy_name")
        policy_status = first_entity_value(tracker, "policy_status")
        user_text = normalize_text(tracker.latest_message.get("text"))
        intent_name = tracker.latest_message.get("intent", {}).get("name")

        # change column names if your real DB columns are different
        name_col = "name"
        status_col = "status"
        rule_col = "rules"

        # if intent_name == "ask_policy_details" or policy_name:
        #     sql = f"""
        #     SELECT
        #         {name_col} AS policy_name,
        #         {status_col} AS status,
        #         {rule_col} AS rule_json
        #     FROM public.policies
        #     WHERE {name_col} ILIKE %s
        #     LIMIT 1;
        #     """

        #     rows = run_query(sql, (f"%{policy_name}%",))

        #     if not rows:
        #         dispatcher.utter_message(text="No matching policy found.")
        #         return [SlotSet("policy_name", policy_name)]

        #     explained = explain_policy_rule(rows[0].get("rule_json"))

        #     output = [{
        #         "policy_name": rows[0].get("policy_name"),
        #         "status": rows[0].get("status"),
        #         **explained,
        #     }]

        #     send_table_response(
        #         dispatcher,
        #         output,
        #         message=f"Policy details for {rows[0].get('policy_name')}",
        #     )

        #     return [SlotSet("policy_name", policy_name)]

        if intent_name == "ask_policy_details" or policy_name:

            STOP_WORDS = {
                "policy", "policies", "policys",
                "rule", "rules",
                "details", "detail",
                "explain", "show", "what", "is",
                "about", "tell", "me",
                "the", "a", "an", "of", "for"
            }

            # If entity not extracted, use full user text as fallback
            search_text = policy_name or user_text

            # Clean punctuation and split
            import re
            clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", search_text.lower())
            words = clean_text.split()

            # Remove generic/noise words
            keywords = [w for w in words if w not in STOP_WORDS]

            if not keywords:
                keywords = words

            if not keywords:
                dispatcher.utter_message(text="Please provide the policy name.")
                return []

            # Build AND matching for better accuracy
            conditions = " AND ".join([f"{name_col} ILIKE %s" for _ in keywords])
            params = [f"%{word}%" for word in keywords]

            sql = f"""
            SELECT
                {name_col} AS policy_name,
                {status_col} AS status,
                {rule_col} AS rule_json
            FROM public.policies
            WHERE {conditions}
            ORDER BY {name_col}
            LIMIT 1;
            """

            rows = run_query(sql, tuple(params))

            # Fallback: try ANY keyword match if AND match fails
            if not rows:
                any_conditions = " OR ".join([f"{name_col} ILIKE %s" for _ in keywords])

                sql = f"""
                SELECT
                    {name_col} AS policy_name,
                    {status_col} AS status,
                    {rule_col} AS rule_json
                FROM public.policies
                WHERE {any_conditions}
                ORDER BY {name_col}
                LIMIT 1;
                """

                rows = run_query(sql, tuple(params))

            if not rows:
                dispatcher.utter_message(text="No matching policy found.")
                return [SlotSet("policy_name", policy_name)]

            explained = explain_policy_rule(rows[0].get("rule_json"))

            output = [{
                "policy_name": rows[0].get("policy_name"),
                "status": rows[0].get("status"),
                **explained,
            }]

            send_table_response(
                dispatcher,
                output,
                message=f"Policy details for {rows[0].get('policy_name')}",
            )

            return [SlotSet("policy_name", policy_name)]

        sql = f"""
        SELECT
            {name_col} AS policy_name,
            {status_col} AS status
        FROM public.policies
        WHERE 1 = 1
        """

        params = []

        if policy_status:
            sql += f" AND {status_col} ILIKE %s"
            params.append(f"%{policy_status}%")
        elif "active" in user_text and "inactive" not in user_text:
            sql += f" AND {status_col} ILIKE %s"
            params.append("%ACTIVE%")
        elif "inactive" in user_text:
            sql += f" AND {status_col} ILIKE %s"
            params.append("%INACTIVE%")

        sql += f"""
        ORDER BY {name_col}
        LIMIT 50;
        """

        rows = run_query(sql, tuple(params))
        send_table_response(dispatcher, rows, message=f"Found {len(rows)} policy record(s).")

        return [SlotSet("policy_status", policy_status)]